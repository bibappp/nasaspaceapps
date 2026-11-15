"""«Часы голой почвы»: GET /api/fields/{id}/bare-soil (контракт docs/contracts/bare_soil.example.json)
и расчёт app/analytics/bare_soil.py. Синтетические ряды в юнит-тестах — не данные какого-либо поля."""
from __future__ import annotations

import ast
import asyncio
import dataclasses
import json
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.analytics import bare_soil as bs
from app.config import get_settings
from app.data_sources import base
from app.data_sources.base import demo_field_record
from app.data_sources.registry import SOURCES
from app.main import app
from app.model.rules import get_rules
from app.schemas import BareSoilOut
from app.services.bare_soil import DEFAULT_START_YEAR, MIN_YEAR, resolve_period

pytestmark = pytest.mark.skipif(demo_field_record() is None, reason="нет data/demo")
H = {"X-Requested-With": "agro"}
CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "bare_soil.example.json"
CURRENT_YEAR = date.today().year
_DEMO_DIR = get_settings().demo_dir
#: межсезонье MODIS и квантили NDVI появятся в data/demo после загрузки на машине с доступом к ORNL
#: (TODO в docs/HACKATHON_LOG.md); тесты ниже проверяют оба состояния демо-данных
SHOULDER_IN_DEMO = (_DEMO_DIR / "modis_shoulder.json").exists()
QUANTILES_IN_DEMO = (_DEMO_DIR / "modis.json").exists() and any(
    r.get("ndvi_q") for r in json.loads((_DEMO_DIR / "modis.json").read_text(encoding="utf-8"))["series"])


def _contract() -> dict:
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    data.pop("_comment", None)
    return data


def _shape(obj):
    """Вложенная структура ключей; у списков — по первому элементу, у пустых — None."""
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_shape(obj[0])] if obj else None
    return None


