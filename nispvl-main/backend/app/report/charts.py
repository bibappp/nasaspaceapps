"""Графики для PDF-отчёта (matplotlib, без дисплея). Единая палитра и типографика."""
from __future__ import annotations

import io
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, Normalize  # noqa: E402
from matplotlib.patches import Polygon as MplPolygon  # noqa: E402

from .fonts import FONT_BOLD_PATH, FONT_PATH  # noqa: E402

for _p in (FONT_PATH, FONT_BOLD_PATH):
    font_manager.fontManager.addfont(str(_p))
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.unicode_minus": False,
    "axes.edgecolor": "#C9CED6",
    "axes.labelcolor": "#374151",
    "xtick.color": "#4B5563",
    "ytick.color": "#4B5563",
    "axes.titleweight": "bold",
    "axes.titlesize": 10,
    "axes.titlecolor": "#1F2328",
})

INK = "#1F2328"
MUTED = "#6B7280"
GRID = "#E5E7EB"
GREEN = "#1F5134"
# Категориальная палитра вариантов (проверена на различимость при дальтонизме; см. frontend/src/lib/colors.ts)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
DRY = "#c2410c"
NORMAL = "#2a78d6"
NDVI_CMAP = LinearSegmentedColormap.from_list("ndvi", ["#f3efe0", "#c9dca6", "#7fae5a", "#2f6b2a", "#16401a"])


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _style(ax, grid_axis: str = "y") -> None:
    ax.grid(True, axis=grid_axis, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(labelsize=8)


# ---------------------------------------------------------------- карта поля
def field_map(geometry: dict, grid: dict | None, raster: list | None, mask: list | None, pixel_polygon, labels: dict) -> bytes:
    """Контур поля поверх пикселей NDVI MODIS; масштабная линейка и стрелка севера."""
    ring = geometry["coordinates"][0]
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    lat0 = sum(lats) / len(lats)
    fig, ax = plt.subplots(figsize=(6.2, 4.6))
    norm = Normalize(0.1, 0.8)
    if grid and raster:
        for r in range(grid["nrows"]):
            for c in range(grid["ncols"]):
                i = r * grid["ncols"] + c
                v = raster[i]
                poly = pixel_polygon(grid, r, c)
                inside = bool(mask[i]) if mask else True
                face = NDVI_CMAP(norm(v * 0.0001)) if v is not None else "#e5e7eb"
                ax.add_patch(MplPolygon(poly, closed=True, facecolor=face, edgecolor="white", linewidth=0.3,
                                        alpha=1.0 if inside else 0.45))
                lons += [p[0] for p in poly]
                lats += [p[1] for p in poly]
        sm = plt.cm.ScalarMappable(norm=norm, cmap=NDVI_CMAP)
        cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
        cb.set_label("NDVI", fontsize=8)
        cb.ax.tick_params(labelsize=7)
    ax.add_patch(MplPolygon([(p[0], p[1]) for p in ring], closed=True, fill=False, edgecolor="#0b2a17", linewidth=2.2))
    pad_x, pad_y = (max(lons) - min(lons)) * 0.04, (max(lats) - min(lats)) * 0.04
    ax.set_xlim(min(lons) - pad_x, max(lons) + pad_x)
    ax.set_ylim(min(lats) - pad_y, max(lats) + pad_y)
    ax.set_aspect(1 / math.cos(math.radians(lat0)))
    ax.tick_params(labelsize=7, colors=MUTED)
    ax.set_xlabel("°E", fontsize=7, color=MUTED)
    ax.set_ylabel("°N", fontsize=7, color=MUTED)
    # масштабная линейка 1 км
    km_deg = 1 / (111.32 * math.cos(math.radians(lat0)))
    x0 = ax.get_xlim()[0] + (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.05
    y0 = ax.get_ylim()[0] + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.05
    ax.plot([x0, x0 + km_deg], [y0, y0], color=INK, linewidth=2.5, solid_capstyle="butt")
    ax.text(x0 + km_deg / 2, y0 + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.02, "1 km", ha="center", fontsize=7, color=INK)
    # стрелка севера
    xn = ax.get_xlim()[1] - (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.06
    yn = ax.get_ylim()[1] - (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.16
    ax.annotate("N", xy=(xn, yn + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.1), xytext=(xn, yn), ha="center", fontsize=8,
                fontweight="bold", color=INK, arrowprops={"arrowstyle": "-|>", "color": INK, "lw": 1.2})
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    return _png(fig)


# ---------------------------------------------------------------- вегетация
def ndvi_history(years: list[dict], trend: dict | None, labels: dict) -> bytes:
    pts = [(r["year"], r["ndvi_max"], r["is_dry"]) for r in years if r.get("ndvi_max") is not None]
    fig, ax = plt.subplots(figsize=(8.6, 2.7))
    ax.scatter([p[0] for p in pts if not p[2]], [p[1] for p in pts if not p[2]], s=22, color=GREEN, label=labels["normal_year"], zorder=3)
    ax.scatter([p[0] for p in pts if p[2]], [p[1] for p in pts if p[2]], s=26, color=DRY, marker="s", label=labels["dry_year"], zorder=3)
    if trend and trend.get("slope_per_year") is not None and pts:
        xs = [pts[0][0], pts[-1][0]]
        ax.plot(xs, [trend["intercept"] + trend["slope_per_year"] * x for x in xs], color=MUTED, linestyle="--", linewidth=1.3,
                label=labels["trend_line"])
    ax.set_ylim(0, 1)
    ax.set_title(labels["chart_ndvi_max"], loc="left")
    _style(ax)
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="lower left")
    return _png(fig)


def ndvi_curves(curves: dict, clim: list[dict], labels: dict, last_n: int = 3) -> bytes:
    fig, ax = plt.subplots(figsize=(8.6, 2.8))
    if clim:
        xs = [c["doy"] for c in clim]
        ax.fill_between(xs, [c["p10"] for c in clim], [c["p90"] for c in clim], color="#d1d5db", alpha=0.5, linewidth=0)
        ax.plot(xs, [c["median"] for c in clim], color=MUTED, linewidth=1.5, label=labels["median_band"])
    for i, y in enumerate(sorted(curves)[-last_n:]):
        pts = curves[y]
        ax.plot([p["doy"] for p in pts], [p["ndvi"] for p in pts], color=SERIES[i], linewidth=1.8, marker="o", markersize=3, label=y)
    ax.set_ylim(0, 1)
    ax.set_xlabel(labels["day_of_year"], fontsize=8)
    ax.set_title(labels["chart_ndvi_curves"], loc="left")
    _style(ax)
    ax.legend(fontsize=7, frameon=False, ncol=4, loc="upper right")
    return _png(fig)


# ---------------------------------------------------------------- вода
def precip_history(years: list[dict], p20: float, from_year: int, labels: dict) -> bytes:
    rows = [r for r in years if r["year"] >= from_year]
    fig, ax = plt.subplots(figsize=(8.6, 2.7))
    ax.bar([r["year"] for r in rows], [r["precip_mm"] for r in rows], color=[DRY if r["is_dry"] else NORMAL for r in rows], width=0.75)
    ax.axhline(p20, color=DRY, linestyle="--", linewidth=1, label=labels["p20_line"])
    ax.bar([0], [0], color=NORMAL, label=labels["normal_year"])
    ax.bar([0], [0], color=DRY, label=labels["dry_year"])
    ax.set_xlim(rows[0]["year"] - 0.8, rows[-1]["year"] + 0.8)
    ax.set_title(labels["chart_precip"], loc="left")
    _style(ax)
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="upper left")
    return _png(fig)


def smap_history(years: list[dict], labels: dict) -> bytes | None:
    rows = [r for r in years if r.get("smap_ratio") is not None]
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(8.6, 2.2))
    ax.bar([r["year"] for r in rows], [r["smap_ratio"] for r in rows],
           color=[DRY if r["smap_ratio"] < 0.9 else NORMAL for r in rows], width=0.7)
    ax.axhline(1, color=MUTED, linewidth=1)
    ax.set_title(labels["chart_smap"], loc="left")
    _style(ax)
    return _png(fig)


# ---------------------------------------------------------------- сценарии
def forecast_chart(variants: list[dict], names: list[str], t: dict[str, str]) -> bytes:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.2))
    for i, (v, label) in enumerate(zip(variants, names, strict=False)):
        years = [y["year"] for y in v["years"]]
        style = {"color": SERIES[i % len(SERIES)], "marker": "o", "linewidth": 1.9, "markersize": 4}
        ax1.plot(years, [y["income_kzt_ha"] / 1000 for y in v["years"]], label=label, **style)
        ax2.plot(years, [y["soil_index"] for y in v["years"]], label=label, **style)
    for ax, title in ((ax1, t["chart_income"]), (ax2, t["chart_soil"])):
        ax.set_title(title, loc="left", fontsize=9)
        ax.set_xticks([y["year"] for y in variants[0]["years"]])
        _style(ax)
    ax1.axhline(0, color="#9CA3AF", linewidth=0.8)
    fig.legend(*ax1.get_legend_handles_labels(), loc="lower center", ncol=2, fontsize=7.5, frameon=False, bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout()
    return _png(fig)


def stress_chart(variants: list[dict], labels: list[str], year_indexes: list[int], t: dict[str, str]) -> bytes:
    fig, ax = plt.subplots(figsize=(9.2, 2.7))
    width = 0.38
    xs = range(len(variants))
    normal = [v["stress"]["total_normal_kzt_ha"] / 1000 for v in variants]
    dry = [v["stress"]["per_year"][i - 1]["total_if_dry_kzt_ha"] / 1000 for v, i in zip(variants, year_indexes, strict=False)]
    ax.bar([x - width / 2 for x in xs], normal, width, label=t["col_normal"], color=NORMAL)
    ax.bar([x + width / 2 for x in xs], dry, width, label=t["dry_year"], color=DRY)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=8)
    ax.axhline(0, color="#9CA3AF", linewidth=0.8)
    ax.set_title(t["chart_stress"], loc="left", fontsize=9)
    _style(ax)
    ax.legend(fontsize=7.5, frameon=False)
    return _png(fig)
