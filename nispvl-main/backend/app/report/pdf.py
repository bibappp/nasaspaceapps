"""Профессиональный PDF-отчёт по полю (A4, ru / kk / en).

Шрифт DejaVu Sans встроен в PDF: встроенные шрифты PDF не содержат казахских букв.
Все числа и графики берутся из ReportData (данные поля и расчёты модели), ничего не задаётся вручную.
"""
from __future__ import annotations

import io
from datetime import date
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

import yaml
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from ..analytics import scenario_exposure
from ..data_sources import modis as modis_mod
from ..data_sources.registry import source_catalog
from ..model.explain import DECIMAL_POINT, NBSP, fmt_int, fmt_num, years_phrase
from ..model.rules import get_rules
from . import charts
from .fonts import FONT, FONT_BOLD, register_fonts

LOCALE_PATH = Path(__file__).resolve().parent.parent / "locales" / "report.yaml"
W, H = A4
MARGIN = 17 * mm
CONTENT_W = W - 2 * MARGIN

GREEN = colors.HexColor("#1F5134")
GREEN_DARK = colors.HexColor("#123522")
INK = colors.HexColor("#1F2328")
MUTED = colors.HexColor("#6B7280")
LINE = colors.HexColor("#E5E7EB")
SURFACE = colors.HexColor("#F6F7F6")
AMBER = colors.HexColor("#92400E")
LEVEL_COLORS = {"low": colors.HexColor("#1F7A4D"), "moderate": colors.HexColor("#B45309"),
                "high": colors.HexColor("#B42318"), "unknown": MUTED}


@lru_cache
def _strings() -> dict:
    return yaml.safe_load(LOCALE_PATH.read_text(encoding="utf-8"))


def strings(lang: str) -> dict:
    return {k: v[lang] for k, v in _strings().items()}


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=FONT, bulletFontName=FONT, fontSize=9.2, leading=13, textColor=INK)
    return {
        "base": base,
        "small": ParagraphStyle("small", parent=base, fontSize=7.8, leading=10.5, textColor=MUTED),
        "h1": ParagraphStyle("h1", parent=base, fontName=FONT_BOLD, fontSize=14, leading=18, textColor=GREEN_DARK, spaceBefore=4, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base, fontName=FONT_BOLD, fontSize=10.5, leading=14, textColor=INK, spaceBefore=6, spaceAfter=3),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=10.2),
        "cellb": ParagraphStyle("cellb", parent=base, fontName=FONT_BOLD, fontSize=8, leading=10.2),
        "cellh": ParagraphStyle("cellh", parent=base, fontName=FONT_BOLD, fontSize=7.6, leading=9.6, textColor=MUTED),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=10, bulletIndent=0, spaceAfter=2),
        "callout": ParagraphStyle("callout", parent=base, fontName=FONT_BOLD, fontSize=8.8, leading=12, textColor=AMBER,
                                  backColor=colors.HexColor("#FEF6E7"), borderPadding=6, borderColor=colors.HexColor("#F3D9A4"),
                                  borderWidth=0.6, spaceBefore=4, spaceAfter=6),
    }


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _table(rows, widths, header=True, align_right_from: int | None = None) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [
        ("FONT", (0, 0), (-1, -1), FONT, 8),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), SURFACE), ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor("#C9CED6"))]
    if align_right_from is not None:
        st.append(("ALIGN", (align_right_from, 1 if header else 0), (-1, -1), "RIGHT"))
    t.setStyle(TableStyle(st))
    return t


def _kv(rows: list[tuple[str, str]], st) -> Table:
    t = Table([[_p(a, st["cellh"]), _p(b, st["cell"])] for a, b in rows], colWidths=[52 * mm, CONTENT_W - 52 * mm])
    t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), FONT, 8), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _img(png: bytes, width: float) -> Image:
    img = Image(io.BytesIO(png))
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth, img.drawHeight = width, width * ratio
    return img


