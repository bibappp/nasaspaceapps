"""Дни без зелёного покрова и индекс опасности эрозии в сценариях планировщика
(app/analytics/scenario_exposure.py). Синтетические ряды в юнит-тестах — не данные какого-либо поля."""
from __future__ import annotations

import ast
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.analytics import scenario_exposure as se
from app.config import get_settings
from app.data_sources.base import demo_field_record
from app.main import app
from app.model.rules import RULES_DIR, RulesError, get_rules, load_rules, parse_window

H = {"X-Requested-With": "agro"}
YEARS = range(2020, 2025)
NEW_FIELDS = ("bare_days_per_year", "exposure_index", "bare_soil")


@pytest.fixture(scope="module")
def rules():
    return get_rules()


def synthetic_daily(windy_every: int = 2) -> pd.DataFrame:
    """Снег до 31 марта и с 15 ноября; ветер — каждый ``windy_every``-й день; сухо всегда."""
    idx = pd.date_range(date(YEARS.start, 1, 1), date(YEARS.stop - 1, 12, 31), freq="D")
    snow = [(d.month <= 3) or (d.month == 11 and d.day >= 15) or d.month == 12 for d in idx]
    windy = pd.array([i % windy_every == 0 for i in range(len(idx))], dtype="boolean")
    dry = pd.array([True] * len(idx), dtype="boolean")
    return pd.DataFrame({"snow": snow, "windy": windy, "dry": dry, "weather": True}, index=idx)


@pytest.fixture(scope="module")
def climate(rules):
    return se.field_climate(synthetic_daily(), rules.erosion, YEARS)


def years_of(crops: list[str]) -> list[dict]:
    return [{"index": i + 1, "year": 2027 + i, "crop": c} for i, c in enumerate(crops)]


# ---------------------------------------------------------------- климатология
def test_snow_free_season_from_snow_rules(climate):
    s = climate["season"]
    assert (s["start"], s["end"]) == (date(2001, 4, 1), date(2001, 11, 14))
    assert s["days"] == (s["end"] - s["start"]).days + 1 and s["n_years"] == len(YEARS)


def test_wind_dry_share_by_month(climate):
    months = {m["month"]: m for m in climate["months"]}
    assert months[1]["season_days"] == 0 and months[1]["p_wind_dry"] is None
    for m in range(4, 11):
        assert months[m]["p_wind_dry"] == pytest.approx(0.5, abs=0.04)
        assert months[m]["n_years"] == len(YEARS)
    assert climate["status"] == "ok"


# ---------------------------------------------------------------- дни без покрова
def test_fallow_has_more_bare_days_than_continuous_crop(rules, climate):
    fallow = se.scenario(rules, years_of(["fallow"] * 4), climate)
    wheat = se.scenario(rules, years_of(["wheat"] * 4), climate)
    assert fallow["bare_days_per_year"] > wheat["bare_days_per_year"] > 0
    assert fallow["mean_exposure"] > wheat["mean_exposure"] > 0
    # пар — без покрова весь бесснежный сезон
    assert fallow["bare_days_per_year"] == climate["season"]["days"]


