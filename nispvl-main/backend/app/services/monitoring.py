"""Мониторинг поля по уже загруженным рядам: помесячный климат и аномалии, NDVI, влажность почвы,
история сезонов, оценка рисков и пригодность культур.

Ничего не прогнозируется: все показатели — исторические наблюдения (спутник), реанализ (NASA POWER)
или результаты модели; тип указывается у каждого значения (поле ``kind``).
"""
from __future__ import annotations

import math
import statistics
from datetime import date

import numpy as np
import pandas as pd

from ..analytics import climate, moisture
from ..data_sources.registry import SOURCES, source_catalog
from ..geometry import parse_field
from ..model import rotation
from ..model.rules import Rules, get_rules
from .analysis import MODIS_START, POWER_START, SMAP_START, analyze

BASELINE = (1991, 2020)


def _r(x, n=1):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


async def load(geometry: dict, region: str, rules: Rules | None = None):
    """Анализ поля + сырые ряды источников (только из демо/кэша, кроме POWER)."""
    rules = rules or get_rules()
    analysis = await analyze(geometry, region, start_jobs=True, rules=rules)
    field = parse_field(geometry)
    today = date.today()
    power = await SOURCES["power"].fetch(field, POWER_START, today)
    modis = SOURCES["modis"].read_cached(field, MODIS_START, today)
    smap = SOURCES["smap"].read_cached(field, SMAP_START, today)
    df = climate.daily_frame(power.data)
    return analysis, df, (modis.data if modis else None), (smap.data if smap else None), power


def source_meta(source_id: str, origin: str | None) -> dict:
    cat = source_catalog()[source_id]
    return {"id": source_id, "title": cat["title"], "resolution_m": cat.get("resolution_m"), "origin": origin,
            "spatial_resolution": cat["spatial_resolution"], "provenance": cat["provenance"]}


# ---------------------------------------------------------------- помесячный климат
def monthly_climate(df: pd.DataFrame, hot_c: float) -> pd.DataFrame:
    g = df.resample("MS")
    m = pd.DataFrame({
        "precip_mm": g["PRECTOTCORR"].sum(min_count=1),
        "t_mean": g["T2M"].mean(),
        "t_max_mean": g["T2M_MAX"].mean(),
        "t_min_mean": g["T2M_MIN"].mean(),
        "hot_days": (df["T2M_MAX"] >= hot_c).resample("MS").sum(),
        "gwetroot": g["GWETROOT"].mean() if "GWETROOT" in df else np.nan,
        "n_days": g["PRECTOTCORR"].count(),
    })
    m["days_in_month"] = m.index.days_in_month
    return m[m["n_days"] >= 0.9 * m["days_in_month"]]


def climate_timeseries(df: pd.DataFrame, start: str, end: str, hot_c: float) -> dict:
    m = monthly_climate(df, hot_c)
    base = m[(m.index.year >= BASELINE[0]) & (m.index.year <= BASELINE[1])]
    normals = {}
    for month, grp in base.groupby(base.index.month):
        normals[int(month)] = {
            "precip_mm": float(grp["precip_mm"].mean()), "precip_sd": float(grp["precip_mm"].std(ddof=1)),
            "t_mean": float(grp["t_mean"].mean()), "t_sd": float(grp["t_mean"].std(ddof=1)),
            "hot_days": float(grp["hot_days"].mean()),
        }
    sel = m[(m.index >= pd.Timestamp(start)) & (m.index <= pd.Timestamp(end) + pd.offsets.MonthEnd(0))]
    rows = []
    for ts, r in sel.iterrows():
        n = normals.get(ts.month, {})
        pn, tn = n.get("precip_mm"), n.get("t_mean")
        rows.append({
            "month": ts.strftime("%Y-%m"),
            "precip_mm": _r(r["precip_mm"]),
            "precip_normal_mm": _r(pn),
            "precip_pct_of_normal": _r(100 * r["precip_mm"] / pn, 0) if pn else None,
            "t_mean": _r(r["t_mean"]),
            "t_normal": _r(tn),
            "t_anomaly": _r(r["t_mean"] - tn) if tn is not None else None,
            "t_max_mean": _r(r["t_max_mean"]),
            "hot_days": int(r["hot_days"]),
            "gwetroot": _r(r["gwetroot"], 3),
        })
    return {"months": rows, "normals": {k: {kk: _r(vv, 2) for kk, vv in v.items()} for k, v in normals.items()},
            "baseline": list(BASELINE), "available": [m.index.min().strftime("%Y-%m"), m.index.max().strftime("%Y-%m")]}


