"""XLSX-книга по полю: шесть листов, прозрачные формулы, фильтры, закреплённые заголовки, графики.

Источник всех чисел — services.report_data.ReportData (те же данные, что в PDF). Пропуски остаются
пустыми ячейками: ничего не подставляется.
"""
from __future__ import annotations

import io
import json
from datetime import date

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from ..analytics import scenario_exposure
from ..data_sources.registry import source_catalog
from ..model.rules import get_rules
from .pdf import strings as report_strings

GREEN = "1F5134"
HEADER_FILL = PatternFill("solid", fgColor="EEF3EF")
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color=GREEN)
HEAD_FONT = Font(name="Calibri", size=10, bold=True, color="1F2328")
NOTE_FONT = Font(name="Calibri", size=9, italic=True, color="6B7280")
THIN = Border(bottom=Side(style="thin", color="D1D5DB"))
WRAP = Alignment(wrap_text=True, vertical="top")

L = {
    "ru": {
        "s1": "Обзор поля", "s2": "Данные среды", "s3": "Сравнение сценариев", "s4": "История сезонов", "s5": "Допущения модели",
        "s6": "Источники и методика",
        "title": "Агро-Севооборот — данные поля", "field": "Поле", "farm": "Хозяйство", "region": "Область", "area": "Площадь, га",
        "centroid": "Центр (широта, долгота)", "bbox": "Границы (мин. долгота, мин. широта, макс. долгота, макс. широта)",
        "boundary": "Контур (GeoJSON)", "history": "История культур", "analysis_date": "Дата анализа", "priority": "Приоритет",
        "weights": "Веса оценок (почва, вода, доход, риск)", "scenario_note": "История культур — учебный сценарий", "notes": "Заметки",
        "month": "Месяц", "precip": "Осадки, мм", "precip_normal": "Норма осадков 1991–2020, мм", "precip_pct": "% нормы",
        "t_mean": "Температура средняя, °C", "t_anom": "Аномалия температуры, °C", "hot": "Жаркие дни (Tmax ≥ 30 °C)",
        "gwet": "Влажность корнеобитаемого слоя POWER (0–1)", "ndvi": "NDVI (среднее композитов месяца)",
        "sm": "Влажность почвы SMAP, м³/м³", "src": "Источники", "units_note": "Осадки, температура, GWETROOT — NASA POWER (реанализ, ячейка ~50 км); NDVI — MODIS MOD13Q1 (250 м); SMAP — SPL3SMP_E (9 км, апрель–май). Пустая ячейка — нет данных.",
        "scenario": "Сценарий", "crops": "Цепочка культур", "soil": "Почва (1–5)", "water": "Вода (1–5)", "income": "Доход (1–5)",
        "risk": "Риск (1–5)", "score": "Взвешенный балл (формула)", "n": "Баланс N, кг/га", "humus": "Гумус, т/га",
        "soil_idx": "Индекс почвы в конце", "deficit": "Дефицит влаги, мм/год", "revenue": "Выручка, тг/га", "cost": "Затраты, тг/га",
        "margin": "Валовая маржа, тг/га (формула)", "m_minus": "Маржа при цене −20 % (формула)", "m_plus": "Маржа при цене +20 % (формула)",
        "loss": "Потеря выручки в засуху, %", "confidence": "Уверенность", "conf_share": "Доля подтверждённых параметров",
        "weight_row": "Вес", "detail": "Расчёт по годам", "year": "Год", "crop": "Культура", "yield": "Урожайность, т/га",
        "price": "Цена, тг/т", "cost_y": "Затраты, тг/га", "margin_y": "Маржа, тг/га (= урожайность × цена − затраты)",
        "yield_dry": "Урожайность в засуху, т/га", "pred": "Эффект предшественника, %", "moist": "Коэффициент влаги",
        "best": "Лучше подходит приоритету",
        "season": "Сезон", "p_season": "Осадки май–август, мм", "p_anom": "Аномалия осадков (z)", "p_diff": "Отклонение от нормы, мм (формула)",
        "dry": "Засушливый год", "t_season": "Температура май–август, °C", "t_diff": "Аномалия температуры, °C (формула)",
        "ndvi_max": "Максимум NDVI", "ndvi_mean": "Средний NDVI сезона", "smap_spring": "SMAP апрель–май, м³/м³",
        "smap_ratio": "SMAP к медиане", "baseline": "Норма 1991–2020", "average": "Среднее за окно",
        "param": "Параметр", "value": "Значение", "unit": "Единица", "source": "Источник", "url": "Ссылка", "status": "Статус",
        "evidence": "Класс обоснованности", "note": "Пояснение",
        "dataset": "Набор данных", "provider": "Поставщик", "resolution": "Пространственное разрешение", "coverage": "Временной охват",
        "processing": "Обработка в проекте", "limits": "Ограничения", "doi": "DOI / ссылка",
        "chart_precip": "Осадки май–август по годам", "chart_ndvi": "Максимум NDVI по годам", "chart_margin": "Валовая маржа по сценариям",
        "yes": "да", "no": "нет",
    },
    "kk": {
        "s1": "Егістікке шолу", "s2": "Орта деректері", "s3": "Сценарийлерді салыстыру", "s4": "Маусымдар тарихы", "s5": "Модель болжамдары",
        "s6": "Дереккөздер мен әдістеме",
        "title": "Агро-Ауыспалы егіс — егістік деректері", "field": "Егістік", "farm": "Шаруашылық", "region": "Облыс", "area": "Ауданы, га",
        "centroid": "Ортасы (ендік, бойлық)", "bbox": "Шекаралар (мин. бойлық, мин. ендік, макс. бойлық, макс. ендік)",
        "boundary": "Контур (GeoJSON)", "history": "Дақылдар тарихы", "analysis_date": "Талдау күні", "priority": "Басымдық",
        "weights": "Бағалардың салмағы (топырақ, су, табыс, тәуекел)", "scenario_note": "Дақылдар тарихы — оқу сценарийі", "notes": "Ескертпелер",
        "month": "Ай", "precip": "Жауын-шашын, мм", "precip_normal": "1991–2020 жауын-шашын нормасы, мм", "precip_pct": "Нормаға %",
        "t_mean": "Орташа температура, °C", "t_anom": "Температура аномалиясы, °C", "hot": "Ыстық күндер (Tmax ≥ 30 °C)",
        "gwet": "POWER тамыр қабатының ылғалдылығы (0–1)", "ndvi": "NDVI (айдағы композиттердің орташасы)",
        "sm": "SMAP топырақ ылғалдылығы, м³/м³", "src": "Дереккөздер", "units_note": "Жауын-шашын, температура, GWETROOT — NASA POWER (реанализ, ~50 км ұяшық); NDVI — MODIS MOD13Q1 (250 м); SMAP — SPL3SMP_E (9 км, сәуір–мамыр). Бос ұяшық — дерек жоқ.",
        "scenario": "Сценарий", "crops": "Дақылдар тізбегі", "soil": "Топырақ (1–5)", "water": "Су (1–5)", "income": "Табыс (1–5)",
        "risk": "Тәуекел (1–5)", "score": "Өлшенген ұпай (формула)", "n": "N балансы, кг/га", "humus": "Гумус, т/га",
        "soil_idx": "Соңындағы топырақ индексі", "deficit": "Ылғал тапшылығы, мм/жыл", "revenue": "Түсім, тг/га", "cost": "Шығындар, тг/га",
        "margin": "Жалпы маржа, тг/га (формула)", "m_minus": "Баға −20 % кезіндегі маржа (формула)", "m_plus": "Баға +20 % кезіндегі маржа (формула)",
        "loss": "Құрғақшылықтағы түсім шығыны, %", "confidence": "Сенімділік", "conf_share": "Расталған параметрлер үлесі",
        "weight_row": "Салмақ", "detail": "Жылдар бойынша есеп", "year": "Жыл", "crop": "Дақыл", "yield": "Өнімділік, т/га",
        "price": "Баға, тг/т", "cost_y": "Шығындар, тг/га", "margin_y": "Маржа, тг/га (= өнімділік × баға − шығындар)",
        "yield_dry": "Құрғақшылықтағы өнімділік, т/га", "pred": "Алғы дақыл әсері, %", "moist": "Ылғал коэффициенті",
        "best": "Басымдыққа ең сәйкес",
        "season": "Маусым", "p_season": "Мамыр–тамыз жауын-шашыны, мм", "p_anom": "Жауын-шашын аномалиясы (z)", "p_diff": "Нормадан ауытқу, мм (формула)",
        "dry": "Құрғақшылық жыл", "t_season": "Мамыр–тамыз температурасы, °C", "t_diff": "Температура аномалиясы, °C (формула)",
        "ndvi_max": "Ең жоғары NDVI", "ndvi_mean": "Маусымдық орташа NDVI", "smap_spring": "SMAP сәуір–мамыр, м³/м³",
        "smap_ratio": "SMAP медианаға қатысты", "baseline": "1991–2020 нормасы", "average": "Терезе бойынша орташа",
        "param": "Параметр", "value": "Мәні", "unit": "Бірлік", "source": "Дереккөз", "url": "Сілтеме", "status": "Мәртебесі",
        "evidence": "Негізділік класы", "note": "Түсіндірме",
        "dataset": "Деректер жиыны", "provider": "Жеткізуші", "resolution": "Кеңістіктік ажыратымдылық", "coverage": "Уақыт бойынша қамту",
        "processing": "Жобадағы өңдеу", "limits": "Шектеулер", "doi": "DOI / сілтеме",
        "chart_precip": "Жылдар бойынша мамыр–тамыз жауын-шашыны", "chart_ndvi": "Жылдар бойынша ең жоғары NDVI", "chart_margin": "Сценарийлер бойынша жалпы маржа",
        "yes": "иә", "no": "жоқ",
    },
    "en": {
        "s1": "Field Overview", "s2": "Environmental Data", "s3": "Crop Rotation Comparison", "s4": "Historical Analysis", "s5": "Model Assumptions",
        "s6": "Sources and Methodology",
        "title": "Agro-Sevooborot — field data", "field": "Field", "farm": "Farm", "region": "Region", "area": "Area, ha",
        "centroid": "Centre (lat, lon)", "bbox": "Bounding box (min lon, min lat, max lon, max lat)",
        "boundary": "Boundary (GeoJSON)", "history": "Crop history", "analysis_date": "Analysis date", "priority": "Priority",
        "weights": "Score weights (soil, water, income, risk)", "scenario_note": "Crop history is a training scenario", "notes": "Notes",
        "month": "Month", "precip": "Precipitation, mm", "precip_normal": "Precipitation normal 1991–2020, mm", "precip_pct": "% of normal",
        "t_mean": "Mean temperature, °C", "t_anom": "Temperature anomaly, °C", "hot": "Hot days (Tmax ≥ 30 °C)",
        "gwet": "POWER root-zone wetness (0–1)", "ndvi": "NDVI (mean of month composites)",
        "sm": "SMAP soil moisture, m³/m³", "src": "Sources", "units_note": "Precipitation, temperature, GWETROOT: NASA POWER (reanalysis, ~50 km cell); NDVI: MODIS MOD13Q1 (250 m); SMAP: SPL3SMP_E (9 km, April–May). An empty cell means no data.",
        "scenario": "Scenario", "crops": "Crop sequence", "soil": "Soil (1–5)", "water": "Water (1–5)", "income": "Income (1–5)",
        "risk": "Risk (1–5)", "score": "Weighted score (formula)", "n": "N balance, kg/ha", "humus": "Humus, t/ha",
        "soil_idx": "Soil index at end", "deficit": "Water deficit, mm/yr", "revenue": "Revenue, KZT/ha", "cost": "Costs, KZT/ha",
        "margin": "Gross margin, KZT/ha (formula)", "m_minus": "Margin at price −20 % (formula)", "m_plus": "Margin at price +20 % (formula)",
        "loss": "Revenue loss in drought, %", "confidence": "Confidence", "conf_share": "Share of supported parameters",
        "weight_row": "Weight", "detail": "Year-by-year calculation", "year": "Year", "crop": "Crop", "yield": "Yield, t/ha",
        "price": "Price, KZT/t", "cost_y": "Costs, KZT/ha", "margin_y": "Margin, KZT/ha (= yield × price − costs)",
        "yield_dry": "Yield in drought, t/ha", "pred": "Predecessor effect, %", "moist": "Moisture coefficient",
        "best": "Best fit for priority",
        "season": "Season", "p_season": "May–August precipitation, mm", "p_anom": "Precipitation anomaly (z)", "p_diff": "Departure from normal, mm (formula)",
        "dry": "Dry year", "t_season": "May–August temperature, °C", "t_diff": "Temperature anomaly, °C (formula)",
        "ndvi_max": "NDVI maximum", "ndvi_mean": "Seasonal mean NDVI", "smap_spring": "SMAP April–May, m³/m³",
        "smap_ratio": "SMAP relative to median", "baseline": "Normal 1991–2020", "average": "Window average",
        "param": "Parameter", "value": "Value", "unit": "Unit", "source": "Source", "url": "Link", "status": "Status",
        "evidence": "Evidence class", "note": "Explanation",
        "dataset": "Dataset", "provider": "Provider", "resolution": "Spatial resolution", "coverage": "Temporal coverage",
        "processing": "Processing in this project", "limits": "Limitations", "doi": "DOI / link",
        "chart_precip": "May–August precipitation by year", "chart_ndvi": "NDVI maximum by year", "chart_margin": "Gross margin by scenario",
        "yes": "yes", "no": "no",
    },
}

