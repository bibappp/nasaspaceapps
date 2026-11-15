"""«Часы голой почвы»: месяц за месяцем — доля дней, когда на поле одновременно нет зелёного покрова
(открытая почва или стерня), дует эрозионный ветер и верхний слой почвы сухой.
NDVI не отличает стерню от открытой почвы, поэтому там, где стерня оставлена стоять, доля — верхняя оценка риска.
Пороги — ``backend/app/rules/erosion.yaml``, расчёт — ``app/analytics/bare_soil.py``.

Источники:
  * POWER — ветер (WS2M_MAX), снег (FRSNO, SNODP), GWETTOP, T2M_MIN; запрашивается сразу (≈ 2 с, затем кэш);
  * MODIS ``modis`` (сезон, DOY 129–273) и ``modis_shoulder`` (весна и осень, DOY 81–113 и 289–305) — фоновые задачи;
  * SMAP ``smap`` (апрель–май, только кэш) и ``smap_season`` (апрель–октябрь, фоновая задача, нужен Earthdata);
    в дни без SMAP сухость — по GWETTOP (``moisture_source`` месяца);
  * SoilGrids — влажность завядания слоя 0–5 см для порога SMAP.
Пока данных нет, месяц получает ``state: missing`` и ``missing_reason`` — никогда не 0.

Форма ответа — docs/contracts/bare_soil.example.json; менять можно только добавлением необязательных полей.
"""
from __future__ import annotations

import calendar
import math
from datetime import date

from ..analytics import bare_soil as bs
from ..analytics import scenario_exposure as se
from ..analytics import soil_water
from ..data_sources.base import DataWarning, SourceResult
from ..data_sources.registry import SOURCES
from ..data_sources.smap import CELL_M
from ..data_sources.smap import FIRST_DAY as SMAP_FIRST_DAY
from ..geometry import Field, parse_field
from ..model.rules import Rules, get_rules
from ..schemas import BareSoilOut
from .analysis import MODIS_START, POWER_START, SMAP_START, _slow_source
from .monitoring import source_meta

#: MOD13Q1 начинается 18.02.2000, поэтому 2000 год неполный; расчёт — с 2001 года.
MIN_YEAR = 2001
#: SMAP SPL3SMP_E доступен с 2015 года — разумное начало периода по умолчанию.
DEFAULT_START_YEAR = 2015

#: определение показателя; казахский текст требует вычитки носителем языка (как и весь интерфейс на kk)
DEFINITION = {
    "exposure": {
        "ru": "Доля дней месяца, когда одновременно: нет зелёного покрова (открытая почва или стерня), ветер "
              "эрозионный и верхний слой сухой. Если стерня оставлена стоять, это верхняя оценка риска.",
        "kk": "Айдағы күндердің үлесі: бір күнде жасыл жамылғы жоқ (ашық топырақ немесе аңыз), жел эрозиялық "
              "және беткі қабат құрғақ. Аңыз тік қалдырылса, бұл тәуекелдің жоғарғы бағасы.",
        "en": "Share of days in the month with no green cover (bare soil or stubble) AND erosive wind AND dry "
              "topsoil on the same day. Where stubble is left standing, this is an upper bound on the risk.",
    }
}


def resolve_period(start_year: int | None, end_year: int | None, today: date | None = None) -> tuple[int, int]:
    """Период по умолчанию 2015…текущий год; допустимо MIN_YEAR…текущий год, иначе ``ValueError`` (422)."""
    current = (today or date.today()).year
    start = DEFAULT_START_YEAR if start_year is None else start_year
    end = current if end_year is None else end_year
    for name, v in (("start_year", start), ("end_year", end)):
        if not MIN_YEAR <= v <= current:
            raise ValueError(f"{name} must be in {MIN_YEAR}..{current}")
    if start > end:
        raise ValueError("start_year must not exceed end_year")
    return start, end


#: ячейка POWER (метеопараметры MERRA-2), градусы широты x долготы
POWER_CELL_DEG = (0.5, 0.625)
KM_PER_DEG = 111.32
#: медленные источники: (id, начало ряда для ключа кэша, запускать ли фоновую задачу)
SLOW_SOURCES = (("modis", MODIS_START, True), ("modis_shoulder", MODIS_START, True),
                ("smap", SMAP_START, False), ("smap_season", SMAP_START, True))
#: какой источник MODIS покрывает какие дни (analytics.bare_soil.ndvi_coverage)
NDVI_COVERAGE = {"main": "modis", "shoulder": "modis_shoulder"}