# ---------------------------------------------------------------- NDVI
def _doy(d: str) -> int:
    return date.fromisoformat(d).timetuple().tm_yday


def ndvi_climatology(series: list[dict], min_valid: float) -> dict[int, dict]:
    """Медиана и P10–P90 NDVI по композитам с одинаковым днём года (±8 дней) по всем годам."""
    by: dict[int, list[float]] = {}
    for r in series:
        if r.get("ndvi") is None or r.get("valid_fraction", 0) < min_valid:
            continue
        key = int(round(_doy(r["date"]) / 16))
        by.setdefault(key, []).append(r["ndvi"])
    return {k: {"median": float(np.median(v)), "p10": float(np.percentile(v, 10)), "p90": float(np.percentile(v, 90)), "n": len(v)}
            for k, v in by.items() if len(v) >= 3}


def ndvi_timeseries(modis: dict | None, start: str, end: str, min_valid: float) -> dict:
    if not modis:
        return {"available": False, "composites": []}
    clim = ndvi_climatology(modis["series"], min_valid)
    rows = []
    for r in modis["series"]:
        if not (start <= r["date"][:7] <= end):
            continue
        c = clim.get(int(round(_doy(r["date"]) / 16)))
        ok = r.get("ndvi") is not None and r.get("valid_fraction", 0) >= min_valid
        rows.append({
            "date": r["date"], "ndvi": r["ndvi"] if ok else None, "valid_fraction": r.get("valid_fraction"),
            "median": _r(c["median"], 3) if c else None, "p10": _r(c["p10"], 3) if c else None, "p90": _r(c["p90"], 3) if c else None,
            "anomaly": _r(r["ndvi"] - c["median"], 3) if (ok and c) else None,
        })
    return {"available": True, "composites": rows, "n_field_pixels": modis.get("n_field_pixels"),
            "season_doy": modis.get("season_doy"), "product": modis.get("product")}


def smap_timeseries(smap: dict | None, start: str, end: str) -> dict:
    if not smap:
        return {"available": False, "days": []}
    days = [{"date": r["date"], "sm": r["sm"]} for r in smap["daily"] if start <= r["date"][:7] <= end and r["sm"] is not None]
    return {"available": True, "days": days, "months": smap.get("months"), "cell": smap.get("cell"), "unit": "m3/m3"}


async def monitoring(geometry: dict, region: str, start: str | None, end: str | None) -> dict:
    rules = get_rules()
    analysis, df, modis, smap, power = await load(geometry, region, rules)
    hot_c = float(rules.model["risk"]["hot_day_threshold_c"].value)
    last = df.index.max()
    end = end or (last - pd.offsets.MonthBegin(1)).strftime("%Y-%m")
    start = start or f"{int(end[:4]) - 4}-01"
    if start > end:
        raise ValueError("start must be before end")
    a = analysis.response
    return {
        "range": {"start": start, "end": end},
        "climate": climate_timeseries(df, start, end, hot_c),
        "ndvi": ndvi_timeseries(modis, start, end, float(rules.model["ndvi_trend"]["min_valid_fraction"])),
        "soil_moisture": smap_timeseries(smap, start, end),
        "sources": {
            "power": source_meta("power", power.origin),
            "modis": source_meta("modis", a["ndvi"].get("origin")),
            "smap": source_meta("smap", a["soil_moisture"].get("origin")),
            "gpm": source_meta("gpm", None) | {"state": "not_available"},
        },
        "jobs": [s for s in a["sources"] if s.get("status") == "pending"],
        "hot_day_threshold_c": hot_c,
        "kind": {"climate": "reanalysis", "ndvi": "observation", "soil_moisture": "observation"},
    }