def _same_keys(actual, expected, path="$"):
    """Ключи ответа совпадают с контрактом везде, где оба списка непусты."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert set(actual) == set(expected), f"{path}: {sorted(actual)} != {sorted(expected)}"
        for k in expected:
            _same_keys(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list) and actual:
        _same_keys(actual[0], expected[0], f"{path}[0]")


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    s = get_settings()
    old = (s.db_path, s.offline)
    s.db_path = tmp_path_factory.mktemp("db") / "t.db"
    s.offline = True
    with TestClient(app) as c, TestClient(app) as other:
        c.post("/api/auth/register", json={"email": "bs@example.org", "password": "password-123"}, headers=H)
        other.post("/api/auth/register", json={"email": "bs2@example.org", "password": "password-123"}, headers=H)
        demo = demo_field_record()
        f = c.post("/api/fields", json={"name": "Демо", "region": "akmola", "geometry": demo["geometry"],
                                        "history": demo["history"]}, headers=H).json()
        yield c, other, f["id"]
    s.db_path, s.offline = old


def test_schema_accepts_the_contract_example():
    BareSoilOut.model_validate(_contract())


def test_response_matches_schema_and_contract_shape(ctx):
    c, _, fid = ctx
    r = c.get(f"/api/fields/{fid}/bare-soil")
    assert r.status_code == 200
    body = r.json()
    BareSoilOut.model_validate(body)
    _same_keys(body, _shape(_contract()))
    assert body["field_id"] == fid


def test_demo_defaults_and_month_invariants(ctx):
    c, _, fid = ctx
    body = c.get(f"/api/fields/{fid}/bare-soil").json()
    assert body["period"] == {"start_year": DEFAULT_START_YEAR, "end_year": CURRENT_YEAR}
    assert body["status"] == "partial"  # межсезонье MODIS ещё не скачано
    assert body["jobs"] == []  # OFFLINE=1: фоновые загрузки не запускаются
    assert [y["year"] for y in body["years"]] == list(range(DEFAULT_START_YEAR, CURRENT_YEAR + 1))
    min_known = get_rules().erosion["month"]["min_known_fraction"].value
    states = set()
    for y in body["years"]:
        assert [m["month"] for m in y["months"]] == list(range(1, 13))
        for m in y["months"]:
            states.add(m["state"])
            if m["state"] == "ok":
                assert m["known_days"] >= min_known * m["days_in_month"]
                assert m["exposure"] == pytest.approx(m["joint_days"] / m["known_days"], abs=1e-4)
                assert m["joint_days"] <= min(m["bare_days"], m["erosive_wind_days"], m["dry_days"])
                assert m["missing_reason"] is None and m["moisture_source"] in ("smap", "power_gwettop", "mixed")
            elif m["state"] == "missing":
                # нет данных — это null и причина, а не ноль
                assert m["exposure"] is None and m["joint_days"] is None and m["bare_days"] is None
                assert m["quality"] == "missing" and m["missing_reason"] in bs.UNKNOWN_CAUSES
            else:
                assert m["exposure"] is None and m["bare_days"] is None
    assert states == {"ok", "snow", "missing"}
    feb = {y["year"]: y["months"][1]["days_in_month"] for y in body["years"]}
    assert feb[2016] == 29 and feb[2017] == 28
    assert {s["id"] for s in body["sources"]} == {"power", "modis", "smap"}
    assert set(body["definition"]["exposure"]) == {"ru", "kk", "en"}


def test_demo_months_without_ndvi_are_missing_pending_fetch(ctx):
    """Пока межсезонье MODIS не скачано, апрель и вторая половина октября — missing (не 0) с причиной."""
    c, _, fid = ctx
    body = c.get(f"/api/fields/{fid}/bare-soil", params={"start_year": 2016, "end_year": 2025}).json()
    if SHOULDER_IN_DEMO:
        reasons = {m["missing_reason"] for y in body["years"] for m in y["months"]}
        assert "ndvi_pending_fetch" not in reasons
        assert "ndvi_pending_fetch" not in {w["code"] for w in body["warnings"]}
        return
    for y in body["years"]:
        april = y["months"][3]
        assert april["state"] == "missing" and april["exposure"] is None
        assert april["missing_reason"] == "ndvi_pending_fetch"
    codes = {w["code"]: w for w in body["warnings"]}
    assert codes["ndvi_pending_fetch"]["source"] == "modis_shoulder"
    assert codes["ndvi_pending_fetch"]["params"]["months"] >= 10


def test_demo_warnings(ctx):
    c, _, fid = ctx
    body = c.get(f"/api/fields/{fid}/bare-soil", params={"start_year": 2014, "end_year": 2025}).json()
    w = {(x["code"], x["source"]) for x in body["warnings"]}
    assert ("cell_larger_than_field", "power") in w
    assert ("cell_larger_than_field", "smap") in w  # в апреле–мае используется SMAP
    assert ("smap_before_2015_unavailable", "smap") in w
    assert ("moisture_fallback_gwettop", "smap") in w
    proxy = next((x for x in body["warnings"] if x["code"] == "ndvi_field_mean_proxy"), None)
    if QUANTILES_IN_DEMO:
        assert proxy is None
    else:
        assert proxy["params"]["months"] > 0 and max(proxy["params"]["years"]) <= 2020  # растры есть с 2021 г.
    assert "bare_soil_not_computed" not in {x["code"] for x in body["warnings"]}


def test_thresholds_in_response_come_from_rules(ctx):
    c, _, fid = ctx
    body = c.get(f"/api/fields/{fid}/bare-soil").json()
    e = get_rules().erosion
    got = {t["id"]: t for t in body["thresholds"]}
    assert set(got) == {"ndvi_bare", "erosive_wind_ms", "dry_topsoil"}
    for cid, ref in e["contract_thresholds"].items():
        group, key = ref.split(".")
        assert got[cid]["value"] == e[group][key].value and got[cid]["source"] == e[group][key].source_id
    eff = body["effective_thresholds"]
    assert eff["ndvi_max"] == e["bare_soil"]["ndvi_max"].value
    assert eff["wind_parameter"] == e["erosive_wind"]["power_parameter"]
    assert eff["gwettop_basis"] == "cdf_match" and eff["gwettop_pairs"] >= e["dry_topsoil"]["gwettop_min_pairs"].value


def test_climatology_and_headline_shape(ctx):
    c, _, fid = ctx
    body = c.get(f"/api/fields/{fid}/bare-soil", params={"start_year": 2015, "end_year": 2025}).json()
    clim = {x["month"]: x for x in body["climatology"]}
    assert set(clim) == set(range(1, 13))
    assert clim[7]["n_years"] >= 3 and clim[7]["exposure_median"] is not None
    if not SHOULDER_IN_DEMO:
        assert clim[4]["n_years"] == 0 and clim[4]["exposure_median"] is None  # апрель ждёт межсезонья MODIS
    for m in body["headline"]["top_months"]:
        assert clim[m]["exposure_median"] > 0
    for w in body["cover_crop_windows"]:
        assert w["needs_review"] == ["kk"] and w["basis"]["kk"].endswith(bs.KK_REVIEW.strip())
        assert w["uncertainty"] in ("low", "medium", "high")
        assert w["start"] >= body["effective_thresholds"]["harvest_end"]
    if not body["cover_crop_windows"]:
        note = body["cover_crop_note"]
        assert note["reason"] and note["basis"]["ru"]
        assert note["advice_scope"] == "general_guidance" and set(note["advice"]) == {"ru", "kk", "en"}
        assert "стерн" in note["advice"]["ru"] and "stubble" in note["advice"]["en"]
        assert note["advice"]["kk"].endswith(bs.KK_REVIEW.strip()) and note["needs_review"] == ["kk"]
        src = get_rules().sources["bilbro_fryrear_1994"]
        assert note["advice_source"] == {"id": "bilbro_fryrear_1994", "name": src["name"], "url": src["url"],
                                         "note": src["note"]}
        assert "только по выдержке" in note["advice_source"]["note"]  # статус проверки — как записан
    else:
        assert body["cover_crop_note"] is None


def test_explicit_period(ctx):
    c, _, fid = ctx
    body = c.get(f"/api/fields/{fid}/bare-soil", params={"start_year": 2020, "end_year": 2022}).json()
    assert body["period"] == {"start_year": 2020, "end_year": 2022}
    assert [y["year"] for y in body["years"]] == [2020, 2021, 2022]


def test_demo_field_sources_come_from_demo_data_offline(ctx):
    """OFFLINE=1 на демо-поле: сеть не нужна, происхождение данных — демо."""
    c, _, fid = ctx
    assert get_settings().offline
    origins = {s["id"]: s["origin"] for s in c.get(f"/api/fields/{fid}/bare-soil").json()["sources"]}
    assert "demo" in origins.values()


@pytest.mark.parametrize("params", [
    {"start_year": MIN_YEAR - 1},
    {"end_year": CURRENT_YEAR + 1},
    {"start_year": 2020, "end_year": 2019},
    {"start_year": "abc"},
])
def test_out_of_range_is_422(ctx, params):
    c, _, fid = ctx
    assert c.get(f"/api/fields/{fid}/bare-soil", params=params).status_code == 422


def test_range_bounds_are_inclusive(ctx):
    c, _, fid = ctx
    r = c.get(f"/api/fields/{fid}/bare-soil", params={"start_year": MIN_YEAR, "end_year": CURRENT_YEAR})
    assert r.status_code == 200 and len(r.json()["years"]) == CURRENT_YEAR - MIN_YEAR + 1


def test_foreign_field_is_404(ctx):
    _, other, fid = ctx
    assert other.get(f"/api/fields/{fid}/bare-soil").status_code == 404
    assert other.get("/api/fields/99999/bare-soil").status_code == 404


def test_requires_login():
    with TestClient(app) as anon:
        assert anon.get("/api/fields/1/bare-soil").status_code in (401, 403)


def test_resolve_period_uses_given_today():
    assert resolve_period(None, None, date(2027, 3, 1)) == (2015, 2027)
    with pytest.raises(ValueError):
        resolve_period(2000, None, date(2027, 3, 1))


# ---------------------------------------------------------------- расчёт на синтетических рядах
E = get_rules().erosion
NDVI_MAX = E["bare_soil"]["ndvi_max"].value
WIND = E["erosive_wind"]["speed_ms"].value
GW_THR = E["dry_topsoil"]["gwettop_fallback"].value
SMAP_THR = E["dry_topsoil"]["smap_fallback_m3m3"].value
WIND_COL = E["erosive_wind"]["power_parameter"]
LOW, HIGH = NDVI_MAX - 0.1, NDVI_MAX + 0.3  # «без покрова» и «зелёный покров» относительно порога из правил


def power_df(start: date, end: date, **over) -> pd.DataFrame:
    """Синтетический POWER: каждый день ветрено и сухо, снега нет, тепло."""
    idx = pd.date_range(start, end, freq="D")
    df = pd.DataFrame({WIND_COL: WIND + 1.0, "GWETTOP": GW_THR - 0.1, "FRSNO": 0.0, "SNODP": 0.0,
                       "T2M_MIN": 10.0}, index=idx)
    for col, val in over.items():
        df[col] = val
    return df


def comp(start: date, value: float, *, valid: bool = True, snow: bool = False) -> bs.Composite:
    return bs.Composite(start, value, valid, snow, False)


NO_SMAP = pd.Series(dtype=float)
APR1 = date(2024, 4, 1)


def run_daily(df, comps, e=E, sm=NO_SMAP, start=APR1, end=date(2024, 4, 30)):
    return bs.daily_conditions(df, comps, sm, SMAP_THR, GW_THR, e, start, end)


def month(daily, e=E, y=2024, m=4):
    return bs.month_summary(daily, y, m, e, last_weather=date(2030, 1, 1), ndvi_ready={"main": True, "shoulder": True})


def patch(e: dict, group: str, key: str, value) -> dict:
    g = dict(e[group])
    g[key] = dataclasses.replace(g[key], value=value)
    return {**e, group: g}


APRIL = [comp(APR1, LOW), comp(APR1 + timedelta(days=16), LOW)]  # окна 1–16 и 17 апр – 2 мая


def test_snow_is_never_bare_power():
    df = power_df(APR1, date(2024, 4, 30))
    df.loc["2024-04-10":"2024-04-14", ["FRSNO", "SNODP"]] = [1.0, 10.0]
    d = run_daily(df, APRIL)
    snowy = d.loc["2024-04-10":"2024-04-14"]
    assert snowy["snow"].all() and not snowy["bare"].any() and snowy["bare"].notna().all()
    assert d.loc["2024-04-01":"2024-04-09", "bare"].all()
    mo = month(d)
    assert mo["state"] == "ok" and mo["bare_days"] == 25 and mo["joint_days"] == 25


def test_snow_is_never_bare_modis_reliability():
    """Композит, где снег (код 2) у большинства пикселей, — снежный, хотя NDVI низкий."""
    code = str(E["snow"]["modis_reliability_snow"].value)
    counts = {"-1": 0, "0": 1, "1": 0, "2": 0, "3": 0}
    counts[code] = 8
    modis = {"series": [{"date": APR1.isoformat(), "ndvi": LOW, "valid_fraction": 1.0, "reliability_counts": counts,
                         "ndvi_q": [LOW] * 9}]}
    comps = bs.composites([modis], E)
    assert comps[0].snow and not comps[0].valid
    d = run_daily(power_df(APR1, date(2024, 4, 30)), comps)
    first = d.loc["2024-04-01":"2024-04-16"]
    assert first["snow"].all() and not first["bare"].any()


def test_snow_month_state():
    df = power_df(APR1, date(2024, 4, 30))
    df.loc["2024-04-01":"2024-04-20", ["FRSNO", "SNODP"]] = [1.0, 10.0]
    mo = month(run_daily(df, APRIL))
    assert mo["state"] == "snow" and mo["exposure"] is None and mo["bare_days"] is None


def test_unknown_condition_day_never_counts_as_joint():
    """В день, когда хоть одно условие неизвестно, опасного дня нет (0), и он не входит в known_days."""
    df = power_df(APR1, date(2024, 4, 30))
    df.loc["2024-04-21":"2024-04-30", "GWETTOP"] = np.nan  # сухость неизвестна (SMAP тоже нет)
    df.loc["2024-04-05", WIND_COL] = np.nan                # ветер неизвестен
    d = run_daily(df, APRIL)
    joint = (d["bare"] & d["windy"] & d["dry"]).fillna(False)
    assert not joint.loc["2024-04-21":"2024-04-30"].any() and not joint.loc["2024-04-05"]
    mo = month(d)
    assert mo["known_days"] == 19 and mo["joint_days"] == 19
    assert mo["exposure"] == 1.0  # joint_days / known_days, а не / days_in_month
    assert mo["quality"] == "partial" and mo["state"] == "ok"


def test_too_few_known_days_is_missing_not_zero():
    df = power_df(APR1, date(2024, 4, 30))
    df.loc["2024-04-10":"2024-04-30", "GWETTOP"] = np.nan
    mo = month(run_daily(df, APRIL))
    assert mo["state"] == "missing" and mo["exposure"] is None and mo["joint_days"] is None
    assert mo["missing_reason"] == "no_moisture"


def test_missing_reason_pending_fetch():
    d = run_daily(power_df(APR1, date(2024, 4, 30)), [])
    mo = bs.month_summary(d, 2024, 4, E, last_weather=date(2030, 1, 1), ndvi_ready={"main": True, "shoulder": False})
    assert mo["state"] == "missing" and mo["missing_reason"] == "ndvi_pending_fetch"
    mo = bs.month_summary(d, 2024, 4, E, last_weather=date(2030, 1, 1), ndvi_ready={"main": True, "shoulder": True})
    assert mo["missing_reason"] == "ndvi_gap"
    mo = bs.month_summary(d, 2024, 4, E, last_weather=date(2024, 3, 31), ndvi_ready={"main": True, "shoulder": True})
    assert mo["missing_reason"] == "future"


def test_interpolation_bridges_one_missing_composite():
    a, c = comp(APR1, LOW), comp(APR1 + timedelta(days=32), HIGH)  # пропущен один композит (облака)
    d = run_daily(power_df(APR1, date(2024, 5, 31)), [a, c], end=date(2024, 5, 31))
    assert d["ndvi"].loc["2024-04-01":"2024-05-18"].notna().all()
    mid = d["ndvi"].loc[pd.Timestamp(a.mid + timedelta(days=16))]
    assert mid == pytest.approx((LOW + HIGH) / 2)


def test_no_interpolation_across_long_gap():
    gap = int(E["ndvi_daily"]["max_interp_gap_days"].value) + 16
    a, b = comp(APR1, LOW), comp(APR1 + timedelta(days=gap), LOW)
    d = run_daily(power_df(APR1, date(2024, 6, 30)), [a, b], end=date(2024, 6, 30))
    between = d.loc[pd.Timestamp(a.end + timedelta(days=1)):pd.Timestamp(b.start - timedelta(days=1))]
    assert len(between) > 0 and between["ndvi"].isna().all() and between["bare"].isna().all()


def test_no_interpolation_across_snow():
    a, c = comp(APR1, LOW), comp(APR1 + timedelta(days=32), LOW)
    df = power_df(APR1, date(2024, 5, 31))
    df.loc["2024-04-20", ["FRSNO", "SNODP"]] = [1.0, 10.0]
    d = run_daily(df, [a, c], end=date(2024, 5, 31))
    gap_days = d.loc["2024-04-17":"2024-05-02"].drop(pd.Timestamp("2024-04-20"))
    assert gap_days["bare"].isna().all()
    assert d.loc["2024-04-20", "bare"] == False  # noqa: E712 — снежный день известен: покров есть


def test_thresholds_are_read_from_rules():
    df = power_df(APR1, date(2024, 4, 30))
    assert month(run_daily(df, APRIL))["bare_days"] == 30
    e = patch(E, "bare_soil", "ndvi_max", LOW - 0.05)
    assert month(run_daily(df, APRIL, e=e), e=e)["bare_days"] == 0
    e = patch(E, "erosive_wind", "speed_ms", WIND + 5)
    mo = month(run_daily(df, APRIL, e=e), e=e)
    assert mo["erosive_wind_days"] == 0 and mo["exposure"] == 0.0
    e = patch(E, "month", "min_known_fraction", 1.0)
    df2 = df.copy()
    df2.loc["2024-04-30", "GWETTOP"] = np.nan
    assert month(run_daily(df2, APRIL, e=e), e=e)["state"] == "missing"


def test_no_threshold_literals_in_analytics():
    """В app/analytics/bare_soil.py нет чисел в сравнениях, кроме 0 и 1 (счёт): пороги — только из erosion.yaml."""
    tree = ast.parse(Path(bs.__file__).read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for side in [node.left, *node.comparators]:
                if isinstance(side, ast.Constant) and isinstance(side.value, int | float) \
                        and not isinstance(side.value, bool) and side.value not in (0, 1):
                    bad.append((node.lineno, side.value))
    assert bad == []


def test_gwettop_threshold_cdf_match_and_fallback():
    days = pd.date_range("2020-04-01", periods=100, freq="D")
    sm = pd.Series(np.linspace(0.10, 0.30, 100), index=days)
    df = pd.DataFrame({"GWETTOP": np.linspace(0.5, 0.9, 100)}, index=days)
    snow = pd.Series(False, index=days)
    gw = bs.gwettop_threshold(df, sm, 0.15, snow, E)
    share_smap = float((sm < 0.15).mean())
    assert gw["basis"] == "cdf_match" and gw["pairs"] == 100
    assert float((df["GWETTOP"] < gw["value"]).mean()) == pytest.approx(share_smap, abs=0.02)
    few = bs.gwettop_threshold(df, sm.iloc[:5], 0.15, snow, E)
    assert few["basis"] == "fallback" and few["value"] == GW_THR


def test_smap_preferred_over_gwettop():
    df = power_df(APR1, date(2024, 4, 30))
    sm = pd.Series(SMAP_THR + 0.1, index=pd.date_range("2024-04-01", "2024-04-30"))  # SMAP: влажно
    mo = month(run_daily(df, APRIL, sm=sm))
    assert mo["moisture_source"] == "smap" and mo["dry_days"] == 0 and mo["exposure"] == 0.0
    mo = month(run_daily(df, APRIL, sm=sm.iloc[:10]))
    assert mo["moisture_source"] == "mixed" and mo["quality"] == "partial"


def test_climatology_headline_and_cover_crop_windows():
    years = [{"year": y, "months": [{"month": m, "state": "ok", "quality": "ok",
                                     "exposure": 0.4 if m == 8 else 0.0} for m in range(1, 13)]}
             for y in range(2010, 2022)]
    clim = bs.climatology(years, E)
    assert clim[7]["exposure_median"] == 0.4 and clim[7]["n_years"] == 12
    assert bs.headline(clim, E) == {"top_months": [8], "max_median_exposure": 0.4}
    frost = {"n_years": 12, "last_spring": date(2001, 5, 10), "first_autumn": date(2001, 11, 15)}
    cc = bs.cover_crop_windows(clim, years, frost, E, None)
    assert cc["windows"] == [] and cc["note"]["reason"] == "no_harvest_date"
    # август — до уборки (01.10): окна нет, текст объясняет почему
    cc = bs.cover_crop_windows(clim, years, frost, E, "akmola")
    assert cc["windows"] == [] and cc["note"]["reason"] == "risk_before_harvest_only"
    assert "август" in cc["note"]["basis"]["ru"] and "сев–уборка" in cc["note"]["basis"]["ru"]
    assert cc["note"]["needs_review"] == ["kk"] and cc["note"]["basis"]["kk"].endswith("(ана тілінде тексеру қажет)")
    assert cc["note"]["advice"] == bs.NO_WINDOW_ADVICE and cc["note"]["advice_scope"] == "general_guidance"
    assert "General guidance, not a field-specific recommendation" in cc["note"]["advice"]["en"]


def _years_with(exposure: dict[int, float]) -> list[dict]:
    return [{"year": y, "months": [{"month": m, "state": "ok", "quality": "ok", "exposure": exposure.get(m, 0.0)}
                                   for m in range(1, 13)]} for y in range(2010, 2022)]


def test_cover_crop_window_starts_after_harvest_only():
    years = _years_with({5: 0.3, 9: 0.3, 10: 0.4, 11: 0.4})
    clim = bs.climatology(years, E)
    harvest = date.fromisoformat("2001-" + E["cover_crop"]["harvest_end"]["kostanay"].value)
    frost = {"n_years": 12, "last_spring": date(2001, 5, 7), "first_autumn": date(2001, 12, 1)}
    cc = bs.cover_crop_windows(clim, years, frost, E, "kostanay")
    assert cc["note"] is None and len(cc["windows"]) == 1
    w = cc["windows"][0]
    # май (сев) и сентябрь (до уборки) не попадают в окно; окно — с даты окончания уборки
    assert w["start"] == harvest.strftime("%m-%d") and w["end"] == "11-30"
    assert harvest.strftime("%d.%m") in w["basis"]["ru"]
    for win in cc["windows"]:
        assert date.fromisoformat("2001-" + win["start"]) >= harvest


def test_cover_crop_no_window_when_frost_before_establishment():
    """Как у демо-полей: опасны май и осень, но заморозок раньше, чем покровная культура взойдёт."""
    years = _years_with({5: 0.29, 9: 0.23, 10: 0.26, 11: 0.47})
    clim = bs.climatology(years, E)
    frost = {"n_years": 11, "last_spring": date(2001, 5, 7), "first_autumn": date(2001, 9, 29)}
    cc = bs.cover_crop_windows(clim, years, frost, E, "kostanay")
    assert cc["windows"] == [] and cc["note"]["reason"] == "frost_before_establishment"
    ru, en = cc["note"]["basis"]["ru"], cc["note"]["basis"]["en"]
    assert "май (0,29)" in ru and "до окончания уборки" in ru and "29.09" in ru
    assert "before a cover crop could establish" in en
    # заморозок позже уборки, но дней меньше min_frost_free_days
    frost2 = {**frost, "first_autumn": date(2001, 10, 20)}
    cc = bs.cover_crop_windows(clim, years, frost2, E, "kostanay")
    assert cc["windows"] == [] and cc["note"]["reason"] == "frost_before_establishment"
    assert "только 19 дн." in cc["note"]["basis"]["ru"]


def test_cover_crop_no_risky_months_and_no_frost():
    years = _years_with({})
    clim = bs.climatology(years, E)
    frost = {"n_years": 11, "last_spring": date(2001, 5, 7), "first_autumn": date(2001, 9, 29)}
    assert bs.cover_crop_windows(clim, years, frost, E, "akmola")["note"]["reason"] == "no_risky_months"
    none = {"n_years": 0, "last_spring": None, "first_autumn": None}
    assert bs.cover_crop_windows(clim, years, none, E, "akmola")["note"]["reason"] == "no_frost_data"


def test_frost_dates_from_t2m_min():
    idx = pd.date_range("2019-01-01", "2020-12-31", freq="D")
    tmin = pd.Series(10.0, index=idx)
    tmin[(idx.month <= 4) | ((idx.month == 5) & (idx.day <= 12))] = -5.0
    tmin[(idx.month >= 10)] = -5.0
    f = bs.frost_dates(pd.DataFrame({"T2M_MIN": tmin}), E, range(2019, 2021))
    assert f["n_years"] == 2 and f["last_spring"] == date(2001, 5, 12) and f["first_autumn"] == date(2001, 10, 1)


# ---------------------------------------------------------------- новое поле запускает фоновые загрузки
NEW_FIELD = {"type": "Polygon", "coordinates": [[[66.0, 50.0], [66.02, 50.0], [66.02, 50.01], [66.0, 50.01], [66.0, 50.0]]]}


def test_new_field_triggers_shoulder_job(tmp_data, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "offline", False)
    monkeypatch.setattr(s, "db_path", tmp_data / "t.db")
    for k in ("earthdata_token", "earthdata_username", "earthdata_password"):
        monkeypatch.setattr(s, k, None)  # SMAP не настроен: тест детерминирован и на машине с токеном
    base._failures.clear()
    days = pd.date_range("2014-01-01", date.today(), freq="D")
    power_data = {"lat": 50.0, "lon": 66.0, "daily": {
        "date": [d.strftime("%Y-%m-%d") for d in days],
        **{c: [1.0] * len(days) for c in ("PRECTOTCORR", "T2M", "T2M_MAX", "T2M_MIN", "GWETROOT", "GWETTOP",
                                          "WS2M", "WS10M", "WS2M_MAX", "WS10M_MAX", "FRSNO", "SNODP")}}}
    called: list[str] = []

    async def power_live(*a, **k):
        return power_data

    async def soil_live(*a, **k):
        raise base.SourceError("stub: SoilGrids not used in this test")

    def slow_stub(sid):
        async def live(*a, **k):
            called.append(sid)
            await asyncio.sleep(0.05)
            return {"series": [], "partial": True}  # неполный результат в кэш не попадает
        return live

    monkeypatch.setattr(SOURCES["power"], "_fetch_live", power_live)
    monkeypatch.setattr(SOURCES["soilgrids"], "_fetch_live", soil_live)
    for sid in ("modis", "modis_shoulder"):
        monkeypatch.setattr(SOURCES[sid], "_fetch_live", slow_stub(sid))

    def no_network(request):
        raise AssertionError(f"unexpected network request {request.url}")

    real = httpx.AsyncClient
    monkeypatch.setattr(base.httpx, "AsyncClient", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(no_network)}))

    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "new@example.org", "password": "password-123"}, headers=H)
        fid = c.post("/api/fields", json={"name": "Новое", "region": "akmola", "geometry": NEW_FIELD,
                                          "history": []}, headers=H).json()["id"]
        body = c.get(f"/api/fields/{fid}/bare-soil").json()
        by_source = {j["source"]: j for j in body["jobs"]}
        assert by_source["modis_shoulder"]["status"] == "pending"
        assert by_source["modis_shoulder"]["job"]["kind"] == "modis_shoulder"
        assert "modis" in by_source
        assert body["status"] == "loading"  # NDVI ещё нет — ничего не посчитано, загрузки идут
        for y in body["years"]:
            for m in y["months"]:
                assert m["state"] in ("missing", "snow") and m["exposure"] is None
        job = jobs.get_job(by_source["modis_shoulder"]["job"]["id"])
        for _ in range(200):  # задача идёт в цикле событий TestClient; ждём её завершения
            if job.status != "running":
                break
            time.sleep(0.01)
    assert "modis_shoulder" in called
