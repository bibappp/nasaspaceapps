"""Климатическая сводка по ряду NASA POWER: осадки сезона, засушливые годы."""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

MIN_COVERAGE = 0.95  # доля суток с данными, при которой период считается полным


def daily_frame(power_data: dict) -> pd.DataFrame:
    df = pd.DataFrame(power_data["daily"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df.apply(pd.to_numeric, errors="coerce")


def _period_sum(df: pd.DataFrame, column: str, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    if end > df.index.max() or start < df.index.min():
        return None
    part = df.loc[start:end, column]
    expected = (end - start).days + 1
    if expected <= 0 or part.count() / expected < MIN_COVERAGE:
        return None
    return float(part.sum() * expected / part.count())  # пропуски заполняем средним


def season_precip_by_year(df: pd.DataFrame, months: list[int]) -> dict[int, float]:
    """Сумма осадков за сезон (по умолчанию май–август) по годам, мм. Только полные сезоны."""
    out: dict[int, float] = {}
    m0, m1 = min(months), max(months)
    for year in range(df.index.min().year, df.index.max().year + 1):
        start = pd.Timestamp(year, m0, 1)
        end = pd.Timestamp(year, m1, 1) + pd.offsets.MonthEnd(0)
        value = _period_sum(df, "PRECTOTCORR", start, end)
        if value is not None:
            out[year] = round(value, 1)
    return out


def offseason_precip_by_year(df: pd.DataFrame, months: list[int]) -> dict[int, float]:
    """Осадки холодного периода перед сезоном (сентябрь прошлого года – апрель), мм."""
    out: dict[int, float] = {}
    first_month, last_month = months[0], months[-1]
    for year in range(df.index.min().year + 1, df.index.max().year + 1):
        start = pd.Timestamp(year - 1 if first_month > last_month else year, first_month, 1)
        end = pd.Timestamp(year, last_month, 1) + pd.offsets.MonthEnd(0)
        value = _period_sum(df, "PRECTOTCORR", start, end)
        if value is not None:
            out[year] = round(value, 1)
    return out


def season_temperature_by_year(df: pd.DataFrame, months: list[int]) -> dict[int, dict[str, float]]:
    out: dict[int, dict[str, float]] = {}
    part = df[df.index.month.isin(months)]
    for year, grp in part.groupby(part.index.year):
        if grp["T2M"].count() < 0.9 * 30 * len(months):
            continue
        out[int(year)] = {
            "t_mean": round(float(grp["T2M"].mean()), 1),
            "t_max_mean": round(float(grp["T2M_MAX"].mean()), 1),
            "hot_days": int((grp["T2M_MAX"] >= 30).sum()),
        }
    return out


def monthly_normals(df: pd.DataFrame, baseline: tuple[int, int]) -> list[dict]:
    part = df[(df.index.year >= baseline[0]) & (df.index.year <= baseline[1])]
    out = []
    for month in range(1, 13):
        m = part[part.index.month == month]
        if m.empty:
            continue
        years = m.index.year.nunique()
        out.append(
            {
                "month": month,
                "precip_mm": round(float(m["PRECTOTCORR"].sum() / years), 1),
                "t_mean": round(float(m["T2M"].mean()), 1),
            }
        )
    return out


def drought_analysis(season: dict[int, float], cfg: dict) -> dict:
    """Засушливые годы по определению из model.yaml.

    Год засушливый, если сумма осадков сезона ниже P-го перцентиля базового периода
    ИЛИ стандартизированная аномалия (год − среднее) / σ не больше порога.
    """
    b0, b1 = cfg["baseline_years"]
    percentile = float(cfg["percentile"].value)
    threshold = float(cfg["anomaly_threshold"].value)
    window = int(cfg["window_years"])

    years = sorted(season)
    base = [season[y] for y in years if b0 <= y <= b1]
    if len(base) < 10:  # ряд слишком короткий — берём всё, что есть
        base = [season[y] for y in years]
        b0, b1 = years[0], years[-1]
    mean, std = float(np.mean(base)), float(np.std(base, ddof=1))
    p_cut = float(np.percentile(base, percentile))

    rows = []
    for y in years:
        z = (season[y] - mean) / std if std > 0 else 0.0
        by_percentile = season[y] < p_cut
        by_anomaly = z <= threshold
        rows.append(
            {
                "year": y,
                "precip_mm": season[y],
                "anomaly": round(z, 2),
                "is_dry": bool(by_percentile or by_anomaly),
                "by_percentile": bool(by_percentile),
                "by_anomaly": bool(by_anomaly),
            }
        )
    recent = rows[-window:]
    dry_recent = [r["year"] for r in recent if r["is_dry"]]
    share = len(dry_recent) / len(recent) if recent else 0.0
    every_nth = int(round(1 / share)) if share > 0 else None
    driest = min(recent, key=lambda r: r["precip_mm"]) if recent else None
    return {
        "definition": {
            "baseline": [b0, b1],
            "percentile": percentile,
            "percentile_mm": round(p_cut, 1),
            "anomaly_threshold": threshold,
            "baseline_mean_mm": round(mean, 1),
            "baseline_std_mm": round(std, 1),
        },
        "years": rows,
        "window": {"from": recent[0]["year"], "to": recent[-1]["year"], "n_years": len(recent)} if recent else None,
        "dry_years": dry_recent,
        "share": round(share, 3),
        "every_nth": every_nth,
        "driest_year": driest["year"] if driest else None,
        "median_mm": round(float(np.median([r["precip_mm"] for r in recent])), 1) if recent else None,
    }


def last_complete_season_year(season: dict[int, float]) -> int:
    return max(season) if season else date.today().year - 1


def safe_ratio(a: float, b: float) -> float:
    return a / b if b and not math.isnan(b) else 1.0
