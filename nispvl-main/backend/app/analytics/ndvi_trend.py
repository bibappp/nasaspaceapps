"""Тренд NDVI: максимум за сезон по годам и линейная регрессия."""
from __future__ import annotations

from scipy import stats


def yearly_max(series: list[dict], min_valid_fraction: float) -> list[dict]:
    by_year: dict[int, dict] = {}
    counts: dict[int, int] = {}
    for row in series:
        if row.get("ndvi") is None or row.get("valid_fraction", 0) < min_valid_fraction:
            continue
        year = int(row["date"][:4])
        counts[year] = counts.get(year, 0) + 1
        if year not in by_year or row["ndvi"] > by_year[year]["ndvi"]:
            by_year[year] = {"year": year, "ndvi": row["ndvi"], "date": row["date"]}
    # сезон считаем состоявшимся, если есть хотя бы 5 пригодных композитов из 10
    return [{**by_year[y], "n_composites": counts[y]} for y in sorted(by_year) if counts[y] >= 5]


def ndvi_trend(series: list[dict], cfg: dict) -> dict:
    yearly = yearly_max(series, float(cfg["min_valid_fraction"]))
    min_years = int(cfg["min_years"])
    p_cut = float(cfg["p_value"].value)
    out: dict = {"yearly_max": yearly, "label": "insufficient", "slope_per_year": None, "p_value": None}
    if len(yearly) < min_years:
        return out
    xs = [r["year"] for r in yearly]
    ys = [r["ndvi"] for r in yearly]
    reg = stats.linregress(xs, ys)
    if reg.pvalue < p_cut:
        label = "rising" if reg.slope > 0 else "declining"
    else:
        label = "stable"
    mean = sum(ys) / len(ys)
    out.update(
        {
            "label": label,
            "slope_per_year": round(float(reg.slope), 5),
            "slope_pct_per_decade": round(float(reg.slope) * 10 / mean * 100, 1) if mean else None,
            "intercept": round(float(reg.intercept), 4),
            "p_value": round(float(reg.pvalue), 4),
            "r2": round(float(reg.rvalue**2), 3),
            "mean": round(mean, 4),
            "from_year": xs[0],
            "to_year": xs[-1],
            "n_years": len(xs),
            "p_threshold": p_cut,
        }
    )
    return out
