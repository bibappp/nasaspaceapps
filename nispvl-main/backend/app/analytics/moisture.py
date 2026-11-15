"""Доступная влага перед посевом.

Запас продуктивной влаги в метровом слое к посеву в году Y:

    запас(Y) = min( ДДВ почвы поля, норма области x поправка(Y) )

  * норма области — обычный запас влаги перед посевом (regions.yaml);
  * поправка(Y) — насколько год был влажнее или суше обычного:
      - если есть SMAP: влажность почвы в апреле–мае года Y / медиана по годам SMAP;
      - иначе: осадки сентября–апреля перед сезоном Y / их медиана (NASA POWER);
    поправка ограничена диапазоном из model.yaml (по умолчанию 0,5–1,5);
  * ДДВ — диапазон доступной влаги метрового слоя по SoilGrids (см. soil_water.py):
    почва не может удержать больше.

Абсолютные значения SMAP и POWER имеют систематические смещения, поэтому
используются только их отношения к собственной норме.
"""
from __future__ import annotations

import statistics

MIN_SMAP_DAYS = 5


def smap_presowing_by_year(smap_data: dict | None, months: list[int]) -> dict[int, dict]:
    """Средняя влажность SMAP за предпосевные месяцы по годам (м³/м³)."""
    if not smap_data:
        return {}
    acc: dict[int, list[float]] = {}
    for row in smap_data.get("daily", []):
        if row.get("sm") is None or int(row["date"][5:7]) not in months:
            continue
        acc.setdefault(int(row["date"][:4]), []).append(row["sm"])
    return {
        year: {"mean": round(sum(v) / len(v), 4), "n_days": len(v)}
        for year, v in sorted(acc.items())
        if len(v) >= MIN_SMAP_DAYS
    }


def gwet_presowing_by_year(daily_df, months: list[int]) -> dict[int, float]:
    """Запасной показатель: модельная влажность корнеобитаемого слоя POWER (GWETROOT, 0–1)."""
    if "GWETROOT" not in daily_df:
        return {}
    part = daily_df[daily_df.index.month.isin(months)]["GWETROOT"].dropna()
    out = {}
    for year, grp in part.groupby(part.index.year):
        if len(grp) >= 0.9 * 30 * len(months):
            out[int(year)] = round(float(grp.mean()), 3)
    return out


def presowing_stock(
    norm_mm: float,
    offseason: dict[int, float],
    smap_by_year: dict[int, dict],
    awc_mm: float | None,
    bounds: tuple[float, float],
    window_years: list[int],
) -> dict:
    """Запас влаги к посеву по годам и «обычный» запас (медиана за окно лет)."""
    off_window = [offseason[y] for y in window_years if y in offseason]
    off_median = statistics.median(off_window) if off_window else None
    smap_median = statistics.median([v["mean"] for v in smap_by_year.values()]) if len(smap_by_year) >= 3 else None

    rows: dict[int, dict] = {}
    for year in sorted(set(offseason) | set(smap_by_year)):
        if smap_median and year in smap_by_year:
            ratio, basis = smap_by_year[year]["mean"] / smap_median, "smap"
        elif off_median and year in offseason:
            ratio, basis = offseason[year] / off_median, "power"
        else:
            continue
        ratio = min(max(ratio, bounds[0]), bounds[1])
        stock = norm_mm * ratio
        capped = awc_mm is not None and stock > awc_mm
        if capped:
            stock = awc_mm
        rows[year] = {"year": year, "ratio": round(ratio, 3), "basis": basis, "stock_mm": round(stock, 1), "capped": capped}

    in_window = [rows[y]["stock_mm"] for y in window_years if y in rows]
    normal = statistics.median(in_window) if in_window else min(norm_mm, awc_mm or norm_mm)
    return {
        "norm_mm": norm_mm,
        "awc_mm": awc_mm,
        "normal_stock_mm": round(normal, 1),
        "by_year": list(rows.values()),
        "uses_smap": smap_median is not None,
        "smap_median": None if smap_median is None else round(smap_median, 4),
        "offseason_median_mm": None if off_median is None else round(off_median, 1),
    }