# ---------------------------------------------------------------- история сезонов
async def seasons(geometry: dict, region: str) -> dict:
    rules = get_rules()
    analysis, df, modis, smap, _ = await load(geometry, region, rules)
    return seasons_from(rules, analysis, df, modis, smap)


def seasons_from(rules: Rules, analysis, df: pd.DataFrame, modis: dict | None, smap: dict | None) -> dict:
    a = analysis.response
    model = rules.model
    months = model["season"]["months"]
    hot_c = float(model["risk"]["hot_day_threshold_c"].value)
    min_valid = float(model["ndvi_trend"]["min_valid_fraction"])
    temps = climate.season_temperature_by_year(df, months)
    season_df = df[df.index.month.isin(months)]
    hot = (season_df["T2M_MAX"] >= hot_c).groupby(season_df.index.year).sum()
    base_years = [y for y in temps if BASELINE[0] <= y <= BASELINE[1]]
    t_mean = statistics.mean(temps[y]["t_mean"] for y in base_years)
    t_sd = statistics.stdev(temps[y]["t_mean"] for y in base_years)
    hot_mean = statistics.mean(float(hot.get(y, 0)) for y in base_years)
    dry = {r["year"]: r for r in a["drought"]["years"]}

    ndvi_by_year: dict[int, list[dict]] = {}
    for r in (modis or {}).get("series", []):
        if r.get("ndvi") is not None and r.get("valid_fraction", 0) >= min_valid:
            ndvi_by_year.setdefault(int(r["date"][:4]), []).append(r)
    smap_years = moisture.smap_presowing_by_year(smap, model["presowing"]["months"])
    smap_med = statistics.median(v["mean"] for v in smap_years.values()) if len(smap_years) >= 3 else None
    gwet = moisture.gwet_presowing_by_year(df, model["presowing"]["months"])

    rows = []
    for y in sorted(dry):
        nd = ndvi_by_year.get(y, [])
        nd_ok = len(nd) >= 5
        peak = max(nd, key=lambda r: r["ndvi"]) if nd_ok else None
        sm = smap_years.get(y)
        rows.append({
            "year": y,
            "precip_mm": dry[y]["precip_mm"], "precip_anomaly_z": dry[y]["anomaly"], "is_dry": dry[y]["is_dry"],
            "t_mean": temps.get(y, {}).get("t_mean"),
            "t_anomaly": _r(temps[y]["t_mean"] - t_mean) if y in temps else None,
            "t_anomaly_z": _r((temps[y]["t_mean"] - t_mean) / t_sd, 2) if y in temps else None,
            "hot_days": int(hot.get(y, 0)) if y in temps else None,
            "ndvi_max": peak["ndvi"] if peak else None, "ndvi_max_date": peak["date"] if peak else None,
            "ndvi_mean": _r(statistics.mean(r["ndvi"] for r in nd), 3) if nd_ok else None,
            "n_composites": len(nd),
            "smap_spring": sm["mean"] if sm else None,
            "smap_ratio": _r(sm["mean"] / smap_med, 2) if (sm and smap_med) else None,
            "gwet_spring": gwet.get(y),
        })
    window = [r for r in rows if r["year"] >= a["drought"]["window"]["from"]] if a["drought"]["window"] else rows

    def avg(key):
        vals = [r[key] for r in window if r[key] is not None]
        return _r(statistics.mean(vals), 3) if vals else None

    curves = {}
    for y, nd in ndvi_by_year.items():
        curves[str(y)] = [{"doy": _doy(r["date"]), "date": r["date"], "ndvi": r["ndvi"]} for r in sorted(nd, key=lambda r: r["date"])]
    clim = ndvi_climatology((modis or {}).get("series", []), min_valid)
    clim_curve = [{"doy": k * 16, "median": _r(v["median"], 3), "p10": _r(v["p10"], 3), "p90": _r(v["p90"], 3)} for k, v in sorted(clim.items())]
    return {
        "years": rows,
        "window_averages": {k: avg(k) for k in ("precip_mm", "t_mean", "hot_days", "ndvi_max", "ndvi_mean", "smap_spring")},
        "baseline": {"years": list(BASELINE), "t_mean": _r(t_mean), "t_sd": _r(t_sd, 2), "hot_days": _r(hot_mean),
                     "precip_mean": a["drought"]["definition"]["baseline_mean_mm"], "precip_sd": a["drought"]["definition"]["baseline_std_mm"]},
        "ndvi_curves": curves,
        "ndvi_climatology": clim_curve,
        "ndvi_trend": a["ndvi"].get("trend"),
        "hot_day_threshold_c": hot_c,
        "kind": {"precip": "reanalysis", "temperature": "reanalysis", "ndvi": "observation", "smap": "observation", "gwet": "reanalysis"},
        "caveat": "ndvi_not_yield",
    }