def _logo(canvas, x, y, size, light=True) -> None:
    """Знак: квадрат со стилизованными строками посева и ростком."""
    canvas.saveState()
    canvas.setFillColor(colors.white if light else GREEN)
    canvas.roundRect(x, y, size, size, size * 0.18, stroke=0, fill=1)
    canvas.setStrokeColor(GREEN if light else colors.white)
    canvas.setLineWidth(size * 0.08)
    canvas.setLineCap(1)
    for i, (x0, x1) in enumerate(((0.2, 0.8), (0.27, 0.73), (0.34, 0.66))):
        yy = y + size * (0.24 + 0.14 * i)
        canvas.line(x + size * x0, yy, x + size * x1, yy)
    canvas.setFillColor(colors.HexColor("#8DBF6A"))
    p = canvas.beginPath()
    p.moveTo(x + size * 0.5, y + size * 0.86)
    p.curveTo(x + size * 0.36, y + size * 0.74, x + size * 0.38, y + size * 0.62, x + size * 0.5, y + size * 0.58)
    p.curveTo(x + size * 0.62, y + size * 0.62, x + size * 0.64, y + size * 0.74, x + size * 0.5, y + size * 0.86)
    canvas.drawPath(p, stroke=0, fill=1)
    canvas.restoreState()


def _name(v: dict, lang: str, t: dict) -> str:
    n = v.get("name")
    if isinstance(n, dict):
        return n.get(lang) or n.get("ru") or v["id"]
    return n or (t["custom_priority"] if v.get("custom") else v["id"])


def build_report(data, *, lang: str = "ru", selected_variant_id: str | None = None, farm_name: str = "",
                 today: date | None = None) -> bytes:
    """data — services.report_data.ReportData. В английском отчёте десятичный разделитель — точка."""
    token = DECIMAL_POINT.set(lang == "en")
    try:
        return _build_report(data, lang=lang, selected_variant_id=selected_variant_id, farm_name=farm_name, today=today)
    finally:
        DECIMAL_POINT.reset(token)