def month_grid(start_year: int, end_year: int) -> list[dict]:
    """Все 12 месяцев каждого года периода без чисел (state: missing)."""
    return [
        {
            "year": y,
            "months": [
                {
                    "month": m,
                    "state": "missing",
                    "bare_days": None,
                    "erosive_wind_days": None,
                    "dry_days": None,
                    "joint_days": None,
                    "days_in_month": calendar.monthrange(y, m)[1],
                    "known_days": 0,
                    "exposure": None,
                    "moisture_source": None,
                    "quality": "missing",
                    "missing_reason": "no_weather",
                }
                for m in range(1, 13)
            ],
        }
        for y in range(start_year, end_year + 1)
    ]


def thresholds(rules: Rules) -> list[dict]:
    """Пороги контракта (ndvi_bare, erosive_wind_ms, dry_topsoil) — правила erosion.yaml."""
    out = []
    for cid, ref in rules.erosion["contract_thresholds"].items():
        group, key = ref.split(".")
        p = rules.erosion[group][key]
        out.append({"id": cid, "value": float(p.value), "unit": p.unit, "source": p.source_id, "status": p.status,
                    "evidence": p.evidence, "note": p.note})
    return out


def _wilting_point_0_5(soil: SourceResult | None) -> float | None:
    if soil is None or not soil.ok:
        return None
    summary = soil_water.soil_summary(soil.data)
    top = next((layer for layer in (summary or {}).get("layers", []) if layer["top_cm"] == 0), None)
    return None if top is None else float(top["wilting_point"])


def _power_cell_km2(lat: float) -> float:
    return POWER_CELL_DEG[0] * KM_PER_DEG * POWER_CELL_DEG[1] * KM_PER_DEG * math.cos(math.radians(lat))


def _job_entry(sid: str, state: dict) -> dict:
    return {"source": sid, "status": state["status"], "job": state.get("job")}


def conditions(power: SourceResult, soil: SourceResult | None, slow: dict[str, SourceResult | None], e: dict,
               start: int, end: int) -> dict:
    """Суточная таблица условий (снег, NDVI, ветер, сухость) с 1 января ``start`` по 31 декабря ``end``.
    Общая для «Часов голой почвы» и планировщика (дни без покрова в сценариях)."""
    df = bs.power_frame(power.data)
    snow = bs.power_snow(df, e)
    sm = bs.smap_days(*(slow[s].data if slow.get(s) else None for s in ("smap", "smap_season")))
    wp = _wilting_point_0_5(soil)
    factor = float(e["dry_topsoil"]["smap_wilting_point_factor"].value)
    smap_thr = factor * wp if wp is not None else float(e["dry_topsoil"]["smap_fallback_m3m3"].value)
    gw = bs.gwettop_threshold(df, sm, smap_thr, snow, e)
    modis_data = [slow[s].data for s in ("modis", "modis_shoulder") if slow.get(s) is not None]
    comps = bs.composites(modis_data, e)
    daily = bs.daily_conditions(df, comps, sm, smap_thr, gw["value"], e, date(start, 1, 1), date(end, 12, 31))
    return {"df": df, "daily": daily, "wp": wp, "smap_thr": smap_thr, "gw": gw}


async def planner_climate(field: Field, rules: Rules, *, today: date | None = None) -> dict:
    """Климатология поля для дней без покрова в сценариях планировщика (analytics.scenario_exposure).

    Период — как у «Часов» по умолчанию: DEFAULT_START_YEAR … последний полный год. Только кэш и демо-данные:
    фоновые загрузки не запускаются (их запускает вкладка «Часы»). Без ветра POWER — ``status: missing``."""
    e = rules.erosion
    today = today or date.today()
    years = range(DEFAULT_START_YEAR, today.year)
    power = await SOURCES["power"].fetch(field, POWER_START, today)
    wind_col = e["erosive_wind"]["power_parameter"]
    if not power.ok or power.origin == "fallback" or wind_col not in power.data.get("daily", {}):
        return se.missing_climate("no_weather", years)
    soil = await SOURCES["soilgrids"].fetch(field, POWER_START, today)
    slow = {sid: _slow_source(SOURCES[sid], field, t0, today, False)[0] for sid, t0, _ in SLOW_SOURCES}
    cond = conditions(power, soil, slow, e, years.start, years.stop - 1)
    return se.field_climate(cond["daily"], e, years)