# ---------------------------------------------------------------- риски
LEVELS = ("low", "moderate", "high")


def _level(value: float | None, moderate: float, high: float, lower_is_worse: bool) -> str:
    if value is None:
        return "unknown"
    if lower_is_worse:
        return "high" if value <= high else "moderate" if value <= moderate else "low"
    return "high" if value >= high else "moderate" if value >= moderate else "low"


async def risk(geometry: dict, region: str) -> dict:
    rules = get_rules()
    rk = {k: float(p.value) for k, p in rules.model["risk"].items()}
    analysis, df, modis, smap, _ = await load(geometry, region, rules)
    s = seasons_from(rules, analysis, df, modis, smap)
    a = analysis.response
    years = s["years"]
    latest = years[-1]
    items = []

    # 1. осадки последнего полного сезона
    items.append({
        "id": "precip_season", "kind": "reanalysis", "source": "power", "period": f"{latest['year']}-05/{latest['year']}-08",
        "value": latest["precip_mm"], "unit": "mm", "reference": s["baseline"]["precip_mean"], "z": latest["precip_anomaly_z"],
        "level": _level(latest["precip_anomaly_z"], rk["precip_anomaly_moderate"], rk["precip_anomaly_high"], True),
    })
    # 2. температура сезона
    items.append({
        "id": "temperature_season", "kind": "reanalysis", "source": "power", "period": f"{latest['year']}-05/{latest['year']}-08",
        "value": latest["t_mean"], "unit": "°C", "reference": s["baseline"]["t_mean"], "z": latest["t_anomaly_z"],
        "level": _level(latest["t_anomaly_z"], rk["temperature_anomaly_moderate"], rk["temperature_anomaly_high"], False),
    })
    # 3. жаркие дни
    hot_vals = [r["hot_days"] for r in years if r["hot_days"] is not None and BASELINE[0] <= r["year"] <= BASELINE[1]]
    hot_sd = statistics.stdev(hot_vals) if len(hot_vals) > 2 else 0
    hot_z = (latest["hot_days"] - s["baseline"]["hot_days"]) / hot_sd if hot_sd else None
    items.append({
        "id": "heat_days", "kind": "reanalysis", "source": "power", "period": f"{latest['year']}-05/{latest['year']}-08",
        "value": latest["hot_days"], "unit": "days", "reference": s["baseline"]["hot_days"], "z": _r(hot_z, 2),
        "threshold_c": rk["hot_day_threshold_c"],
        "level": _level(hot_z, rk["temperature_anomaly_moderate"], rk["temperature_anomaly_high"], False),
    })
    # 4. вегетация (NDVI) последнего сезона с данными
    nd_years = [r for r in years if r["ndvi_max"] is not None]
    if len(nd_years) >= 8:
        last_nd = nd_years[-1]
        vals = [r["ndvi_max"] for r in nd_years]
        pct = 100 * sum(v < last_nd["ndvi_max"] for v in vals) / len(vals)
        items.append({
            "id": "vegetation", "kind": "observation", "source": "modis", "period": last_nd["ndvi_max_date"],
            "value": last_nd["ndvi_max"], "unit": "NDVI", "reference": _r(statistics.median(vals), 3), "percentile": _r(pct, 0),
            "level": _level(pct, rk["ndvi_percentile_moderate"], rk["ndvi_percentile_high"], True),
        })
    else:
        items.append({"id": "vegetation", "kind": "observation", "source": "modis", "level": "unknown",
                      "state": a["ndvi"]["state"].get("status")})
    # 5. влажность почвы перед посевом
    sm_years = [r for r in years if r["smap_ratio"] is not None]
    if sm_years:
        last_sm = sm_years[-1]
        items.append({
            "id": "soil_moisture", "kind": "observation", "source": "smap", "period": f"{last_sm['year']}-04/{last_sm['year']}-05",
            "value": last_sm["smap_spring"], "unit": "m3/m3", "ratio": last_sm["smap_ratio"],
            "level": _level(last_sm["smap_ratio"], rk["moisture_ratio_moderate"], rk["moisture_ratio_high"], True),
        })
    else:
        gw = [r for r in years if r["gwet_spring"] is not None]
        med = statistics.median(r["gwet_spring"] for r in gw) if gw else None
        ratio = gw[-1]["gwet_spring"] / med if gw and med else None
        items.append({
            "id": "soil_moisture", "kind": "reanalysis", "source": "power", "period": f"{gw[-1]['year']}-04/{gw[-1]['year']}-05" if gw else None,
            "value": gw[-1]["gwet_spring"] if gw else None, "unit": "0-1", "ratio": _r(ratio, 2), "fallback_for": "smap",
            "level": _level(ratio, rk["moisture_ratio_moderate"], rk["moisture_ratio_high"], True),
        })
    # 6. частота засух
    d = a["drought"]
    items.append({
        "id": "drought_frequency", "kind": "statistic", "source": "power",
        "period": f"{d['window']['from']}/{d['window']['to']}" if d["window"] else None,
        "value": d["share"], "unit": "share", "every_nth": d["every_nth"], "dry_years": d["dry_years"],
        "level": _level(d["share"], rk["drought_share_moderate"], rk["drought_share_high"], False),
    })
    # 7. модельная чувствительность пшеницы к засухе
    cond = analysis.conditions
    w_ref = cond.p_season_ref + cond.stock_ref
    coef_n = rotation.moisture_coefficient(rules, "wheat", cond.p_season_normal + cond.stock_normal, w_ref)
    coef_d = rotation.moisture_coefficient(rules, "wheat", cond.p_season_dry + cond.stock_dry, w_ref)
    loss = 100 * (1 - coef_d / coef_n) if coef_n else None
    items.append({
        "id": "model_drought_exposure", "kind": "model", "source": "model", "period": str(cond.dry_year),
        "value": _r(loss), "unit": "%", "crop": "wheat",
        "level": _level(loss, rk["model_loss_moderate"], rk["model_loss_high"], False),
    })
    order = {"unknown": -1, "low": 0, "moderate": 1, "high": 2}
    overall = max((i["level"] for i in items), key=lambda x: order[x])
    thresholds = {k: p.ref() for k, p in rules.model["risk"].items()}
    return {"latest_season": latest["year"], "overall": overall, "items": items, "thresholds": thresholds,
            "warnings": a["warnings"]}


