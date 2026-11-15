"""Анализ поля: данные источников -> климатическая сводка -> условия для модели."""
from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass
from datetime import date

from .. import jobs
from ..analytics import climate, moisture, ndvi_trend, soil_water
from ..config import get_settings
from ..data_sources.base import DataSource, DataWarning, SourceResult, is_demo_field
from ..data_sources.registry import SOURCES, source_catalog
from ..geometry import Field, parse_field
from ..model.rotation import FieldConditions
from ..model.rules import Rules, get_rules

POWER_START = date(1981, 1, 1)
MODIS_START = date(2000, 1, 1)
SMAP_START = date(2015, 1, 1)
#: выше этого содержания гумуса в слое 0–30 см (для пашни Северного Казахстана) значение SoilGrids
#: помечается как подозрительное — нужна проверка агрохимическим анализом
SUSPICIOUS_HUMUS_PCT = 8.0


class AnalysisError(RuntimeError):
    """Расчёт невозможен (нет климатических данных)."""


@dataclass
class Analysis:
    field: Field
    response: dict
    conditions: FieldConditions


def _slow_source(src: DataSource, field: Field, start: date, end: date, start_jobs: bool) -> tuple[SourceResult | None, dict]:
    """Медленный источник: отдаём демо/кэш сразу, иначе запускаем фоновую задачу."""
    hit = src.read_cached(field, start, end)
    if hit is not None:
        return hit, {"status": "ready", "origin": hit.origin}
    if not src.enabled:
        return None, {"status": "not_configured"}
    if get_settings().offline:
        return None, {"status": "unavailable", "reason": "offline"}
    job_id = f"{src.id}:{src.cache_key(field, start, end)}"
    job = jobs.get_job(job_id)
    if job is None and not start_jobs:
        return None, {"status": "not_started"}
    if job is None or job.status == "failed" and start_jobs:
        job = jobs.start_job(job_id, src.id, lambda progress: src.fetch(field, start, end, progress=progress))
    if job.status == "failed":
        return None, {"status": "unavailable", "reason": job.error, "job": job.as_dict()}
    if job.status == "done":  # задача завершилась между проверками: данные уже в кэше
        hit = src.read_cached(field, start, end)
        if hit is not None:
            return hit, {"status": "ready", "origin": hit.origin}
        # результат неполный и в кэш не попал: считаем источник недоступным
        return None, {"status": "unavailable", "reason": "partial", "job": job.as_dict()}
    return None, {"status": "pending", "job": job.as_dict()}


def _resolution(source_id: str, lang_keys: tuple[str, ...] = ("ru", "kk", "en")) -> dict:
    meta = source_catalog()[source_id]
    return {
        "source": source_id,
        "title": meta["title"],
        "resolution_m": meta.get("resolution_m"),
        "spatial_resolution": {k: meta["spatial_resolution"][k] for k in lang_keys},
        "provenance": {k: meta["provenance"][k] for k in lang_keys},
        "temporal_coverage": {k: meta["temporal_coverage"][k] for k in lang_keys},
    }


