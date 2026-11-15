"""XLSX-книга: листы, формулы, фильтры, закреплённые заголовки, графики, данные без выдуманных значений."""
from __future__ import annotations

import asyncio
import io

import pytest
from openpyxl import load_workbook

from app.config import get_settings
from app.data_sources.base import demo_field_record
from app.report.xlsx import L, build_workbook
from app.schemas import CompareRequest


@pytest.fixture(scope="module")
def data():
    if demo_field_record() is None:
        pytest.skip("нет data/demo")
    from app.services.report_data import gather

    s = get_settings()
    old = s.offline
    s.offline = True
    demo = demo_field_record()
    req = CompareRequest(geometry=demo["geometry"], region=demo["region"], history=demo["history"], priority="balanced", horizon_years=4)
    d = asyncio.run(gather(req, {"name": "Поле 1"}))
    s.offline = old
    return d


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_workbook_structure(data, lang):
    wb = load_workbook(io.BytesIO(build_workbook(data, lang=lang)))
    t = L[lang]
    assert wb.sheetnames == [t[k][:31] for k in ("s1", "s2", "s3", "s4", "s5", "s6")]
    for name in wb.sheetnames[1:]:
        ws = wb[name]
        assert ws.freeze_panes is not None, name
        assert ws.auto_filter.ref, name
    assert len(wb[t["s3"][:31]]._charts) >= 1 and len(wb[t["s4"][:31]]._charts) == 2


def test_formulas_are_transparent_and_consistent(data):
    wb = load_workbook(io.BytesIO(build_workbook(data, lang="en")))
    ws = wb["Crop Rotation Comparison"]
    assert ws["G2"].value.startswith("=SUMPRODUCT(") and ws["N2"].value == "=L2-M2"
    for i, v in enumerate(data.comparison["variants"], start=2):
        assert ws[f"L{i}"].value - ws[f"M{i}"].value == v["economics"]["gross_margin_kzt_ha"]
        weights = [ws.cell(row=len(data.comparison["variants"]) + 3, column=j).value for j in range(3, 7)]
        scores = [ws.cell(row=i, column=j).value for j in range(3, 7)]
        assert sum(w * s for w, s in zip(weights, scores, strict=True)) == pytest.approx(v["weighted_score"], abs=0.02)
    # годовой расчёт: маржа = урожайность × цена − затраты
    detail = [r for r in ws.iter_rows(values_only=False) if isinstance(r[6].value, str) and r[6].value.startswith("=D")]
    assert len(detail) == sum(len(v["years"]) for v in data.comparison["variants"])
    hist = wb["Historical Analysis"]
    assert hist["C6"].value == "=B6-$B$2"


def test_environmental_sheet_has_no_invented_values(data):
    wb = load_workbook(io.BytesIO(build_workbook(data, lang="en")))
    ws = wb["Environmental Data"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    months = [r for r in rows if r[0] and len(str(r[0])) == 7]
    assert months[0][0] == "2000-01"
    by_month = {r[0]: r for r in months}
    # SMAP есть только за апрель–май, NDVI — только в месяцы вегетационного сезона
    assert all(r[9] is None for m, r in by_month.items() if m[5:] not in ("04", "05"))
    assert all(r[8] is None for m, r in by_month.items() if m[5:] in ("01", "02", "03", "11", "12"))
    jul21 = by_month["2021-07"]
    src = next(x for x in data.climate_monthly["months"] if x["month"] == "2021-07")
    assert jul21[1] == src["precip_mm"] and jul21[4] == src["t_mean"]


def test_assumptions_sheet_lists_every_parameter(data):
    from app.model.rules import get_rules

    wb = load_workbook(io.BytesIO(build_workbook(data, lang="ru")))
    ws = wb[L["ru"]["s5"][:31]]
    paths = [r[0] for r in ws.iter_rows(min_row=2, values_only=True) if r[0]]
    assert set(paths) == {p.path for p in get_rules().all_params()}
