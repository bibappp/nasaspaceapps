"""Аналитика: засушливые годы, тренд NDVI, почва, запас влаги, сетки спутников."""
from __future__ import annotations

import math

import pytest

from app.analytics import climate, moisture, ndvi_trend, soil_water
from app.data_sources import modis, smap


def test_drought_uses_percentile_or_anomaly(rules):
    cfg = rules.model["drought"]
    season = {y: 160.0 + 3 * (y - 1991) for y in range(1991, 2021)}  # 160…247 мм, 20-й перцентиль ≈ 177
    season.update({1995: 100.0, 2005: 110.0, 2010: 60.0, 2015: 200.0})
    for y in range(2021, 2027):
        season[y] = 200.0
    season[2021] = 80.0
    res = climate.drought_analysis(season, cfg)
    dry = {r["year"] for r in res["years"] if r["is_dry"]}
    assert {1995, 2005, 2010, 2021} <= dry
    assert 2015 not in dry and 2000 not in dry and 2019 not in dry
    assert res["definition"]["percentile_mm"] < 200
    assert res["definition"]["baseline"] == [1991, 2020]
    assert res["window"]["n_years"] == cfg["window_years"]
    assert res["driest_year"] == 2010
    # доля и «каждый N-й год» считаются за окно последних лет, а не за весь ряд
    window = [r for r in res["years"]][-cfg["window_years"]:]
    share = sum(r["is_dry"] for r in window) / len(window)
    assert res["share"] == pytest.approx(share, abs=1e-3)
    assert res["every_nth"] == round(1 / share)


def test_season_sum_requires_complete_period():
    import pandas as pd

    days = pd.date_range("2020-01-01", "2021-07-15")
    df = pd.DataFrame({"PRECTOTCORR": 1.0}, index=days)
    season = climate.season_precip_by_year(df, [5, 6, 7, 8])
    assert season == {2020: 123.0}  # 2021 год ещё не закончился — не учитывается


def _series(values: dict[int, float]) -> list[dict]:
    rows = []
    for year, peak in values.items():
        for i, k in enumerate((0.6, 0.8, 1.0, 0.9, 0.7, 0.5)):
            rows.append({"date": f"{year}-0{5 + i // 2}-{10 + i:02d}", "ndvi": round(peak * k, 4), "valid_fraction": 1.0})
    return rows


def test_ndvi_trend_labels(rules):
    cfg = rules.model["ndvi_trend"]
    years = range(2000, 2020)
    rising = ndvi_trend.ndvi_trend(_series({y: 0.5 + 0.01 * (y - 2000) for y in years}), cfg)
    declining = ndvi_trend.ndvi_trend(_series({y: 0.8 - 0.01 * (y - 2000) for y in years}), cfg)
    noisy = ndvi_trend.ndvi_trend(_series({y: 0.65 + (0.05 if y % 2 else -0.05) for y in years}), cfg)
    short = ndvi_trend.ndvi_trend(_series({y: 0.6 for y in range(2000, 2004)}), cfg)
    assert rising["label"] == "rising" and rising["p_value"] < 0.05
    assert declining["label"] == "declining" and declining["slope_per_year"] < 0
    assert noisy["label"] == "stable"
    assert short["label"] == "insufficient"


def test_ndvi_yearly_max_skips_poor_quality_composites():
    rows = _series({2010: 0.7})
    rows.append({"date": "2010-08-01", "ndvi": 0.95, "valid_fraction": 0.2})  # облачный композит
    assert ndvi_trend.yearly_max(rows, 0.5)[0]["ndvi"] == pytest.approx(0.7)