# ---------------------------------------------------------------- пригодность культур
async def suitability(geometry: dict, region: str, history: list[dict]) -> dict:
    """Общая пригодность культур для поля по правилам модели. Не валидированная рекомендация."""
    rules = get_rules()
    sc = {k: float(p.value) for k, p in rules.model["suitability"].items()}
    analysis, df, *_ = await load(geometry, region, rules)
    cond = analysis.conditions
    hist = [h["crop"] for h in sorted(history, key=lambda h: h["year"])]
    prev = hist[-1] if hist else None
    w_ref = cond.p_season_ref + cond.stock_ref
    w_norm = cond.p_season_normal + cond.stock_normal
    w_dry = cond.p_season_dry + cond.stock_dry
    start_year = rotation.default_start_year()
    crops = []
    for cid, crop in rules.crops.items():
        if crop["group"] == "fallow":
            continue
        sim = rotation.simulate(rules, cond, [cid], hist, 3, start_year)["years"][0]
        coef = rotation.moisture_coefficient(rules, cid, w_norm, w_ref)
        loss = sim["yield_loss_dry_pct"]
        flags = []
        if coef < sc["moisture_coef_caution"]:
            flags.append("moisture")
        if sim["predecessor_effect_pct"] <= sc["predecessor_caution_pct"]:
            flags.append("predecessor")
        if sim["monoculture"]:
            flags.append("monoculture")
        if loss >= sc["drought_loss_caution_pct"]:
            flags.append("drought")
        if sim["income_kzt_ha"] <= 0:
            flags.append("margin")
        params = [crop[k] for k in ("base_yield_t_ha", "price_kzt_t", "cost_kzt_ha", "water_need_mm", "ky")]
        conf = rotation.parameter_confidence([p.ref() for p in params])
        crops.append({
            "crop": cid, "group": crop["group"],
            "category": "favourable" if not flags else "conditional" if len(flags) == 1 else "limited",
            "flags": flags,
            "water_need_mm": crop["water_need_mm"].value, "water_available_mm": round(w_norm, 1),
            "moisture_coef": round(coef, 3), "ky": crop["ky"].value,
            "drought_loss_pct": loss, "predecessor": prev, "predecessor_effect_pct": sim["predecessor_effect_pct"],
            "predecessor_rule": sim["predecessor_rule"], "monoculture": sim["monoculture"],
            "yield_t_ha": sim["yield_t_ha"], "gross_margin_kzt_ha": sim["income_kzt_ha"],
            "confidence": conf,
        })
    order = {"favourable": 0, "conditional": 1, "limited": 2}
    crops.sort(key=lambda c: (order[c["category"]], -c["gross_margin_kzt_ha"]))
    # тепловой контекст из POWER: сумма активных температур выше 5 °C за май–сентябрь (средняя за 10 лет)
    recent = df[(df.index.year >= df.index.max().year - 10) & (df.index.month.isin([5, 6, 7, 8, 9]))]
    gdd = (recent["T2M"] - 5).clip(lower=0).groupby(recent.index.year).sum()
    gdd = gdd[gdd.index < df.index.max().year] if df.index.max().month < 10 else gdd
    soil = analysis.response["soil"]["summary"]
    return {
        "crops": crops,
        "context": {
            "water_normal_mm": round(w_norm, 1), "water_dry_mm": round(w_dry, 1), "dry_year": cond.dry_year,
            "gdd5_may_sep_mean": _r(float(gdd.mean()), 0) if len(gdd) else None, "gdd_years": [int(gdd.index.min()), int(gdd.index.max())] if len(gdd) else None,
            "soil": soil["topsoil"] if soil else None, "predecessor": prev,
        },
        "thresholds": {k: p.ref() for k, p in rules.model["suitability"].items()},
        "scope": "general_model_based",
    }