async def analyze(
    geometry: dict,
    region: str,
    *,
    start_jobs: bool = True,
    rules: Rules | None = None,
    stress_year: int | None = None,
    today: date | None = None,
) -> Analysis:
    rules = rules or get_rules()
    region_rule = rules.region(region)
    field = parse_field(geometry)
    today = today or date.today()
    model = rules.model
    warnings: list[DataWarning] = []

    # ---- быстрые источники: климат и почва ---------------------------------
    power_res, soil_res = await asyncio.gather(
        SOURCES["power"].fetch(field, POWER_START, today),
        SOURCES["soilgrids"].fetch(field, POWER_START, today),
    )
    warnings += power_res.warnings + soil_res.warnings
    if not power_res.ok:
        raise AnalysisError("climate data (NASA POWER) is unavailable and no cached copy exists")

    df = climate.daily_frame(power_res.data)
    season_months = model["season"]["months"]
    season = climate.season_precip_by_year(df, season_months)
    if len(season) < 10:
        raise AnalysisError("climate series is too short")
    offseason = climate.offseason_precip_by_year(df, model["offseason"]["months"])
    drought = climate.drought_analysis(season, model["drought"])
    window_years = [r["year"] for r in drought["years"]][-int(model["drought"]["window_years"]) :]
    p_normal = statistics.median(season[y] for y in window_years)

    soil = soil_water.soil_summary(soil_res.data, int(model["water"]["root_zone_cm"])) if soil_res.ok else None
    awc = soil["awc_mm"] if soil else None

    # ---- медленные источники: SMAP и NDVI ----------------------------------
    smap_res, smap_state = _slow_source(SOURCES["smap"], field, SMAP_START, today, start_jobs)
    modis_res, modis_state = _slow_source(SOURCES["modis"], field, MODIS_START, today, start_jobs)

    smap_by_year = moisture.smap_presowing_by_year(smap_res.data if smap_res else None, model["presowing"]["months"])
    norm: float = float(region_rule["presowing_stock_norm_mm"].value)
    stock = moisture.presowing_stock(
        norm, offseason, smap_by_year, awc, tuple(model["water"]["smap_ratio_bounds"]), window_years
    )
    stock_by_year = {r["year"]: r for r in stock["by_year"]}

    # ---- засушливый год для стресс-теста -----------------------------------
    preferred = int(model["stress_test"]["default_year"].value)
    dry_set = {r["year"] for r in drought["years"] if r["is_dry"]}
    if stress_year is not None:
        if stress_year not in dry_set:
            raise ValueError(f"stress_year {stress_year} is not a dry year for this field: {sorted(dry_set)}")
        dry_year, dry_reason = stress_year, "user_selected"
    elif preferred in dry_set and preferred in stock_by_year:
        dry_year, dry_reason = preferred, "default_year"
    else:
        dry_year, dry_reason = drought["driest_year"], "driest_year"
    p_dry = season[dry_year]
    stock_dry = stock_by_year.get(dry_year, {}).get("stock_mm", stock["normal_stock_mm"])

    # ---- опорные значения области -------------------------------------------
    p_ref = region_rule["reference_season_precip_mm"].value
    if p_ref is None:
        p_ref = p_normal
        warnings.append(DataWarning("region_reference_missing", "rules", {"region": region}))

    conditions = FieldConditions(
        region=region,
        area_ha=round(field.area_ha, 2),
        p_season_normal=round(p_normal, 1),
        stock_normal=stock["normal_stock_mm"],
        p_season_dry=p_dry,
        stock_dry=stock_dry,
        dry_year=dry_year,
        p_season_ref=float(p_ref),
        stock_ref=norm,
        awc_mm=awc,
        moisture_basis="smap" if stock["uses_smap"] else "power",
    )

    # ---- NDVI -----------------------------------------------------------------
    ndvi: dict = {"state": modis_state}
    if modis_res is not None:
        d = modis_res.data
        trend = ndvi_trend.ndvi_trend(d["series"], model["ndvi_trend"])
        ndvi.update(
            {
                "series": d["series"],
                "trend": trend,
                "n_field_pixels": d["n_field_pixels"],
                "missing_years": d.get("missing_years", []),
                "raster_dates": sorted(d.get("rasters", {}).keys()),
                "origin": modis_res.origin,
            }
        )
        if d["n_field_pixels"] < 4:
            warnings.append(DataWarning("ndvi_few_pixels", "modis", {"pixels": d["n_field_pixels"]}))
        if d.get("missing_years"):
            warnings.append(DataWarning("ndvi_missing_years", "modis", {"years": d["missing_years"]}))
    elif modis_state["status"] == "unavailable":
        warnings.append(DataWarning("source_unavailable", "modis", {"detail": modis_state.get("reason") or ""}))

    # ---- влажность почвы -------------------------------------------------------
    gwet = moisture.gwet_presowing_by_year(df, model["presowing"]["months"])
    soil_moisture = {
        "state": smap_state,
        "basis": conditions.moisture_basis,
        "smap_by_year": [{"year": y, **v} for y, v in smap_by_year.items()],
        "power_gwetroot_by_year": [{"year": y, "value": v} for y, v in gwet.items() if y >= 2000],
        "stock": stock,
        "cell": (smap_res.data or {}).get("cell") if smap_res else None,
        "origin": smap_res.origin if smap_res else None,
    }
    if smap_state["status"] == "not_configured":
        warnings.append(DataWarning("smap_not_configured", "smap"))
    elif smap_state["status"] == "unavailable":
        warnings.append(DataWarning("source_unavailable", "smap", {"detail": smap_state.get("reason") or ""}))

    # ---- постоянные оговорки о разрешении данных --------------------------------
    warnings.append(DataWarning("resolution_power", "power"))
    if stock["uses_smap"]:
        warnings.append(DataWarning("resolution_smap", "smap"))
    if soil is not None:
        warnings.append(DataWarning("soil_is_model_map", "soilgrids"))
        humus = soil["topsoil"].get("humus_pct")
        if humus is not None and humus > SUSPICIOUS_HUMUS_PCT:
            # SoilGrids в верхних сантиметрах степных почв нередко завышает органический углерод
            warnings.append(DataWarning("soil_humus_suspicious", "soilgrids", {"humus_pct": humus}))
    else:
        warnings.append(DataWarning("soil_missing_awc", "soilgrids"))

    temps = climate.season_temperature_by_year(df, season_months)
    minx, miny, maxx, maxy = field.bbox
    response = {
        "field": {
            "area_ha": round(field.area_ha, 1),
            "centroid": {"lat": round(field.centroid_lat, 5), "lon": round(field.centroid_lon, 5)},
            "bbox": [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)],
            "region": region,
            "region_name": region_rule["name"],
            "is_demo": is_demo_field(field),
            "geometry": field.geojson(),
        },
        "climate": {
            "origin": power_res.origin,
            "fetched_at": power_res.fetched_at,
            "series_from": int(df.index.min().year),
            "series_to": df.index.max().strftime("%Y-%m-%d"),
            "season_months": season_months,
            "season_precip": [{"year": y, "precip_mm": v, **temps.get(y, {})} for y, v in season.items()],
            "normal_precip_mm": round(p_normal, 1),
            "monthly_normals": climate.monthly_normals(df, tuple(model["drought"]["baseline_years"])),
            "elevation_m": power_res.data.get("elevation_m"),
        },
        "drought": {**drought, "stress_year": dry_year, "stress_year_reason": dry_reason},
        "ndvi": ndvi,
        "soil_moisture": soil_moisture,
        "soil": {"origin": soil_res.origin, "summary": soil, "fetched_at": soil_res.fetched_at},
        "conditions": conditions.as_dict(),
        "region_reference": {
            "season_precip_mm": float(p_ref),
            "presowing_stock_mm": norm,
            "rules": [region_rule["reference_season_precip_mm"].ref(), region_rule["presowing_stock_norm_mm"].ref()],
        },
        "resolutions": [_resolution(s) for s in ("power", "modis", "smap", "soilgrids")],
        "warnings": [w.as_dict() for w in warnings],
        "sources": [
            power_res.meta(),
            soil_res.meta(),
            {"source": "modis", "origin": modis_res.origin if modis_res else None, **modis_state},
            {"source": "smap", "origin": smap_res.origin if smap_res else None, **smap_state},
        ],
    }
    return Analysis(field=field, response=response, conditions=conditions)