def test_saxton_rawls_matches_published_loam():
    # Saxton & Rawls (2006), табл. 3: суглинок (40 % песка, 20 % глины, 2,5 % ОВ): ВЗ ≈ 0,15, НВ ≈ 0,28
    w = soil_water.saxton_rawls(0.40, 0.20, 2.5)
    assert w["wp"] == pytest.approx(0.15, abs=0.02)
    assert w["fc"] == pytest.approx(0.28, abs=0.02)
    assert w["wp"] < w["fc"] < w["sat"]
    sand = soil_water.saxton_rawls(0.88, 0.05, 1.0)
    assert sand["fc"] - sand["wp"] < w["fc"] - w["wp"]  # песок держит меньше влаги


def test_soil_summary_from_soilgrids_layout():
    depths = {"0-5cm": (0, 5), "5-15cm": (5, 15), "15-30cm": (15, 30), "30-60cm": (30, 60), "60-100cm": (60, 100)}

    def layer(v):
        return {"depths": {k: {"mean": v, "top_cm": a, "bottom_cm": b} for k, (a, b) in depths.items()}}

    s = soil_water.soil_summary({"properties": {"sand": layer(40.0), "clay": layer(20.0), "soc": layer(14.5), "phh2o": layer(7.0)}})
    assert s["awc_mm"] == pytest.approx(sum(L["awc_mm"] for L in s["layers"]), abs=1)
    assert 100 < s["awc_mm"] < 200
    assert s["topsoil"]["humus_pct"] == pytest.approx(14.5 / 10 * 1.724, abs=0.01)
    assert soil_water.soil_summary({"properties": {}}) is None


def test_presowing_stock_ratio_and_cap():
    offseason = {y: 100.0 for y in range(2000, 2025)}
    offseason[2010] = 50.0
    smap_years = {2016: {"mean": 0.30}, 2017: {"mean": 0.15}, 2018: {"mean": 0.30}, 2019: {"mean": 0.45}}
    res = moisture.presowing_stock(120, offseason, smap_years, awc_mm=140, bounds=(0.5, 1.5), window_years=list(range(2000, 2025)))
    by = {r["year"]: r for r in res["by_year"]}
    assert res["uses_smap"]
    assert by[2010]["basis"] == "power" and by[2010]["stock_mm"] == 60.0
    assert by[2017]["basis"] == "smap" and by[2017]["stock_mm"] == 60.0
    assert by[2019]["stock_mm"] == 140.0 and by[2019]["capped"]  # 120 x 1,5 = 180 > влагоёмкости 140


# ---- сетки спутников: эталонные значения из файлов NASA -------------------------
@pytest.mark.parametrize(
    "lat, lon, row, col, clat, clon",
    [
        # центр ячейки взят из latitude_pm/longitude_pm файла SMAP_L3_SM_P_E_20210510_R19240_001.h5
        (51.9, 71.4, 171, 2692, 51.9211, 71.3745),
        (51.68569, 70.93175, 173, 2687, 51.6945, 70.9077),
        (54.87, 69.15, 146, 2668, 54.8559, 69.1338),
    ],
)
def test_smap_ease_grid_matches_nasa_file(lat, lon, row, col, clat, clon):
    assert smap.lonlat_to_rowcol(lon, lat) == (row, col)
    c_lon, c_lat = smap.cell_center(row, col)
    assert c_lat == pytest.approx(clat, abs=1e-4) and c_lon == pytest.approx(clon, abs=1e-4)
    ring = smap.cell_polygon(row, col)
    assert ring[0] == ring[-1] and len(ring) == 5


def test_modis_sinusoidal_window_contains_request_point():
    # окно ORNL для точки 51.9N 71.4E, ±1 км (ответ сервиса 12.11.2026)
    grid = {"xllcorner": 4897910.42, "yllcorner": 5769864.88, "cellsize": 231.656358264, "nrows": 9, "ncols": 9}
    lon, lat = modis.pixel_center(grid, 4, 4)
    assert lat == pytest.approx(51.9, abs=0.003) and lon == pytest.approx(71.4, abs=0.004)
    assert math.isclose(grid["cellsize"], 231.656358264)