async def compute(field: Field, start: int, end: int, rules: Rules, *, start_jobs: bool = True,
                  today: date | None = None, region: str | None = None) -> dict:
    """Расчёт по данным: годы, климатология, окна, источники, предупреждения, задачи."""
    e = rules.erosion
    today = today or date.today()
    warnings: list[DataWarning] = []
    power = await SOURCES["power"].fetch(field, POWER_START, today)
    soil = await SOURCES["soilgrids"].fetch(field, POWER_START, today)
    warnings += power.warnings
    slow: dict[str, tuple[SourceResult | None, dict]] = {
        sid: _slow_source(SOURCES[sid], field, t0, today, start_jobs and with_job) for sid, t0, with_job in SLOW_SOURCES
    }
    with_jobs = {sid for sid, _, with_job in SLOW_SOURCES if with_job}
    # в jobs — только реально запущенные фоновые загрузки; остальные состояния — в warnings
    jobs = [_job_entry(sid, st) for sid, (_, st) in slow.items() if sid in with_jobs and st.get("job")]
    origins = {"power": power.origin, **{sid: (res.origin if res else None) for sid, (res, _) in slow.items()}}

    years = month_grid(start, end)
    result = {"years": years, "climatology": [], "headline": {"top_months": [], "max_median_exposure": None},
              "cover_crop_windows": [], "cover_crop_note": None, "jobs": jobs, "origins": origins, "effective_thresholds": None}
    wind_col = e["erosive_wind"]["power_parameter"]
    if not power.ok or power.origin == "fallback" or wind_col not in power.data.get("daily", {}):
        # без ветра своего поля считать нельзя: климат демо-поля или старый кэш без ветра не подставляем
        code = "power_without_wind" if power.ok and power.origin != "fallback" else "bare_soil_no_weather"
        warnings.append(DataWarning(code, "power", {"origin": power.origin}))
        return {**result, "warnings": warnings}

    cond = conditions(power, soil, {sid: res for sid, (res, _) in slow.items()}, e, start, end)
    df, daily, wp, smap_thr, gw = cond["df"], cond["daily"], cond["wp"], cond["smap_thr"], cond["gw"]
    weather_days = df.index[df[wind_col].notna()]
    last_weather = weather_days[-1].date() if len(weather_days) else None
    ndvi_ready = {cov: slow[sid][1]["status"] == "ready" for cov, sid in NDVI_COVERAGE.items()}

    flags = {"gwettop": 0, "ndvi_proxy": 0, "smap": 0}
    proxy_years: set[int] = set()
    pending: list[str] = []
    for y in years:
        months = []
        for m in range(1, 13):
            mo = bs.month_summary(daily, y["year"], m, e, last_weather=last_weather, ndvi_ready=ndvi_ready)
            f = mo.pop("_flags")
            for k in flags:
                flags[k] += int(bool(f.get(k)))
            if f.get("ndvi_proxy"):
                proxy_years.add(y["year"])
            if mo["missing_reason"] == "ndvi_pending_fetch":
                pending.append(f"{y['year']}-{m:02d}")
            months.append(mo)
        y["months"] = months

    clim = bs.climatology(years, e)
    frost = bs.frost_dates(df, e, range(start, end + 1))
    cc = bs.cover_crop_windows(clim, years, frost, e, region)
    if cc["note"] is not None:
        sid = e["cover_crop"]["no_window_advice_source"]
        src = rules.sources[sid]
        cc["note"]["advice_source"] = {"id": sid, "name": src["name"], "url": src["url"], "note": src.get("note", "")}
    harvest = e["cover_crop"]["harvest_end"].get(region) if region else None
    result.update(
        climatology=clim, headline=bs.headline(clim, e),
        cover_crop_windows=cc["windows"], cover_crop_note=cc["note"],
        effective_thresholds={
            "ndvi_max": float(e["bare_soil"]["ndvi_max"].value),
            "ndvi_field_quantile": float(e["bare_soil"]["min_field_fraction"].value),
            "wind_parameter": wind_col,
            "wind_ms": float(e["erosive_wind"]["speed_ms"].value),
            "smap_m3m3": round(smap_thr, 4),
            "smap_basis": "wilting_point_0_5cm" if wp is not None else "fallback",
            "gwettop": gw["value"],
            "gwettop_basis": gw["basis"],
            "gwettop_pairs": gw["pairs"],
            "last_frost_spring": frost["last_spring"].strftime("%m-%d") if frost["last_spring"] else None,
            "first_frost_autumn": frost["first_autumn"].strftime("%m-%d") if frost["first_autumn"] else None,
            "frost_years": frost["n_years"],
            "harvest_end": harvest.value if harvest is not None else None,
        },
    )

    # ---- предупреждения ---------------------------------------------------------
    field_km2 = field.area_ha / 100
    cell_km2 = _power_cell_km2(field.centroid_lat)
    if field_km2 < cell_km2:
        warnings.append(DataWarning("cell_larger_than_field", "power",
                                    {"cell_km2": round(cell_km2), "field_km2": round(field_km2, 2)}))
    smap_cell_km2 = (CELL_M / 1000) ** 2
    if flags["smap"] and field_km2 < smap_cell_km2:
        warnings.append(DataWarning("cell_larger_than_field", "smap",
                                    {"cell_km2": round(smap_cell_km2), "field_km2": round(field_km2, 2)}))
    if date(start, 1, 1) < SMAP_FIRST_DAY:
        warnings.append(DataWarning("smap_before_2015_unavailable", "smap",
                                    {"first_day": SMAP_FIRST_DAY.isoformat(), "fallback": "power_gwettop"}))
    if flags["gwettop"]:
        warnings.append(DataWarning("moisture_fallback_gwettop", "smap", {"months": flags["gwettop"]}))
    if gw["basis"] == "fallback":
        warnings.append(DataWarning("gwettop_threshold_fallback", "rules",
                                    {"pairs": gw["pairs"], "value": gw["value"]}))
    if wp is None:
        warnings.append(DataWarning("smap_threshold_fallback", "soilgrids", {"value": smap_thr}))
    if flags["ndvi_proxy"]:
        warnings.append(DataWarning("ndvi_field_mean_proxy", "modis",
                                    {"months": flags["ndvi_proxy"], "years": sorted(proxy_years)}))
    if pending:
        sources = sorted({sid for cov, sid in NDVI_COVERAGE.items() if not ndvi_ready[cov]})
        warnings.append(DataWarning("ndvi_pending_fetch", ",".join(sources), {"months": len(pending)}))
    for sid, (_, st) in slow.items():
        if st["status"] == "unavailable" and st.get("reason") != "offline":
            warnings.append(DataWarning("source_unavailable", sid, {"detail": st.get("reason") or ""}))
        elif st["status"] == "unavailable":
            warnings.append(DataWarning("offline_no_cache", sid))
        elif st["status"] == "not_configured" and sid == "smap_season":
            warnings.append(DataWarning("smap_not_configured", sid))
    return {**result, "warnings": warnings}