def _build_report(data, *, lang: str, selected_variant_id: str | None, farm_name: str, today: date | None) -> bytes:
    register_fonts()
    rules = get_rules()
    t = strings(lang)
    st = _styles()
    today = today or date.today()
    c, a, seasons, risk = data.comparison, data.analysis, data.seasons, data.risk
    info = data.field_info
    variants = c["variants"]
    by_id = {v["id"]: v for v in variants}
    sel = by_id.get(selected_variant_id or "") or by_id[c["best_variant_id"]]
    n_years = c["horizon_years"]
    yp = years_phrase(n_years)[lang]
    field = a["field"]
    crop = lambda cid, short=True: rules.crop_name(cid, lang, short=short)  # noqa: E731
    chain = lambda v: " → ".join(crop(x) for x in v["crops"])  # noqa: E731
    field_name = info.get("name") or field["region_name"][lang]
    farm = farm_name or info.get("farm_name") or ""
    labels = {k: t[k] for k in ("normal_year", "dry_year", "trend_line", "chart_ndvi_max", "chart_ndvi_curves", "median_band",
                                 "day_of_year", "chart_precip", "chart_smap", "p20_line")}
    story: list = []

    # ================================================================ обложка (рисуется в onPage) + краткие выводы
    story += [NextPageTemplate("content"), PageBreak()]
    d = a["drought"]
    weights = {k: v for k, v in c["weights"].items() if k in ("soil", "water", "income", "risk")}
    base = next((v for v in variants if v["id"] == c.get("baseline_variant_id")), variants[0])
    story.append(_p(t["s_summary"], st["h1"]))
    priority_name = t["custom_priority"] if c.get("weights_custom") else c["priority_name"][lang]
    margin_diff = sel["economics"]["gross_margin_kzt_ha"] - base["economics"]["gross_margin_kzt_ha"]
    risk_high = [i for i in risk["items"] if i["level"] == "high"]
    bullets = [
        t["recommended_intro"].format(name=_name(sel, lang, t), score=fmt_num(sel["weighted_score"], 2)),
        t["weights_text"].format(priority=priority_name, **{k: round(v * 100) for k, v in weights.items()}),
        f"{t['col_margin'].format(n=yp)}: {fmt_int(sel['economics']['gross_margin_kzt_ha'])} "
        f"({'+' if margin_diff >= 0 else '−'}{fmt_int(abs(margin_diff))} — {_name(base, lang, t)}).",
        t["water_text"].format(n=len(d["dry_years"]), total=(d["window"] or {}).get("n_years"), from_year=(d["window"] or {}).get("from"),
                               to_year=(d["window"] or {}).get("to"), years=", ".join(map(str, d["dry_years"])) or "—",
                               stock=fmt_num(c["conditions"]["stock_normal"], 0),
                               basis=t["basis_smap"] if c["conditions"]["moisture_basis"] == "smap" else t["basis_power"]),
    ]
    if risk_high:
        bullets.append(f"{t['col_level']}: {t['level_high']} — " + "; ".join(_risk_label(i, t) for i in risk_high))
    bullets.append(t["driver_confidence"].format(level=t[f"conf_{sel['confidence']['level']}"],
                                                 supported=sel["confidence"]["params_supported"], total=sel["confidence"]["params_total"]))
    bullets.append(t["no_field_yield"])
    for b in bullets:
        story.append(Paragraph(escape(b), st["bullet"], bulletText="•"))
    story.append(_p(t["disclaimer"], st["callout"]))

    # ================================================================ 1. поле
    story.append(_p(f"1. {t['s_field']}", st["h1"]))
    hist = c.get("history") or []
    history_text = ", ".join(f"{h['year']}: {crop(h['crop'])}" for h in hist) or t["not_set"]
    if info.get("history_is_scenario") or field.get("is_demo"):
        history_text += f" ({t['history_scenario']})"
    cen = field["centroid"]
    bb = field["bbox"]
    rows = [
        (t["field_name"], field_name),
        (t["farm"], farm or "—"),
        (t["region"], field["region_name"][lang]),
        (t["area"], f"{fmt_num(field['area_ha'], 1)}{NBSP}{t['ha']}"),
        (t["centroid"], f"{cen['lat']:.5f}, {cen['lon']:.5f}"),
        (t["bbox"], f"{bb[0]:.4f}–{bb[2]:.4f} °E; {bb[1]:.4f}–{bb[3]:.4f} °N"),
        (t["history"], history_text),
    ]
    soil_user = info.get("soil") or {}
    if any(soil_user.get(k) not in (None, "") for k in ("humus_pct", "ph", "texture")):
        rows.append((t["soil_user"], t["soil_user_value"].format(
            humus=fmt_num(soil_user.get("humus_pct"), 1) if soil_user.get("humus_pct") is not None else "—",
            ph=fmt_num(soil_user.get("ph"), 1) if soil_user.get("ph") is not None else "—",
            texture=soil_user.get("texture") or "—", year=soil_user.get("survey_year") or "—")))
    soil = a["soil"]["summary"]
    if soil:
        top = soil["topsoil"]
        rows.append((t["soil_model"], t["soil_value"].format(humus=fmt_num(top["humus_pct"] or 0, 1), clay=fmt_num(top["clay_pct"] or 0, 0),
                                                            sand=fmt_num(top["sand_pct"] or 0, 0), ph=fmt_num(top["ph"] or 0, 1),
                                                            awc=fmt_num(soil["awc_mm"], 0))))
    if info.get("notes"):
        rows.append((t["notes"], info["notes"]))
    story.append(_kv(rows, st))
    m = data.modis
    if m and m.get("rasters"):
        dates = sorted(m["rasters"])
        best_date = max(dates[-10:], key=lambda dt: sum(v for v in m["rasters"][dt] if v is not None))
        png = charts.field_map(field["geometry"], m["grid"], m["rasters"][best_date], m.get("field_mask"), modis_mod.pixel_polygon, labels)
        story += [Spacer(1, 3 * mm), _img(png, 128 * mm), _p(t["map_caption"].format(date=best_date), st["small"])]
    else:
        story += [Spacer(1, 3 * mm), _img(charts.field_map(field["geometry"], None, None, None, None, labels), 110 * mm)]

    # ================================================================ 2. данные и источники
    story += [CondPageBreak(60 * mm), _p(f"2. {t['s_data']}", st["h1"])]
    cat = source_catalog()
    origins = {s["source"]: s.get("origin") for s in a.get("sources", [])}
    periods = {
        "power": f"{a['climate']['series_from']}-01-01 … {a['climate']['series_to']}",
        "modis": (f"{data.ndvi['composites'][0]['date']} … {data.ndvi['composites'][-1]['date']}" if data.ndvi.get("composites") else "—"),
        "smap": (f"{data.smap['days'][0]['date']} … {data.smap['days'][-1]['date']}" if data.smap.get("days") else "—"),
        "soilgrids": "SoilGrids 2.0",
    }
    head = [_p(h, st["cellh"]) for h in (t["col_dataset"], t["col_used"], t["col_period"], t["col_resolution"], t["col_origin"])]
    drows = [head]
    for sid in ("power", "modis", "smap", "soilgrids"):
        meta = cat[sid]
        o = origins.get(sid)
        drows.append([_p(meta["title"], st["cellb"]), _p(meta["used_for"][lang], st["cell"]), _p(periods[sid], st["cell"]),
                      _p(meta["spatial_resolution"][lang], st["cell"]), _p(t.get(f"origin_{o}", t["origin_none"]) if o else t["origin_none"], st["cell"])])
    story.append(_table(drows, [30 * mm, 36 * mm, 30 * mm, 56 * mm, 24 * mm]))
    story.append(Spacer(1, 2 * mm))
    story.append(_p(cat["gpm"]["limitations"][lang], st["small"]))

    # ================================================================ 3. вегетация
    story += [CondPageBreak(90 * mm), _p(f"3. {t['s_vegetation']}", st["h1"])]
    trend = seasons.get("ndvi_trend")
    if trend and trend.get("label") and trend["label"] != "insufficient":
        story.append(_p(t["ndvi_trend_text"].format(from_year=trend["from_year"], to_year=trend["to_year"], label=t[f"ndvi_{trend['label']}"],
                                                    slope=fmt_num(trend["slope_per_year"], 4), p=fmt_num(trend["p_value"], 3)), st["base"]))
        story.append(_img(charts.ndvi_history(seasons["years"], trend, labels), CONTENT_W))
        story.append(_img(charts.ndvi_curves(seasons["ndvi_curves"], seasons["ndvi_climatology"], labels), CONTENT_W))
    else:
        story.append(_p(t["ndvi_missing"], st["base"]))
    story.append(_p(t["ndvi_caveat"], st["small"]))

    # ================================================================ 4. осадки и влага
    story += [CondPageBreak(80 * mm), _p(f"4. {t['s_water']}", st["h1"])]
    w0 = (d["window"] or {}).get("from", 2002)
    story.append(_img(charts.precip_history(seasons["years"], d["definition"]["percentile_mm"], w0, labels), CONTENT_W))
    smap_png = charts.smap_history(seasons["years"], labels)
    if smap_png:
        story.append(_img(smap_png, CONTENT_W))
    story.append(_p(cat["smap"]["spatial_resolution"][lang], st["small"]))

    # ================================================================ 5. тенденции и риски
    story += [CondPageBreak(60 * mm), _p(f"5. {t['s_risk']}", st["h1"])]
    rrows = [[_p(h, st["cellh"]) for h in (t["col_indicator"], t["col_value"], t["col_reference"], t["col_level"], t["col_kind"])]]
    for i in risk["items"]:
        lvl = Paragraph(f'<font color="{LEVEL_COLORS[i["level"]].hexval()}">■</font> {escape(t["level_" + i["level"]])}', st["cell"])
        rrows.append([_p(_risk_label(i, t), st["cell"]), _p(_risk_value(i, t), st["cell"]), _p(_risk_ref(i), st["cell"]), lvl,
                      _p(t["kind_" + i["kind"]] if f"kind_{i['kind']}" in t else i["kind"], st["cell"])])
    story.append(_table(rrows, [70 * mm, 28 * mm, 28 * mm, 24 * mm, 26 * mm]))

    # ================================================================ 6. сравнение
    story += [PageBreak(), _p(f"6. {t['s_compare']}", st["h1"])]
    story.append(_p(t["weights_text"].format(priority=priority_name, **{k: round(v * 100) for k, v in weights.items()}), st["base"]))
    head = [_p(h, st["cellh"]) for h in (t["col_scenario"], t["col_soil"], t["col_water"], t["col_income"], t["col_risk"],
                                          t["col_weighted"], t["col_margin"].format(n=yp), t["col_confidence"])]
    crows = [head]
    for i, v in enumerate(variants):
        star = "★ " if v["fits_priority"] else ""
        crows.append([Paragraph(f"<b>{star}{i + 1}. {escape(_name(v, lang, t))}</b><br/>{escape(chain(v))}", st["cell"])]
                     + [fmt_num(v["scores"][k]["score"], 1) for k in ("soil", "water", "income", "risk")]
                     + [fmt_num(v["weighted_score"], 2), fmt_int(v["economics"]["gross_margin_kzt_ha"]), t[f"conf_{v['confidence']['level']}"]])
    story.append(_table(crows, [56 * mm, 13 * mm, 13 * mm, 14 * mm, 13 * mm, 14 * mm, 30 * mm, 21 * mm], align_right_from=1))
    story.append(_p(t["scores_note"], st["small"]))

    # ================================================================ 7. оценки
    story += [Spacer(1, 3 * mm), _p(f"7. {t['s_assess']}", st["h1"])]
    head = [_p(h, st["cellh"]) for h in ("#", t["col_n"], t["col_humus"], t["col_soil_index"], t["col_deficit"], t["col_drought_loss"],
                                          t["col_bare_days"], t["col_exposure"])]
    # дни без покрова и индекс эрозии необязательны (в анализах до задачи 5 их нет) — тогда «—»
    arows = [head] + [[str(i + 1), fmt_num(v["totals"]["nitrogen_kg_ha"], 0), fmt_num(v["totals"]["humus_t_ha"], 1),
                       fmt_num(v["totals"]["soil_index_end"], 1), fmt_num(v["totals"]["water_deficit_mean_mm"], 0),
                       fmt_num(v["totals"]["drought_loss_pct"], 1),
                       fmt_num(v["bare_days_per_year"], 0) if v.get("bare_days_per_year") is not None else "—",
                       fmt_num(v["exposure_index"], 2) if v.get("exposure_index") is not None else "—"]
                      for i, v in enumerate(variants)]
    story.append(_table(arows, [10 * mm, 22 * mm, 20 * mm, 22 * mm, 26 * mm, 26 * mm, 24 * mm, 26 * mm], align_right_from=1))
    story.append(_p(escape(scenario_exposure.report_note(c, t, crop, float(rules.erosion["erosive_wind"]["speed_ms"].value),
                                                         fmt_num, lang)), st["small"]))
    story.append(Spacer(1, 3 * mm))
    head = [_p(h, st["cellh"]) for h in ("#", t["col_revenue"], t["col_cost"], t["col_gross"], t["col_price_minus"], t["col_price_plus"])]
    erows = [head] + [[str(i + 1)] + [fmt_int(v["economics"][k]) for k in ("revenue_kzt_ha", "cost_kzt_ha", "gross_margin_kzt_ha",
                                                                           "margin_price_minus20_kzt_ha", "margin_price_plus20_kzt_ha")]
                      for i, v in enumerate(variants)]
    story.append(_table(erows, [12 * mm, 32 * mm, 32 * mm, 32 * mm, 34 * mm, 34 * mm], align_right_from=1))
    story.append(_p(t["econ_note"], st["small"]))

    # ================================================================ 8. многолетняя симуляция
    story += [CondPageBreak(90 * mm), _p(f"8. {t['s_forecast']}", st["h1"])]
    short = [f"{i + 1}. {chain(v)}" for i, v in enumerate(variants)]
    story.append(_img(charts.forecast_chart(variants, short, t), CONTENT_W))
    story.append(_p(t["forecast_note"], st["small"]))

    # ================================================================ 9. стресс-тест
    story += [CondPageBreak(90 * mm), _p(f"9. {t['s_stress']}", st["h1"])]
    dy = c["conditions"]["dry_year"]
    srow = next((r for r in seasons["years"] if r["year"] == dy), {})
    story.append(_p(t["stress_conditions"].format(
        year=dy, precip=fmt_num(srow.get("precip_mm"), 0), normal=fmt_num(d["definition"]["baseline_mean_mm"], 0),
        z=fmt_num(srow.get("precip_anomaly_z"), 2), stock=fmt_num(c["conditions"]["stock_dry"], 0),
        ndvi=fmt_num(srow.get("ndvi_max"), 2) if srow.get("ndvi_max") is not None else "—"), st["base"]))
    story.append(_p(t["stress_method"], st["small"]))
    idx = [v["stress"]["worst_year_index"] for v in variants]
    s_rows = [[_p(h, st["cellh"]) for h in (t["col_scenario"], t["col_normal"], t["col_dry"], t["col_loss"])]]
    for i, v in enumerate(variants):
        py = v["stress"]["per_year"][idx[i] - 1]
        s_rows.append([_p(short[i], st["cell"]), fmt_int(v["stress"]["total_normal_kzt_ha"]),
                       f"{fmt_int(py['total_if_dry_kzt_ha'])} ({py['year']})", "−" + fmt_int(py["loss_kzt_ha"])])
    story.append(_table(s_rows, [86 * mm, 30 * mm, 34 * mm, 26 * mm], align_right_from=1))
    story.append(_img(charts.stress_chart(variants, [str(i + 1) for i in range(len(variants))], idx, t), CONTENT_W))

    # ================================================================ 10. рекомендованный сценарий
    story += [PageBreak(), _p(f"10. {t['s_recommended']}", st["h1"])]
    story.append(_p(f"{_name(sel, lang, t)}: {chain(sel)}", st["h2"]))
    story.append(_p(t["recommended_intro"].format(name=_name(sel, lang, t), score=fmt_num(sel["weighted_score"], 2)), st["base"]))
    y_rows = [[_p(h, st["cellh"]) for h in (t["col_year"], t["col_crop"], t["col_yield"], t["col_margin_year"], t["col_margin_dry"], t["col_soil_index"])]]
    for y in sel["years"]:
        y_rows.append([str(y["year"]), _p(crop(y["crop"], short=False), st["cell"]), fmt_num(y["yield_t_ha"], 2),
                       fmt_int(y["income_kzt_ha"]), fmt_int(y["income_dry_kzt_ha"]), fmt_num(y["soil_index"], 1)])
    story.append(_table(y_rows, [16 * mm, 44 * mm, 28 * mm, 30 * mm, 34 * mm, 24 * mm], align_right_from=2))
    story.append(_p(t["why"], st["h2"]))
    for line in sel.get("explanation", []):
        story.append(Paragraph(escape(line.get(lang) or line["ru"]), st["bullet"], bulletText="•"))
    story.append(_p(t["drivers"], st["h2"]))
    for line in (
        t["driver_conditions"].format(water=fmt_num(c["normal_water_mm"], 0), ref=fmt_num(c["reference_water_mm"], 0), nth=d["every_nth"] or "—"),
        t["driver_datasets"],
        t["driver_confidence"].format(level=t[f"conf_{sel['confidence']['level']}"], supported=sel["confidence"]["params_supported"],
                                      total=sel["confidence"]["params_total"]),
        t["no_field_yield"],
    ):
        story.append(Paragraph(escape(line), st["bullet"], bulletText="•"))

    # ================================================================ 11. допущения
    story += [CondPageBreak(60 * mm), _p(f"11. {t['s_assumptions']}", st["h1"]), _p(t["assumptions_intro"], st["small"]), Spacer(1, 2 * mm)]
    params = {}
    for key in ("soil", "water", "income", "risk"):
        for prm in sel["scores"][key]["params"]:
            params[prm["path"]] = prm
    p_rows = [[_p(h, st["cellh"]) for h in (t["col_param"], t["col_value"], t["col_status"], t["col_evidence"], t["col_source"])]]
    for prm in sorted(params.values(), key=lambda x: x["path"]):
        val = prm["value"] if not isinstance(prm["value"], dict) else ", ".join(f"{k} {v}" for k, v in prm["value"].items())
        p_rows.append([_p(prm["path"], st["cell"]), _p(f"{val} {prm['unit']}", st["cell"]), _p(prm["status"], st["cell"]),
                       _p(t.get(f"ev_{prm.get('evidence')}", prm.get("evidence", "")), st["cell"]), _p(prm["source"][:140], st["small"])])
    story.append(_table(p_rows, [46 * mm, 24 * mm, 21 * mm, 22 * mm, 63 * mm]))

    # ================================================================ 12. ограничения
    story += [CondPageBreak(50 * mm), _p(f"12. {t['s_limitations']}", st["h1"])]
    for line in t["limitations"]:
        story.append(Paragraph(escape(line), st["bullet"], bulletText="•"))

    # ================================================================ 13. источники и литература
    story += [CondPageBreak(50 * mm), _p(f"13. {t['s_references']}", st["h1"])]
    for sid in ("power", "modis", "smap", "soilgrids", "gpm"):
        meta = cat[sid]
        ref = f"{meta['title']}. {meta['provider']}. {meta['url']}" + (f" DOI: {meta['doi']}" if meta.get("doi") else "")
        story.append(Paragraph(escape(ref), st["bullet"], bulletText="•"))
    used_sources = {}
    for prm in params.values():
        if prm.get("url", "").startswith("http"):
            used_sources[prm["source"]] = prm["url"]
    for name, url in sorted(used_sources.items()):
        story.append(Paragraph(escape(f"{name}. {url}"), st["bullet"], bulletText="•"))

    # ================================================================ подписи
    story += [CondPageBreak(55 * mm), _p(t["s_sign"], st["h1"])]
    sign = Table([[_p(t["sign_farm"], st["cell"]), farm], [_p(t["sign_farmer"], st["cell"]), ""], [_p(t["sign_agronomist"], st["cell"]), ""],
                  [_p(t["sign_date"], st["cell"]), ""]], colWidths=[50 * mm, CONTENT_W - 50 * mm], rowHeights=[11 * mm] * 4)
    sign.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), FONT, 9), ("LINEBELOW", (1, 0), (1, -1), 0.6, INK), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    story += [KeepTogether([sign]), Spacer(1, 4 * mm), _p(t["generated_by"].format(date=today.strftime("%d.%m.%Y")), st["small"])]

    # ================================================================ оформление страниц
    def cover(canvas, doc) -> None:
        canvas.saveState()
        band = H * 0.46
        canvas.setFillColor(GREEN_DARK)
        canvas.rect(0, H - band, W, band, stroke=0, fill=1)
        canvas.setFillColor(GREEN)
        canvas.rect(0, H - band, W, 6 * mm, stroke=0, fill=1)
        _logo(canvas, MARGIN, H - 34 * mm, 13 * mm)
        canvas.setFillColor(colors.white)
        canvas.setFont(FONT_BOLD, 15)
        canvas.drawString(MARGIN + 17 * mm, H - 26.5 * mm, t["brand"])
        canvas.setFont(FONT, 8.5)
        canvas.setFillColor(colors.HexColor("#CFE3D4"))
        canvas.drawString(MARGIN + 17 * mm, H - 32 * mm, t["brand_tagline"])
        canvas.setFillColor(colors.white)
        canvas.setFont(FONT_BOLD, 24)
        canvas.drawString(MARGIN, H - band + 52 * mm, t["title"])
        canvas.setFont(FONT, 15)
        canvas.drawString(MARGIN, H - band + 40 * mm, field_name[:60])
        canvas.setFont(FONT, 10)
        canvas.setFillColor(colors.HexColor("#CFE3D4"))
        canvas.drawString(MARGIN, H - band + 31 * mm,
                          f"{field['region_name'][lang]} · {fmt_num(field['area_ha'], 1)} {t['ha']} · {cen['lat']:.4f}° N, {cen['lon']:.4f}° E")
        canvas.drawString(MARGIN, H - band + 24 * mm, f"{t['date']}: {today.strftime('%d.%m.%Y')}" + (f" · {t['prepared_for']}: {farm}" if farm else ""))
        # блок ключевых фактов
        y0 = H - band - 18 * mm
        facts = [
            (t["s_recommended"], f"{_name(sel, lang, t)} — {chain(sel)}"),
            (t["col_margin"].format(n=yp), fmt_int(sel["economics"]["gross_margin_kzt_ha"])),
            (t["col_confidence"], t[f"conf_{sel['confidence']['level']}"]),
            (t["risk_drought_frequency"].format(period=f"{(d['window'] or {}).get('from')}–{(d['window'] or {}).get('to')}"),
             f"{len(d['dry_years'])} / {(d['window'] or {}).get('n_years')}"),
        ]
        for i, (label, value) in enumerate(facts):
            yy = y0 - i * 15 * mm
            canvas.setFillColor(MUTED)
            canvas.setFont(FONT, 8)
            canvas.drawString(MARGIN, yy, label)
            canvas.setFillColor(INK)
            canvas.setFont(FONT_BOLD, 11.5)
            canvas.drawString(MARGIN, yy - 5.5 * mm, value[:85])
            canvas.setStrokeColor(LINE)
            canvas.line(MARGIN, yy - 9 * mm, W - MARGIN, yy - 9 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont(FONT, 7.8)
        tx = canvas.beginText(MARGIN, 34 * mm)
        tx.setLeading(10)
        for chunk in _wrap(t["cover_note"], 120):
            tx.textLine(chunk)
        canvas.drawText(tx)
        canvas.setFillColor(AMBER)
        canvas.setFont(FONT_BOLD, 8)
        canvas.drawString(MARGIN, 18 * mm, t["disclaimer"][:150])
        canvas.restoreState()

    def page(canvas, doc) -> None:
        canvas.saveState()
        _logo(canvas, MARGIN, H - 12 * mm, 5.5 * mm, light=False)
        canvas.setFont(FONT_BOLD, 8)
        canvas.setFillColor(INK)
        canvas.drawString(MARGIN + 7.5 * mm, H - 10.2 * mm, t["brand"])
        canvas.setFont(FONT, 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(W - MARGIN, H - 10.2 * mm, f"{field_name[:50]} · {today.strftime('%d.%m.%Y')}")
        canvas.setStrokeColor(LINE)
        canvas.line(MARGIN, H - 14 * mm, W - MARGIN, H - 14 * mm)
        canvas.line(MARGIN, 13 * mm, W - MARGIN, 13 * mm)
        canvas.setFont(FONT, 7)
        canvas.drawString(MARGIN, 9 * mm, t["disclaimer"][:140])
        canvas.drawRightString(W - MARGIN, 9 * mm, f"{t['page']} {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=20 * mm, bottomMargin=18 * mm,
                          title=f"{t['title']} — {field_name}", author="Agro-Sevooborot",
                          lang={"kk": "kk-KZ", "en": "en-GB"}.get(lang, "ru-RU"), initialFontName=FONT, initialFontSize=9)
    frame = Frame(MARGIN, 18 * mm, CONTENT_W, H - 38 * mm, id="body")
    doc.addPageTemplates([PageTemplate("cover", [frame], onPage=cover), PageTemplate("content", [frame], onPage=page)])
    doc.build(story)
    return buf.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


def _risk_label(i: dict, t: dict) -> str:
    tpl = t.get(f"risk_{i['id']}", i["id"])
    period = i.get("period") or ""
    if i["id"] == "drought_frequency" and period:
        period = period.replace("/", "–")
    return tpl.format(period=period, threshold=fmt_num(i.get("threshold_c", 30), 0))


def _risk_value(i: dict, t: dict) -> str:
    v = i.get("value")
    if v is None:
        return "—"
    unit = {"mm": f" {t['mm']}", "°C": " °C", "days": "", "m3/m3": " m³/m³", "%": " %", "share": "", "NDVI": "", "0-1": ""}.get(i.get("unit", ""), "")
    if i.get("unit") == "share":
        return f"{round(v * 100)} %"
    digits = 3 if i.get("unit") in ("m3/m3", "NDVI", "0-1") else 1
    return f"{fmt_num(v, digits)}{unit}"


def _risk_ref(i: dict) -> str:
    if i.get("reference") is not None:
        z = f" (z = {fmt_num(i['z'], 2)})" if i.get("z") is not None else ""
        return f"{fmt_num(i['reference'], 1 if i.get('unit') != 'NDVI' else 3)}{z}"
    if i.get("ratio") is not None:
        return f"× {fmt_num(i['ratio'], 2)}"
    if i.get("every_nth"):
        return f"1 / {i['every_nth']}"
    return "—"
