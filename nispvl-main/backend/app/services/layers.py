"""Слои карты: NDVI (пиксели MODIS), влажность почвы (ячейки SMAP), осадки (ячейка POWER).

Каждый слой — GeoJSON FeatureCollection из прямоугольников-ячеек со значением ``value``
и блоком ``meta`` (единицы, шкала легенды, разрешение источника, список доступных дат).
"""
from __future__ import annotations

from datetime import date

import numpy as np

from ..analytics import climate
from ..data_sources import modis, smap
from ..data_sources.base import demo_field_record
from ..data_sources.registry import SOURCES, source_catalog
from ..geometry import Field, GeometryError, parse_field
from ..model.rules import get_rules
from .analysis import MODIS_START, POWER_START, SMAP_START

KINDS = ("ndvi", "ndvi_anomaly", "soil_moisture", "precip")

# сетка метеопараметров MERRA-2, на которой отдаёт данные NASA POWER
POWER_DLAT, POWER_DLON = 0.5, 0.625


class LayerError(RuntimeError):
    pass


def field_for_bbox(bbox: tuple[float, float, float, float]) -> Field:
    """Поле для запроса слоя. Если bbox совпадает с демо-полем — берём само демо-поле."""
    minx, miny, maxx, maxy = bbox
    rec = demo_field_record()
    if rec:
        demo = parse_field(rec["geometry"])
        if all(abs(a - b) < 1e-4 for a, b in zip(demo.bbox, bbox)):
            return demo
    return parse_field(
        {"type": "Polygon", "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]]}
    )


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    try:
        parts = [float(p) for p in text.split(",")]
    except ValueError as exc:
        raise GeometryError("bbox must be 'minLon,minLat,maxLon,maxLat'") from exc
    if len(parts) != 4 or parts[0] >= parts[2] or parts[1] >= parts[3]:
        raise GeometryError("bbox must be 'minLon,minLat,maxLon,maxLat'")
    return parts[0], parts[1], parts[2], parts[3]


def _feature(ring: list[list[float]], value: float | None, **props) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"value": value, **props},
    }


def _meta(source_id: str, **extra) -> dict:
    cat = source_catalog()[source_id]
    return {
        "source": source_id,
        "source_title": cat["title"],
        "resolution_m": cat.get("resolution_m"),
        "spatial_resolution": cat["spatial_resolution"],
        **extra,
    }


def _nearest(dates: list[str], wanted: str | None) -> str:
    if not wanted or wanted in dates:
        return wanted if wanted in dates else dates[-1]
    target = date.fromisoformat(wanted)
    return min(dates, key=lambda d: abs((date.fromisoformat(d) - target).days))


async def ndvi_layer(field: Field, when: str | None) -> dict:
    res = SOURCES["modis"].read_cached(field, MODIS_START, date.today())
    if res is None:
        res = await SOURCES["modis"].fetch(field, MODIS_START, date.today())
    if not res.ok or not res.data.get("rasters"):
        raise LayerError("NDVI raster is not available for this field yet")
    d = res.data
    dates = sorted(d["rasters"])
    chosen = _nearest(dates, when)
    grid, raster, mask = d["grid"], d["rasters"][chosen], d["field_mask"]
    scale = d.get("ndvi_scale", 0.0001)
    feats = []
    for r in range(grid["nrows"]):
        for c in range(grid["ncols"]):
            i = r * grid["ncols"] + c
            v = raster[i]
            feats.append(
                _feature(
                    modis.pixel_polygon(grid, r, c),
                    None if v is None else round(v * scale, 3),
                    in_field=bool(mask[i]),
                )
            )
    return {
        "type": "FeatureCollection",
        "features": feats,
        "meta": _meta(
            "modis", kind="ndvi", date=chosen, dates=dates, unit="NDVI", legend={"min": 0.1, "max": 0.8}, origin=res.origin
        ),
    }


def _year_of(when: str | None, years: list[int]) -> int:
    wanted = int(when[:4]) if when else years[-1]
    return min(years, key=lambda y: abs(y - wanted))