PROCESSING = {
    "power": {"ru": "Суточный ряд в точке центра поля; суммы осадков май–август, помесячные агрегаты, нормы 1991–2020, аномалии.",
              "kk": "Егістік ортасындағы тәуліктік қатар; мамыр–тамыз жауын-шашынының қосындысы, айлық агрегаттар, 1991–2020 нормалары, аномалиялар.",
              "en": "Daily series at the field centre; May–August totals, monthly aggregates, 1991–2020 normals and anomalies."},
    "modis": {"ru": "10 композитов сезона в год; пиксели с pixel_reliability 0–1, центр которых внутри контура; среднее по полю, максимум сезона, тренд.",
              "kk": "Жылына маусымның 10 композиті; ортасы контур ішінде, pixel_reliability 0–1 пиксельдер; егістік бойынша орташа, маусым максимумы, тренд.",
              "en": "10 seasonal composites per year; pixels with pixel_reliability 0–1 whose centre is inside the boundary; field mean, seasonal maximum, trend."},
    "smap": {"ru": "Окно 3×3 ячейки через OPeNDAP; утренние и вечерние ретривы с флагом рекомендуемого качества; апрель–май; отношение к медиане лет.",
             "kk": "OPeNDAP арқылы 3×3 ұяшық терезесі; ұсынылған сапа белгісі бар таңғы және кешкі ретривтер; сәуір–мамыр; жылдар медианасына қатынас.",
             "en": "3×3-cell window via OPeNDAP; AM and PM retrievals with the recommended-quality flag; April–May; ratio to the multi-year median."},
    "soilgrids": {"ru": "Точка центра поля, слои 0–100 см; влагоёмкость по Saxton & Rawls (2006).",
                  "kk": "Егістік ортасындағы нүкте, 0–100 см қабаттар; ылғал сыйымдылығы Saxton & Rawls (2006) бойынша.",
                  "en": "Field-centre point, 0–100 cm layers; water-holding capacity by Saxton & Rawls (2006)."},
    "gpm": {"ru": "Не используется (см. ограничения).", "kk": "Пайдаланылмайды (шектеулерді қараңыз).", "en": "Not used (see limitations)."},
    "landsat": {"ru": "Не используется (заготовка модуля).", "kk": "Пайдаланылмайды (модуль дайындамасы).", "en": "Not used (placeholder module)."},
}