def overall_status(years: list[dict], jobs: list[dict]) -> str:
    """ok / partial / loading / missing; будущие месяцы (missing_reason: future) не учитываются."""
    months = [m for y in years for m in y["months"] if m["missing_reason"] != "future"]
    done = [m for m in months if m["state"] in ("ok", "snow")]
    running = any(j["status"] == "pending" for j in jobs)
    if not done:
        return "loading" if running else "missing"
    if running or len(done) < len(months) or any(m["quality"] == "partial" for m in done):
        return "partial"
    return "ok"


def _sources(origins: dict) -> list[dict]:
    """Источники в форме monitoring.source_meta. MODIS и SMAP — по основному ряду, межсезонье — в jobs."""
    return [source_meta(sid, origins.get(sid) or (origins.get(alt) if alt else None))
            for sid, alt in (("power", None), ("modis", "modis_shoulder"), ("smap", "smap_season"))]


async def bare_soil(field_id: int, geometry: dict, start_year: int | None, end_year: int | None,
                    rules: Rules | None = None, *, start_jobs: bool = True, region: str | None = None) -> dict:
    """Ответ по контракту. ``rules`` — правила с порогами erosion.yaml (по умолчанию ``get_rules()``);
    аудит (``make audit``) передаёт правила с другим порогом NDVI для оценки чувствительности."""
    rules = rules or get_rules()
    start, end = resolve_period(start_year, end_year)
    field = parse_field(geometry)
    r = await compute(field, start, end, rules, start_jobs=start_jobs, region=region)
    body = {
        "field_id": field_id,
        "period": {"start_year": start, "end_year": end},
        "status": overall_status(r["years"], r["jobs"]),
        "jobs": r["jobs"],
        "headline": r["headline"],
        "definition": DEFINITION,
        "thresholds": thresholds(rules),
        "effective_thresholds": r["effective_thresholds"],
        "years": r["years"],
        "climatology": r["climatology"],
        "cover_crop_windows": r["cover_crop_windows"],
        "cover_crop_note": r["cover_crop_note"],
        "sources": _sources(r["origins"]),
        "warnings": [w.as_dict() for w in r["warnings"]],
    }
    return BareSoilOut.model_validate(body).model_dump(mode="json")
