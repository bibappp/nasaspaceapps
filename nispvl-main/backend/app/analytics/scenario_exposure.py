"""Дни без зелёного покрова и индекс опасности ветровой эрозии для сценариев планировщика.

Чистые функции без сети и файлов. Все пороги — правила ``rules/erosion.yaml`` (те же, что у «Часов голой
почвы»), окна сева и уборки — ``rules/crops.yaml``; числовых порогов здесь нет.

Для каждого года сценария:

    бесснежный сезон  = от медианы последнего весеннего до медианы первого осеннего снежного дня (правила snow,
                        граница весны и осени — cover_crop.season_split_month), климатология поля
    период покрова    = [граница окна сева, граница окна уборки] (erosion.planner.canopy_start / canopy_end);
                        у пара покрова нет (crops.fallow.bare_whole_season)
    bare_days         = дни бесснежного сезона вне периода покрова
    p(месяц)          = доля известных бесснежных дней месяца, когда одновременно эрозионный ветер и сухой
                        верхний слой (как в «Часах», но без NDVI — покров задаёт календарь культуры)
    risky_days        = Σ p(месяц дня) по дням без покрова — ожидаемое число опасных дней
    exposure          = risky_days / дней бесснежного сезона — доля дней сезона «без покрова, ветер и сухо»,
                        тот же смысл, что exposure у «Часов», только за весь сезон

По сценарию: ``bare_days_per_year`` и ``exposure_index`` — средние по годам плана. В балл почвы не входят.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..model.rules import Param, Rules, parse_window
from .bare_soil import REF_YEAR, _ref_doy


def _ref_date(doy: float) -> date:
    return date(REF_YEAR, 1, 1) + timedelta(days=int(round(doy)) - 1)


def _ref_doys(idx: pd.DatetimeIndex) -> np.ndarray:
    """Номер дня в невисокосном опорном году для каждой даты (как ``bare_soil._ref_doy``)."""
    return np.array([_ref_doy(d) for d in idx.date], dtype=int)


def snow_free_season(daily: pd.DataFrame, e: dict, years: range) -> dict:
    """Медианы дат последнего весеннего и первого осеннего снежного дня по полным годам → бесснежный сезон."""
    split = int(e["cover_crop"]["season_split_month"])
    last, first = [], []
    for y in years:
        d = daily[daily.index.year == y]
        if len(d) < (date(y, 12, 31) - date(y, 1, 1)).days + 1 or not bool(d["weather"].all()):  # полные годы
            continue
        sn = d[d["snow"].astype(bool)]
        spring, autumn = sn[sn.index.month <= split], sn[sn.index.month > split]
        if len(spring) and len(autumn):
            last.append(_ref_doy(spring.index[-1].date()))
            first.append(_ref_doy(autumn.index[0].date()))
    if not last:
        return {"start": None, "end": None, "days": None, "n_years": 0}
    start = _ref_date(float(np.median(last))) + timedelta(days=1)
    end = _ref_date(float(np.median(first))) - timedelta(days=1)
    if start > end:
        return {"start": None, "end": None, "days": None, "n_years": len(last)}
    return {"start": start, "end": end, "days": (end - start).days + 1, "n_years": len(last)}


def wind_dry_by_month(daily: pd.DataFrame, e: dict, season: dict, years: range) -> list[dict]:
    """Для каждого месяца — доля известных бесснежных дней сезона, когда и ветер эрозионный, и сухо.

    Месяц года входит в расчёт, если известных дней не меньше ``month.min_known_fraction`` от дней сезона
    в этом месяце; доля показывается, если таких лет не меньше ``climatology.min_years`` (иначе ``None``)."""
    min_frac = float(e["month"]["min_known_fraction"].value)
    min_years = int(e["climatology"]["min_years"].value)
    d = daily[(daily.index.year >= years.start) & (daily.index.year < years.stop)]
    if season["start"] is None or len(d) == 0:
        return [{"month": m, "p_wind_dry": None, "n_years": 0, "season_days": 0} for m in range(1, 13)]
    doy = _ref_doys(d.index)
    in_season = (doy >= _ref_doy(season["start"])) & (doy <= _ref_doy(season["end"]))
    snow = d["snow"].to_numpy(dtype=bool)
    known = (d["windy"].notna() & d["dry"].notna()).to_numpy() & in_season & ~snow
    joint = (d["windy"].fillna(False) & d["dry"].fillna(False)).to_numpy(dtype=bool) & known
    frame = pd.DataFrame({"year": d.index.year, "month": d.index.month, "season": in_season, "known": known,
                          "joint": joint})
    by = frame.groupby(["month", "year"]).sum()
    out = []
    for m in range(1, 13):
        season_days = int(sum(1 for k in range(1, calendar.monthrange(REF_YEAR, m)[1] + 1)
                              if season["start"] <= date(REF_YEAR, m, k) <= season["end"]))
        rows = by.loc[m] if m in by.index.get_level_values(0) else None
        ok = rows[(rows["season"] > 0) & (rows["known"] >= min_frac * rows["season"])] if rows is not None else None
        n_years = 0 if ok is None else len(ok)
        p = None
        if season_days and n_years >= min_years and ok["known"].sum() > 0:
            p = round(float(ok["joint"].sum() / ok["known"].sum()), 4)
        out.append({"month": m, "p_wind_dry": p, "n_years": n_years, "season_days": season_days})
    return out


def field_climate(daily: pd.DataFrame, e: dict, years: range) -> dict:
    """Климатология поля для планировщика: бесснежный сезон и доля дней «ветер и сухо» по месяцам."""
    season = snow_free_season(daily, e, years)
    months = wind_dry_by_month(daily, e, season, years)
    if season["start"] is None:
        status, reason = "missing", "no_snow_season"
    elif not any(m["p_wind_dry"] is not None for m in months if m["season_days"]):
        status, reason = "missing", "no_wind_dry_climatology"
    elif any(m["p_wind_dry"] is None for m in months if m["season_days"]):
        status, reason = "partial", None
    else:
        status, reason = "ok", None
    return {"status": status, "missing_reason": reason, "season": season, "months": months,
            "period": {"start_year": years.start, "end_year": years.stop - 1}}


def missing_climate(reason: str, years: range | None = None) -> dict:
    """Климатологии нет (нет ветра POWER и т. п.): числа сценариев — ``None``, не 0."""
    period = {"start_year": years.start, "end_year": years.stop - 1} if years else None
    return {"status": "missing", "missing_reason": reason,
            "season": {"start": None, "end": None, "days": None, "n_years": 0}, "months": [], "period": period}


# ---------------------------------------------------------------- период покрова культуры
def _pick(window: tuple[date, date], choice: str) -> date:
    a, b = window
    if choice.endswith("_start"):
        return a
    if choice.endswith("_end"):
        return b
    return a + timedelta(days=(b - a).days // 2)


def canopy(rules: Rules, crop_id: str, *, start: str | None = None, end: str | None = None) -> tuple[date, date] | None:
    """Период покрова культуры (включительно) в опорном году; ``None`` — покрова нет (пар).
    ``start``/``end`` заменяют выбор из erosion.planner (только для оценки чувствительности в аудите)."""
    crop = rules.crop(crop_id)
    flag = crop.get("bare_whole_season")
    if isinstance(flag, Param) and flag.value:
        return None
    pl = rules.erosion["planner"]
    c0 = _pick(parse_window(crop["sowing_window"]), start or pl["canopy_start"].value)
    c1 = _pick(parse_window(crop["harvest_window"]), end or pl["canopy_end"].value)
    return c0, c1


def season_year(rules: Rules, crop_id: str, climate: dict, **choice: Any) -> dict:
    """Один год сценария: дни без покрова, ожидаемые опасные дни и exposure."""
    season = climate["season"]
    cp = canopy(rules, crop_id, **choice)
    base = {"crop": crop_id, "canopy_start": cp[0].strftime("%m-%d") if cp else None,
            "canopy_end": cp[1].strftime("%m-%d") if cp else None}
    if season["start"] is None:
        return {**base, "bare_days": None, "risky_days": None, "exposure": None}
    p = {m["month"]: m["p_wind_dry"] for m in climate["months"]}
    bare = [season["start"] + timedelta(days=k) for k in range(season["days"])]
    if cp is not None:
        bare = [d for d in bare if not cp[0] <= d <= cp[1]]
    probs = [p.get(d.month) for d in bare]
    risky = None if any(x is None for x in probs) else float(sum(probs))
    return {**base, "bare_days": len(bare), "risky_days": None if risky is None else round(risky, 1),
            "exposure": None if risky is None else round(risky / season["days"], 4)}


def _mean(xs: list[float | None], digits: int) -> float | None:
    return None if not xs or any(x is None for x in xs) else round(float(np.mean(xs)), digits)


def scenario(rules: Rules, years: list[dict], climate: dict, **choice: Any) -> dict:
    """Сценарий по годам плана (``years`` — элементы ``variant["years"]``) → объект ``bare_soil``."""
    per_year = [{"index": y["index"], "year": y["year"], **season_year(rules, y["crop"], climate, **choice)}
                for y in years]
    bare = _mean([y["bare_days"] for y in per_year], 1)
    exposure = _mean([y["exposure"] for y in per_year], 4)
    if climate["status"] == "missing":
        status, reason = "missing", climate["missing_reason"]
    elif exposure is None:
        status, reason = "partial", "wind_dry_months_missing"
    else:
        status, reason = climate["status"], None
    return {"status": status, "missing_reason": reason, "bare_days_per_year": bare, "mean_exposure": exposure,
            "risky_days_per_year": _mean([y["risky_days"] for y in per_year], 1), "per_year": per_year}


def rule_refs(rules: Rules, crop_ids: list[str], region: str | None) -> list[dict]:
    """Правила, на которых стоят числа: окна культур, выбор границ покрова, пороги ветра, сухости и снега."""
    e = rules.erosion
    refs: list[Param] = []
    for cid in dict.fromkeys(crop_ids):
        crop = rules.crop(cid)
        refs += [crop[k] for k in ("sowing_window", "harvest_window", "bare_whole_season") if isinstance(crop.get(k), Param)]
    refs += [e["planner"]["canopy_start"], e["planner"]["canopy_end"], e["erosive_wind"]["speed_ms"],
             e["dry_topsoil"]["smap_wilting_point_factor"], e["dry_topsoil"]["gwettop_min_pairs"],
             e["snow"]["power_frsno_min"], e["snow"]["power_snodp_min_cm"], e["month"]["min_known_fraction"],
             e["climatology"]["min_years"]]
    harvest = e["cover_crop"]["harvest_end"].get(region) if region else None
    if harvest is not None:
        refs.append(harvest)
    return [p.ref() for p in refs]


def season_out(climate: dict) -> dict:
    """Климатология поля в ответе API (даты — «ММ-ДД»)."""
    s = climate["season"]
    return {"status": climate["status"], "missing_reason": climate["missing_reason"], "period": climate["period"],
            "start": s["start"].strftime("%m-%d") if s["start"] else None,
            "end": s["end"].strftime("%m-%d") if s["end"] else None, "days": s["days"], "n_years": s["n_years"],
            "months": [m for m in climate["months"] if m["season_days"]]}


def attach(rules: Rules, result: dict, climate: dict, region: str | None) -> None:
    """Добавить в каждый вариант ``bare_days_per_year``, ``exposure_index`` и объект ``bare_soil``;
    в ответ — ``bare_soil_season``. Балл, оценки и рейтинг не меняются (``in_score: false``)."""
    season = season_out(climate)
    for v in result["variants"]:
        sc = scenario(rules, v["years"], climate)
        v["bare_days_per_year"] = sc["bare_days_per_year"]
        v["exposure_index"] = sc["mean_exposure"]
        v["bare_soil"] = {**sc, "season": {k: season[k] for k in ("start", "end", "days", "n_years", "period")},
                          "rules": rule_refs(rules, [y["crop"] for y in v["years"]], region), "in_score": False}
    result["bare_soil_season"] = season


# ---------------------------------------------------------------- отчёты (PDF и XLSX — одни и те же тексты)
def _short_source(name: str) -> str:
    """Короткое название источника для отчёта: до первой запятой, точки, скобки или двоеточия."""
    cut = min((i for i in (name.find(ch) for ch in ",.(:") if i > 0), default=len(name))
    return name[:cut].strip()


def window_sources(variants: list[dict]) -> list[dict]:
    """Источники и статусы окон сева и уборки культур сравниваемых сценариев:
    ``[{source, status, evidence, crops}]`` — одна строка на источник (коротко) и статус."""
    groups: dict[tuple, list[str]] = {}
    for v in variants:
        for r in (v.get("bare_soil") or {}).get("rules", []):
            parts = r["path"].split(".")
            if parts[0] != "crops":
                continue
            crops = groups.setdefault((_short_source(r["source"]), r["status"], r["evidence"]), [])
            if parts[1] not in crops:
                crops.append(parts[1])
    return [{"source": k[0], "status": k[1], "evidence": k[2], "crops": c} for k, c in groups.items()]


def _mmdd(x: str, lang: str) -> str:
    d = date(REF_YEAR, int(x[:2]), int(x[3:]))
    return f"{d.day} {d.strftime('%b')}" if lang == "en" else d.strftime("%d.%m")


def report_note(comparison: dict, t: dict, crop_name: Any, wind_ms: float, fmt: Any, lang: str) -> str:
    """Пояснение к столбцам «дни без покрова» и «индекс опасности эрозии»: определение, источник и статус.
    ``t`` — строки отчёта (locales/report.yaml), ``crop_name(id)`` — название культуры, ``fmt(x, digits)`` — число."""
    season = comparison.get("bare_soil_season")
    if not season:  # анализ сохранён до задачи 5 — отчёт показывает «—»
        return t["bare_not_saved"]
    if season["start"] is None:
        return t["bare_missing"].format(reason=season.get("missing_reason") or "")
    windows = "; ".join(f"{', '.join(crop_name(c) for c in w['crops'])} — {w['source']} ({w['status']}, {w['evidence']})"
                        for w in window_sources(comparison["variants"]))
    return t["bare_note"].format(start=_mmdd(season["start"], lang), end=_mmdd(season["end"], lang), days=season["days"],
                                 n=season["n_years"], wind=fmt(wind_ms, 1), windows=windows)