def test_crop_bare_days_are_season_minus_canopy(rules, climate):
    sow, harvest = parse_window(rules.crop("wheat")["sowing_window"]), parse_window(rules.crop("wheat")["harvest_window"])
    # по умолчанию: покров с конца окна сева до середины окна уборки (erosion.planner)
    c0, c1 = sow[1], harvest[0] + timedelta(days=(harvest[1] - harvest[0]).days // 2)
    y = se.season_year(rules, "wheat", climate)
    assert (y["canopy_start"], y["canopy_end"]) == (c0.strftime("%m-%d"), c1.strftime("%m-%d"))
    assert y["bare_days"] == climate["season"]["days"] - ((c1 - c0).days + 1)
    assert 0 <= y["exposure"] <= 1 and y["risky_days"] <= y["bare_days"]


def test_canopy_choice_comes_from_rules(rules, climate):
    default = se.season_year(rules, "wheat", climate)
    # покров дольше (раньше начало или позже конец) — дней без покрова меньше
    assert se.season_year(rules, "wheat", climate, start="sowing_start")["bare_days"] < default["bare_days"]
    assert se.season_year(rules, "wheat", climate, end="harvest_end")["bare_days"] < default["bare_days"]
    assert se.season_year(rules, "wheat", climate, end="harvest_start")["bare_days"] > default["bare_days"]


def test_missing_climate_gives_none_not_zero(rules):
    sc = se.scenario(rules, years_of(["wheat", "fallow"]), se.missing_climate("no_weather", YEARS))
    assert sc["status"] == "missing" and sc["missing_reason"] == "no_weather"
    assert sc["bare_days_per_year"] is None and sc["mean_exposure"] is None
    assert all(y["bare_days"] is None for y in sc["per_year"])


def test_unknown_wind_dry_month_gives_none_exposure(rules):
    daily = synthetic_daily()
    daily.loc[daily.index.month == 7, "windy"] = pd.NA  # июль неизвестен во все годы
    clim = se.field_climate(daily, rules.erosion, YEARS)
    sc = se.scenario(rules, years_of(["fallow"]), clim)
    assert clim["status"] == "partial" and sc["status"] == "partial"
    assert sc["bare_days_per_year"] == clim["season"]["days"] and sc["mean_exposure"] is None


def test_no_threshold_literals_in_scenario_exposure():
    """В app/analytics/scenario_exposure.py нет чисел в сравнениях, кроме 0 и 1: пороги — только из правил."""
    tree = ast.parse(Path(se.__file__).read_text(encoding="utf-8"))
    bad = [(n.lineno, s.value) for n in ast.walk(tree) if isinstance(n, ast.Compare)
           for s in [n.left, *n.comparators]
           if isinstance(s, ast.Constant) and isinstance(s.value, int | float) and not isinstance(s.value, bool)
           and s.value not in (0, 1)]
    assert bad == []


# ---------------------------------------------------------------- правила
def test_every_crop_has_windows_with_source_and_status(rules):
    for cid, crop in rules.crops.items():
        if crop["group"] == "fallow":
            assert crop["bare_whole_season"].value is True
            continue
        for key in ("sowing_window", "harvest_window"):
            p = crop[key]
            assert parse_window(p) is not None and p.source_id and p.status and p.evidence and p.note, f"{cid}.{key}"
            if p.source_id == "expert_guess":
                assert (p.status, p.evidence) == ("assumption", "preliminary"), f"{cid}.{key}"


def _copy_rules(tmp_path):
    for f in RULES_DIR.glob("*.yaml"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


@pytest.mark.parametrize(("name", "old", "new", "match"), [
    ("crops.yaml", '{value: {start: "05-05", end: "05-20"}', '{value: {start: "05-05", end: "05-41"}', "pea.sowing_window"),
    ("crops.yaml", '{value: {start: "05-05", end: "05-20"}', '{value: {start: "05-25", end: "05-20"}', "pea.sowing_window"),
    ("crops.yaml", '{value: {start: "08-01", end: "08-31"}', '{value: {start: "05-10", end: "08-31"}', "sowing_window must end before"),
    ("crops.yaml", '{value: {start: "08-20", end: "10-01"}', '{value: {start: "08-20", end: "10-15"}', "harvest_end"),
    ("crops.yaml", "    bare_whole_season:\n", "    bare_season_renamed:\n", "bare_whole_season"),
    ("erosion.yaml", "{value: sowing_end,", "{value: sowing_late,", "canopy_start"),
    ("erosion.yaml", "sensitivity_canopy_end: [harvest_start, harvest_mid, harvest_end]",
     "sensitivity_canopy_end: [harvest_start]", "sensitivity_canopy_end"),
])
def test_loader_rejects_bad_windows(tmp_path, name, old, new, match):
    d = _copy_rules(tmp_path)
    text = (d / name).read_text(encoding="utf-8")
    assert old in text, old
    (d / name).write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(RulesError, match=match):
        load_rules(d)


def test_loader_requires_windows_for_crops(tmp_path):
    d = _copy_rules(tmp_path)
    text = (d / "crops.yaml").read_text(encoding="utf-8")
    start = text.index("  chickpea:")
    i = text.index("    sowing_window:", start)
    j = text.index("    harvest_window:", i)
    (d / "crops.yaml").write_text(text[:i] + text[j:], encoding="utf-8")
    with pytest.raises(RulesError, match="chickpea.sowing_window"):
        load_rules(d)


# ---------------------------------------------------------------- API и сохранённые анализы
pytestmark_demo = pytest.mark.skipif(demo_field_record() is None, reason="нет data/demo")


@pytest.fixture
def env(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(s, "offline", True)
    auth._failed.clear()
    yield tmp_path


def _compare_body(**kw):
    demo = demo_field_record()
    return {"geometry": demo["geometry"], "region": "akmola", "start_year": 2027,
            "history": [{"year": y, "crop": "wheat"} for y in range(2022, 2027)], **kw}


@pytestmark_demo
def test_compare_has_fields_and_fallow_scenario_is_most_exposed(env):
    with TestClient(app) as c:
        r = c.post("/api/rotations/compare", json=_compare_body())
    assert r.status_code == 200
    res = r.json()
    season = res["bare_soil_season"]
    assert season["status"] == "ok" and season["days"] > 0
    by_id = {v["id"]: v for v in res["variants"]}
    for v in res["variants"]:
        for k in NEW_FIELDS:
            assert k in v
        b = v["bare_soil"]
        assert b["bare_days_per_year"] == v["bare_days_per_year"] and b["mean_exposure"] == v["exposure_index"]
        assert b["in_score"] is False and b["rules"] and len(b["per_year"]) == len(v["years"])
        assert 0 < v["exposure_index"] <= 1
    assert by_id["pea_rapeseed_fallow"]["bare_days_per_year"] > by_id["wheat_mono"]["bare_days_per_year"]
    fallow_year = next(y for y in by_id["pea_rapeseed_fallow"]["bare_soil"]["per_year"] if y["crop"] == "fallow")
    assert fallow_year["bare_days"] == season["days"]


@pytestmark_demo
def test_bare_soil_does_not_change_scores(env, monkeypatch):
    with TestClient(app) as c:
        with_bs = c.post("/api/rotations/compare", json=_compare_body()).json()
        monkeypatch.setattr(se, "attach", lambda *a, **k: None)
        without = c.post("/api/rotations/compare", json=_compare_body()).json()
    assert "bare_soil" not in without["variants"][0]
    for a, b in zip(with_bs["variants"], without["variants"]):
        assert a["weighted_score"] == b["weighted_score"] and a["scores"] == b["scores"]
    assert with_bs["best_variant_id"] == without["best_variant_id"]


@pytestmark_demo
def test_new_and_old_saved_analyses(env):
    """Новый анализ сохраняет поля; старый анализ без них открывается и даёт PDF и XLSX."""
    from app import db

    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "farmer@example.org", "password": "correct horse 1"}, headers=H)
        body = {"name": "Поле", "region": "akmola", "geometry": demo_field_record()["geometry"],
                "history": [{"year": y, "crop": "wheat"} for y in range(2022, 2027)]}
        fid = c.post("/api/fields", json=body, headers=H).json()["id"]
        a = c.post(f"/api/fields/{fid}/analyses", json={"title": "новый"}, headers=H).json()
        assert all(k in v for v in a["result"]["variants"] for k in NEW_FIELDS)

        # старый анализ: результат сохранён до задачи 5, полей нет
        old = json.loads(json.dumps(a["result"]))
        old.pop("bare_soil_season")
        for v in old["variants"]:
            for k in NEW_FIELDS:
                v.pop(k)
        with db.connect() as conn:
            conn.execute("UPDATE analyses SET result = ? WHERE id = ?", (json.dumps(old, ensure_ascii=False), a["id"]))
        again = c.get(f"/api/analyses/{a['id']}")
        assert again.status_code == 200
        assert all(k not in v for v in again.json()["result"]["variants"] for k in NEW_FIELDS)
        for ext in ("pdf", "xlsx"):
            r = c.get(f"/api/fields/{fid}/report.{ext}?lang=ru&analysis_id={a['id']}")
            assert r.status_code == 200 and len(r.content) > 1000


# ---------------------------------------------------------------- PDF и XLSX
@pytest.fixture(scope="module")
def report_data():
    if demo_field_record() is None:
        pytest.skip("нет data/demo")
    import asyncio

    from app.schemas import CompareRequest
    from app.services.report_data import gather

    s = get_settings()
    old = s.offline
    s.offline = True
    demo = demo_field_record()
    req = CompareRequest(geometry=demo["geometry"], region=demo["region"], history=demo["history"])
    d = asyncio.run(gather(req))
    s.offline = old
    return d


def _without_bare_soil(data):
    import copy
    import dataclasses

    comp = copy.deepcopy(data.comparison)
    comp.pop("bare_soil_season")
    for v in comp["variants"]:
        for k in NEW_FIELDS:
            v.pop(k)
    return dataclasses.replace(data, comparison=comp)


def _pdf_text(pdf: bytes) -> str:
    import io

    from pypdf import PdfReader

    return " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages).replace("\n", " ")


def _comparison_sheet(xlsx: bytes):
    import io

    import openpyxl

    return openpyxl.load_workbook(io.BytesIO(xlsx)).worksheets[2]


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_pdf_has_bare_soil_columns_with_source_and_status(report_data, lang):
    from app.report import pdf as pdf_mod

    t = pdf_mod.strings(lang)
    text = _pdf_text(pdf_mod.build_report(report_data, lang=lang))
    season = report_data.comparison["bare_soil_season"]
    assert f"{season['days']} " in text and "assumption" in text and "agronomist_review" in text
    assert "Казгидромет" in text
    for word in t["col_exposure"].split()[:2]:
        assert word in text
    for v in report_data.comparison["variants"]:
        assert str(round(v["bare_days_per_year"])) in text


def test_xlsx_has_bare_soil_columns_and_note(report_data):
    from app.report import pdf as pdf_mod
    from app.report.xlsx import build_workbook

    t = pdf_mod.strings("ru")
    ws = _comparison_sheet(build_workbook(report_data, lang="ru"))
    head = [c.value for c in ws[1]]
    i, j = head.index(t["col_bare_days"]) + 1, head.index(t["col_exposure"]) + 1
    variants = report_data.comparison["variants"]
    for row, v in enumerate(variants, start=2):
        assert ws.cell(row=row, column=i).value == v["bare_days_per_year"]
        assert ws.cell(row=row, column=j).value == v["exposure_index"]
    note = ws.cell(row=len(variants) + 4, column=2).value
    assert "Казгидромет" in note and "assumption" in note


def test_reports_for_old_comparison_show_dash(report_data):
    """Сравнение без новых полей (анализ до задачи 5): PDF — «—», XLSX — пустые ячейки, без ошибок."""
    from app.report import pdf as pdf_mod
    from app.report.xlsx import build_workbook

    old = _without_bare_soil(report_data)
    t = pdf_mod.strings("ru")
    assert t["bare_not_saved"].split(":")[0] in _pdf_text(pdf_mod.build_report(old, lang="ru"))
    ws = _comparison_sheet(build_workbook(old, lang="ru"))
    i = [c.value for c in ws[1]].index(t["col_bare_days"]) + 1
    assert all(ws.cell(row=r, column=i).value is None for r in range(2, len(old.comparison["variants"]) + 2))