async def soil_moisture_layer(field: Field, when: str | None) -> dict:
    months = get_rules().model["presowing"]["months"]
    res = SOURCES["smap"].read_cached(field, SMAP_START, date.today())
    if res is not None and res.ok and res.data.get("daily"):
        d = res.data
        n = d["window_cells"]
        acc: dict[int, tuple[list[float], list[int]]] = {}
        for row in d["daily"]:
            if int(row["date"][5:7]) not in months:
                continue
            sums, cnts = acc.setdefault(int(row["date"][:4]), ([0.0] * (n * n), [0] * (n * n)))
            for i, v in enumerate(row["window"]):
                if v is not None:
                    sums[i] += v
                    cnts[i] += 1
        years = sorted(acc)
        year = _year_of(when, years)
        sums, cnts = acc[year]
        r0, c0 = d["cell"]["row"] - n // 2, d["cell"]["col"] - n // 2
        feats = []
        for i in range(n * n):
            r, c = r0 + i // n, c0 + i % n
            value = round(sums[i] / cnts[i], 3) if cnts[i] else None
            feats.append(_feature(smap.cell_polygon(r, c), value, in_field=(i == n * n // 2), n_days=cnts[i]))
        return {
            "type": "FeatureCollection",
            "features": feats,
            "meta": _meta(
                "smap",
                kind="soil_moisture",
                date=f"{year}-05-31",
                dates=[f"{y}-05-31" for y in years],
                period="presowing",
                unit="m3/m3",
                legend={"min": 0.1, "max": 0.4},
                origin=res.origin,
            ),
        }
    # запасной вариант: модельная влажность корнеобитаемого слоя из NASA POWER (одна ячейка ~50 км)
    pres = await SOURCES["power"].fetch(field, POWER_START, date.today())
    if not pres.ok:
        raise LayerError("soil moisture data is not available")
    gwet = _gwet(pres.data, months)
    years = sorted(gwet)
    year = _year_of(when, years)
    return {
        "type": "FeatureCollection",
        "features": [_feature(_power_cell(pres.data["lat"], pres.data["lon"]), gwet[year], in_field=True)],
        "meta": _meta(
            "power",
            kind="soil_moisture",
            date=f"{year}-05-31",
            dates=[f"{y}-05-31" for y in years],
            period="presowing",
            unit="0-1",
            legend={"min": 0.4, "max": 1.0},
            origin=pres.origin,
            fallback_for="smap",
        ),
    }


def _gwet(power_data: dict, months: list[int]) -> dict[int, float]:
    from ..analytics.moisture import gwet_presowing_by_year

    return {y: v for y, v in gwet_presowing_by_year(climate.daily_frame(power_data), months).items() if y >= 2000}


def _power_cell(lat: float, lon: float) -> list[list[float]]:
    lat_c = round(lat / POWER_DLAT) * POWER_DLAT
    lon_c = round((lon + 180) / POWER_DLON) * POWER_DLON - 180
    y0, y1 = lat_c - POWER_DLAT / 2, lat_c + POWER_DLAT / 2
    x0, x1 = lon_c - POWER_DLON / 2, lon_c + POWER_DLON / 2
    return [[x0, y1], [x1, y1], [x1, y0], [x0, y0], [x0, y1]]


async def precip_layer(field: Field, when: str | None) -> dict:
    res = await SOURCES["power"].fetch(field, POWER_START, date.today())
    if not res.ok:
        raise LayerError("precipitation data is not available")
    season = climate.season_precip_by_year(climate.daily_frame(res.data), get_rules().model["season"]["months"])
    years = [y for y in sorted(season) if y >= 2000]
    year = _year_of(when, years)
    return {
        "type": "FeatureCollection",
        "features": [_feature(_power_cell(res.data["lat"], res.data["lon"]), season[year], in_field=True)],
        "meta": _meta(
            "power",
            kind="precip",
            date=f"{year}-08-31",
            dates=[f"{y}-08-31" for y in years],
            period="season",
            unit="mm",
            legend={"min": 50, "max": 350},
            origin=res.origin,
        ),
    }


async def ndvi_anomaly_layer(field: Field, when: str | None) -> dict:
    """Отклонение NDVI выбранного композита от медианы того же композита (тот же день года)
    за все сезоны, для которых сохранены пиксельные растры (до 6 последних)."""
    base = await ndvi_layer(field, when)
    res = SOURCES["modis"].read_cached(field, MODIS_START, date.today())
    rasters = res.data["rasters"]
    chosen = base["meta"]["date"]
    doy = date.fromisoformat(chosen).timetuple().tm_yday
    peers = [d for d in rasters if d != chosen and abs(date.fromisoformat(d).timetuple().tm_yday - doy) <= 8]
    scale = res.data.get("ndvi_scale", 0.0001)
    feats = []
    for i, f in enumerate(base["features"]):
        v = rasters[chosen][i]
        others = [rasters[d][i] for d in peers if rasters[d][i] is not None]
        anomaly = None
        if v is not None and len(others) >= 2:
            anomaly = round((v - float(np.median(others))) * scale, 3)
        feats.append({**f, "properties": {**f["properties"], "value": anomaly}})
    meta = {**base["meta"], "kind": "ndvi_anomaly", "unit": "ΔNDVI", "legend": {"min": -0.2, "max": 0.2},
            "reference_dates": sorted(peers), "diverging": True}
    return {"type": "FeatureCollection", "features": feats, "meta": meta}


def field_summary(layer: dict) -> dict:
    """Среднее значение слоя по ячейкам внутри поля и честная оговорка о разрешении."""
    inside = [f["properties"]["value"] for f in layer["features"] if f["properties"].get("in_field")]
    vals = [v for v in inside if v is not None]
    res = layer["meta"].get("resolution_m") or 0
    return {
        "field_mean": round(sum(vals) / len(vals), 3) if vals else None,
        "cells_in_field": len(inside),
        "cells_with_data": len(vals),
        "coarser_than_field": res >= 1000,
    }


async def build_layer_for_field(kind: str, field: Field, when: str | None) -> dict:
    if kind == "ndvi":
        layer = await ndvi_layer(field, when)
    elif kind == "ndvi_anomaly":
        layer = await ndvi_anomaly_layer(field, when)
    elif kind == "soil_moisture":
        layer = await soil_moisture_layer(field, when)
    elif kind == "precip":
        layer = await precip_layer(field, when)
    else:
        raise LayerError(f"unknown layer '{kind}'")
    layer["meta"]["summary"] = field_summary(layer)
    return layer


async def build_layer(kind: str, bbox: tuple[float, float, float, float], when: str | None) -> dict:
    field = field_for_bbox(bbox)
    return await build_layer_for_field(kind, field, when)

