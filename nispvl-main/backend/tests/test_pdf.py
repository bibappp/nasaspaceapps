"""PDF-отчёт: три языка, казахские буквы без «квадратиков», содержание из данных поля."""
from __future__ import annotations

import asyncio
import io

import pytest
import yaml
from pypdf import PdfReader

from app.config import get_settings
from app.data_sources.base import demo_field_record
from app.model import explain
from app.report import pdf as pdf_mod
from app.report.fonts import FONT, KAZAKH_LETTERS, missing_glyphs
from app.schemas import CompareRequest

ALL_KK = set("әғқңөұүһі")


@pytest.fixture(scope="module")
def data():
    if demo_field_record() is None:
        pytest.skip("нет data/demo")
    from app.services.report_data import gather

    s = get_settings()
    old = s.offline
    s.offline = True
    demo = demo_field_record()
    req = CompareRequest(geometry=demo["geometry"], region=demo["region"], history=demo["history"], priority="max_income", horizon_years=4)
    d = asyncio.run(gather(req, {"name": "Солтүстік егістік", "farm_name": "ТОО «Қызылжар»", "history_is_scenario": True}))
    s.offline = old
    return d


def _text(pdf: bytes) -> tuple[str, PdfReader]:
    reader = PdfReader(io.BytesIO(pdf))
    return "".join(p.extract_text() for p in reader.pages), reader


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_pdf_builds_with_all_sections(data, lang):
    pdf = pdf_mod.build_report(data, lang=lang)
    assert pdf.startswith(b"%PDF")
    text, reader = _text(pdf)
    t = pdf_mod.strings(lang)
    assert len(reader.pages) >= 8
    for key in ("title", "s_summary", "s_field", "s_data", "s_vegetation", "s_water", "s_risk", "s_compare", "s_assess",
                "s_forecast", "s_stress", "s_recommended", "s_assumptions", "s_limitations", "s_references", "s_sign"):
        assert t[key].split()[0] in text, key
    assert "Қызылжар" in text
    fonts = {str(f.get_object()["/BaseFont"]) for p in reader.pages for f in (p["/Resources"].get("/Font") or {}).values()}
    assert fonts and all("DejaVu" in f for f in fonts), fonts


def test_kazakh_pdf_contains_all_kazakh_letters(data):
    text, _ = _text(pdf_mod.build_report(data, lang="kk"))
    found = ALL_KK & set(text.lower())
    assert len(found) >= 8, sorted(found)


def test_pdf_numbers_come_from_the_model(data):
    best = next(v for v in data.comparison["variants"] if v["fits_priority"])
    text, _ = _text(pdf_mod.build_report(data, lang="en"))
    margin = f"{best['economics']['gross_margin_kzt_ha']:,}".replace(",", " ")
    assert margin in text or margin.replace(" ", " ") in text
    for y in data.analysis["drought"]["dry_years"]:
        assert str(y) in text


def test_font_has_all_kazakh_letters():
    assert missing_glyphs(KAZAKH_LETTERS) == set()


def test_all_report_and_explanation_strings_have_glyphs():
    texts = []
    for path in (pdf_mod.LOCALE_PATH, explain.TEMPLATES_PATH):
        for entry in yaml.safe_load(path.read_text(encoding="utf-8")).values():
            for lang in ("ru", "kk", "en"):
                v = entry[lang]
                texts += v if isinstance(v, list) else [v]
    assert missing_glyphs("".join(texts) + "★→•−≈–—«»№■³", FONT) == set()