def _header(ws: Worksheet, row: int, headers: list[str], widths: list[int] | None = None) -> None:
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=i, value=h)
        c.font, c.fill, c.alignment, c.border = HEAD_FONT, HEADER_FILL, Alignment(wrap_text=True, vertical="center"), THIN
    if widths:
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 32


def _finish(ws: Worksheet, header_row: int, last_row: int, last_col: int) -> None:
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    if last_row > header_row:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(last_col)}{last_row}"


def build_workbook(data, *, lang: str = "ru") -> bytes:
    rules = get_rules()
    t = L[lang]
    rs = report_strings(lang)  # строки locales/report.yaml — те же, что в PDF
    c, a, seasons = data.comparison, data.analysis, data.seasons
    info = data.field_info
    field = a["field"]
    crop = lambda cid: rules.crop_name(cid, lang, short=False)  # noqa: E731
    wb = Workbook()

    # ---------------------------------------------------------------- 1. обзор поля
    ws = wb.active
    ws.title = t["s1"][:31]
    ws["A1"] = t["title"]
    ws["A1"].font = TITLE_FONT
    weights = {k: v for k, v in c["weights"].items() if k in ("soil", "water", "income", "risk")}
    rows = [
        (t["field"], info.get("name") or ""), (t["farm"], info.get("farm_name") or ""), (t["region"], field["region_name"][lang]),
        (t["area"], field["area_ha"]), (t["centroid"], f"{field['centroid']['lat']:.5f}, {field['centroid']['lon']:.5f}"),
        (t["bbox"], ", ".join(f"{x:.5f}" for x in field["bbox"])),
        (t["boundary"], json.dumps(field["geometry"])),
        (t["history"], "; ".join(f"{h['year']}: {crop(h['crop'])}" for h in c.get("history", [])) or ""),
        (t["analysis_date"], data.generated.isoformat()),
        (t["priority"], c["priority_name"][lang] if not c.get("weights_custom") else "custom"),
        (t["weights"], ", ".join(f"{round(weights[k] * 100)} %" for k in ("soil", "water", "income", "risk"))),
    ]
    if info.get("history_is_scenario") or field.get("is_demo"):
        rows.append((t["scenario_note"], t["yes"]))
    if info.get("notes"):
        rows.append((t["notes"], info["notes"]))
    for i, (k, v) in enumerate(rows, start=3):
        ws.cell(row=i, column=1, value=k).font = HEAD_FONT
        cell = ws.cell(row=i, column=2, value=v)
        cell.alignment = WRAP
    ws["B6"].number_format = "#,##0.0"
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 90

    # ---------------------------------------------------------------- 2. данные среды (помесячно)
    ws = wb.create_sheet(t["s2"][:31])
    ndvi_m: dict[str, list[float]] = {}
    for r in data.ndvi.get("composites", []):
        if r["ndvi"] is not None:
            ndvi_m.setdefault(r["date"][:7], []).append(r["ndvi"])
    sm_m: dict[str, list[float]] = {}
    for r in data.smap.get("days", []):
        sm_m.setdefault(r["date"][:7], []).append(r["sm"])
    head = [t["month"], t["precip"], t["precip_normal"], t["precip_pct"], t["t_mean"], t["t_anom"], t["hot"], t["gwet"], t["ndvi"], t["sm"], t["src"]]
    _header(ws, 1, head, [10, 13, 16, 10, 14, 14, 13, 16, 16, 16, 34])
    row = 2
    for m in data.climate_monthly["months"]:
        nd = ndvi_m.get(m["month"])
        sm = sm_m.get(m["month"])
        srcs = ["NASA POWER"] + (["MODIS MOD13Q1"] if nd else []) + (["SMAP SPL3SMP_E"] if sm else [])
        ws.cell(row=row, column=1, value=m["month"])
        ws.cell(row=row, column=2, value=m["precip_mm"]).number_format = "0.0"
        ws.cell(row=row, column=3, value=m["precip_normal_mm"]).number_format = "0.0"
        ws.cell(row=row, column=4, value=f"=IF(C{row}>0,B{row}/C{row},\"\")").number_format = "0%"
        ws.cell(row=row, column=5, value=m["t_mean"]).number_format = "0.0"
        ws.cell(row=row, column=6, value=m["t_anomaly"]).number_format = "+0.0;-0.0;0.0"
        ws.cell(row=row, column=7, value=m["hot_days"])
        ws.cell(row=row, column=8, value=m["gwetroot"]).number_format = "0.000"
        if nd:
            ws.cell(row=row, column=9, value=round(sum(nd) / len(nd), 4)).number_format = "0.000"
        if sm:
            ws.cell(row=row, column=10, value=round(sum(sm) / len(sm), 4)).number_format = "0.000"
        ws.cell(row=row, column=11, value=", ".join(srcs))
        row += 1
    _finish(ws, 1, row - 1, len(head))
    ws.cell(row=row + 1, column=1, value=t["units_note"]).font = NOTE_FONT

    # ---------------------------------------------------------------- 3. сравнение сценариев
    ws = wb.create_sheet(t["s3"][:31])
    head = [t["scenario"], t["crops"], t["soil"], t["water"], t["income"], t["risk"], t["score"], t["n"], t["humus"], t["soil_idx"],
            t["deficit"], t["revenue"], t["cost"], t["margin"], t["m_minus"], t["m_plus"], t["loss"], t["confidence"], t["conf_share"], t["best"],
            rs["col_bare_days"], rs["col_exposure"]]
    _header(ws, 1, head, [26, 40, 9, 9, 9, 9, 13, 11, 10, 11, 12, 13, 13, 15, 15, 15, 12, 12, 12, 12, 13, 14])
    # строка весов: взвешенный балл считается формулой SUMPRODUCT
    wrow = len(c["variants"]) + 3
    ws.cell(row=wrow, column=2, value=t["weight_row"]).font = HEAD_FONT
    for j, k in enumerate(("soil", "water", "income", "risk"), start=3):
        ws.cell(row=wrow, column=j, value=weights[k]).number_format = "0%"
    for i, v in enumerate(c["variants"], start=2):
        name = v.get("name")
        name = name.get(lang) if isinstance(name, dict) else (name or v["id"])
        e, tt = v["economics"], v["totals"]
        vals = [name, " → ".join(crop(x) for x in v["crops"])] + [v["scores"][k]["score"] for k in ("soil", "water", "income", "risk")]
        for j, val in enumerate(vals, start=1):
            ws.cell(row=i, column=j, value=val)
        ws.cell(row=i, column=7, value=f"=SUMPRODUCT(C{i}:F{i},$C${wrow}:$F${wrow})").number_format = "0.00"
        for j, val, fmt in ((8, tt["nitrogen_kg_ha"], "0"), (9, tt["humus_t_ha"], "0.00"), (10, tt["soil_index_end"], "0.0"),
                            (11, tt["water_deficit_mean_mm"], "0"), (12, e["revenue_kzt_ha"], "#,##0"), (13, e["cost_kzt_ha"], "#,##0")):
            ws.cell(row=i, column=j, value=val).number_format = fmt
        ws.cell(row=i, column=14, value=f"=L{i}-M{i}").number_format = "#,##0"
        ws.cell(row=i, column=15, value=f"=L{i}*0.8-M{i}").number_format = "#,##0"
        ws.cell(row=i, column=16, value=f"=L{i}*1.2-M{i}").number_format = "#,##0"
        ws.cell(row=i, column=17, value=tt["drought_loss_pct"] / 100).number_format = "0.0%"
        ws.cell(row=i, column=18, value=v["confidence"]["level"])
        ws.cell(row=i, column=19, value=v["confidence"]["share"]).number_format = "0%"
        ws.cell(row=i, column=20, value=t["yes"] if v["fits_priority"] else t["no"])
        # необязательные (в анализах до задачи 5 их нет): пустая ячейка, ничего не подставляется
        if v.get("bare_days_per_year") is not None:
            ws.cell(row=i, column=21, value=v["bare_days_per_year"]).number_format = "0"
        if v.get("exposure_index") is not None:
            ws.cell(row=i, column=22, value=v["exposure_index"]).number_format = "0.00"
    last = len(c["variants"]) + 1
    _finish(ws, 1, last, len(head))
    # источник и статус дней без покрова и индекса эрозии — строкой под весами
    note = scenario_exposure.report_note(c, rs, crop, float(rules.erosion["erosive_wind"]["speed_ms"].value),
                                         lambda x, d: f"{x:.{d}f}" if lang == "en" else f"{x:.{d}f}".replace(".", ","), lang)
    ws.cell(row=wrow + 1, column=2, value=note).font = NOTE_FONT
    chart = BarChart()
    chart.title = t["chart_margin"]
    chart.y_axis.title = "KZT/ha"
    chart.add_data(Reference(ws, min_col=14, min_row=1, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last))
    chart.height, chart.width = 7.5, 16
    ws.add_chart(chart, f"B{wrow + 3}")
    # расчёт по годам с формулами
    r0 = wrow + 20
    ws.cell(row=r0, column=1, value=t["detail"]).font = TITLE_FONT
    dh = [t["scenario"], t["year"], t["crop"], t["yield"], t["price"], t["cost_y"], t["margin_y"], t["yield_dry"], t["pred"], t["moist"],
          rs["col_bare_days_y"], rs["col_risky_days_y"]]
    _header(ws, r0 + 1, dh)
    rr = r0 + 2
    for v in c["variants"]:
        bare_y = {y["index"]: y for y in (v.get("bare_soil") or {}).get("per_year", [])}
        for y in v["years"]:
            b = bare_y.get(y["index"], {})
            if b.get("bare_days") is not None:
                ws.cell(row=rr, column=11, value=b["bare_days"])
            if b.get("risky_days") is not None:
                ws.cell(row=rr, column=12, value=b["risky_days"]).number_format = "0.0"
            ws.cell(row=rr, column=1, value=v["id"])
            ws.cell(row=rr, column=2, value=y["year"])
            ws.cell(row=rr, column=3, value=crop(y["crop"]))
            ws.cell(row=rr, column=4, value=y["yield_t_ha"]).number_format = "0.000"
            ws.cell(row=rr, column=5, value=y["price_kzt_t"]).number_format = "#,##0"
            ws.cell(row=rr, column=6, value=y["cost_kzt_ha"]).number_format = "#,##0"
            ws.cell(row=rr, column=7, value=f"=D{rr}*E{rr}-F{rr}").number_format = "#,##0"
            ws.cell(row=rr, column=8, value=y["yield_dry_t_ha"]).number_format = "0.000"
            ws.cell(row=rr, column=9, value=y["predecessor_effect_pct"])
            ws.cell(row=rr, column=10, value=y["moisture_coef"]).number_format = "0.000"
            rr += 1

    # ---------------------------------------------------------------- 4. история сезонов
    ws = wb.create_sheet(t["s4"][:31])
    b = seasons["baseline"]
    ws["A1"], ws["B1"] = t["baseline"], ""
    ws["A1"].font = HEAD_FONT
    ws["A2"], ws["B2"] = t["p_season"], b["precip_mean"]
    ws["A3"], ws["B3"] = t["t_season"], b["t_mean"]
    head = [t["season"], t["p_season"], t["p_diff"], t["p_anom"], t["dry"], t["t_season"], t["t_diff"], t["hot"], t["ndvi_max"], t["ndvi_mean"],
            t["smap_spring"], t["smap_ratio"]]
    hr = 5
    _header(ws, hr, head, [9, 14, 16, 12, 11, 14, 16, 12, 11, 12, 14, 12])
    rr = hr + 1
    for r in seasons["years"]:
        ws.cell(row=rr, column=1, value=r["year"])
        ws.cell(row=rr, column=2, value=r["precip_mm"]).number_format = "0.0"
        ws.cell(row=rr, column=3, value=f"=B{rr}-$B$2").number_format = "+0.0;-0.0;0.0"
        ws.cell(row=rr, column=4, value=r["precip_anomaly_z"]).number_format = "+0.00;-0.00;0.00"
        ws.cell(row=rr, column=5, value=t["yes"] if r["is_dry"] else t["no"])
        if r["t_mean"] is not None:
            ws.cell(row=rr, column=6, value=r["t_mean"]).number_format = "0.0"
            ws.cell(row=rr, column=7, value=f"=F{rr}-$B$3").number_format = "+0.0;-0.0;0.0"
        ws.cell(row=rr, column=8, value=r["hot_days"])
        for j, key, fmt in ((9, "ndvi_max", "0.000"), (10, "ndvi_mean", "0.000"), (11, "smap_spring", "0.000"), (12, "smap_ratio", "0.00")):
            if r[key] is not None:
                ws.cell(row=rr, column=j, value=r[key]).number_format = fmt
        rr += 1
    last = rr - 1
    _finish(ws, hr, last, len(head))
    avg_row = rr + 1
    ws.cell(row=avg_row, column=1, value=t["average"]).font = HEAD_FONT
    for j in (2, 6, 8, 9, 10, 11):
        col = get_column_letter(j)
        ws.cell(row=avg_row, column=j, value=f"=AVERAGE({col}{hr + 1}:{col}{last})").number_format = "0.00"
    ch = BarChart()
    ch.title = t["chart_precip"]
    ch.add_data(Reference(ws, min_col=2, min_row=hr, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=hr + 1, max_row=last))
    ch.height, ch.width = 7.5, 22
    ws.add_chart(ch, f"N{hr}")
    lc = LineChart()
    lc.title = t["chart_ndvi"]
    lc.add_data(Reference(ws, min_col=9, min_row=hr, max_row=last), titles_from_data=True)
    lc.set_categories(Reference(ws, min_col=1, min_row=hr + 1, max_row=last))
    lc.height, lc.width = 7.5, 22
    ws.add_chart(lc, f"N{hr + 17}")

    # ---------------------------------------------------------------- 5. допущения модели
    ws = wb.create_sheet(t["s5"][:31])
    head = [t["param"], t["value"], t["unit"], t["source"], t["url"], t["status"], t["evidence"], t["note"]]
    _header(ws, 1, head, [44, 14, 16, 50, 40, 12, 18, 90])
    rr = 2
    for p in rules.all_params():
        val = p.value if not isinstance(p.value, dict) else json.dumps(p.value, ensure_ascii=False)
        for j, v in enumerate([p.path, val, p.unit, p.source_name, p.source_url, p.status, p.evidence, p.note], start=1):
            cell = ws.cell(row=rr, column=j, value=v)
            if j in (4, 8):
                cell.alignment = WRAP
        rr += 1
    _finish(ws, 1, rr - 1, len(head))

    # ---------------------------------------------------------------- 6. источники и методика
    ws = wb.create_sheet(t["s6"][:31])
    head = [t["dataset"], t["provider"], t["resolution"], t["coverage"], t["processing"], t["limits"], t["doi"]]
    _header(ws, 1, head, [34, 30, 50, 50, 50, 60, 40])
    rr = 2
    for sid, meta in source_catalog().items():
        vals = [meta["title"], meta["provider"], meta["spatial_resolution"][lang], meta["temporal_coverage"][lang],
                PROCESSING.get(sid, {}).get(lang, ""), meta["limitations"][lang], meta.get("doi") or meta["url"]]
        for j, v in enumerate(vals, start=1):
            ws.cell(row=rr, column=j, value=v).alignment = WRAP
        rr += 1
    for sid, src in rules.sources.items():
        if str(src["url"]).startswith("http"):
            ws.cell(row=rr, column=1, value=sid)
            ws.cell(row=rr, column=2, value=src["name"]).alignment = WRAP
            ws.cell(row=rr, column=7, value=src["url"])
            rr += 1
    _finish(ws, 1, rr - 1, len(head))

    wb.properties.title = t["title"]
    wb.properties.creator = "Agro-Sevooborot"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def today_iso() -> str:
    return date.today().isoformat()
