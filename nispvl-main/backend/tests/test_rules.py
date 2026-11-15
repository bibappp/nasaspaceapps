"""Правила: у каждой цифры есть источник и статус."""
from __future__ import annotations

import shutil

import pytest

from app.model.rules import RULES_DIR, RulesError, load_rules

REQUIRED_CROPS = {"wheat", "lentil", "pea", "chickpea", "flax", "rapeseed", "sunflower", "fallow"}


def test_every_param_has_source_and_status(rules):
    params = rules.all_params()
    assert len(params) > 60
    for p in params:
        assert p.status in ("verified", "assumption"), p.path
        assert p.source_name and p.source_url, p.path
        assert p.unit != "", p.path
        if p.status == "assumption":
            assert p.note, f"{p.path}: у допущения должно быть пояснение"


def test_required_crops_regions_and_variants(rules):
    assert REQUIRED_CROPS <= set(rules.crops)
    assert set(rules.regions) == {"akmola", "kostanay", "north_kazakhstan"}
    assert [v["crops"] for v in rules.model["default_variants"]] == [
        ["wheat", "wheat", "wheat", "wheat"],
        ["wheat", "lentil", "wheat", "flax"],
        ["wheat", "pea", "rapeseed", "fallow"],
        ["wheat", "chickpea", "sunflower", "wheat"],
    ]
    assert set(rules.model["priorities"]) == {"max_income", "save_moisture", "restore_soil", "minimize_risk", "balanced"}
    for crop in rules.crops.values():
        assert crop["name"]["ru"] and crop["name"]["kk"]
    for cid in ("lentil", "pea", "chickpea"):
        assert rules.crops[cid]["nitrogen_fixing"] is True
    assert rules.crops["wheat"]["nitrogen_fixing"] is False


def test_prices_come_from_one_document_and_date(rules):
    """Аудит: цены нельзя смешивать из разных источников и дат — это искажает сравнение культур.
    Все культуры, для которых есть цена в рекомендациях МСХ РК от 27.07.2026, берут её оттуда."""
    for cid in ("wheat", "lentil", "pea", "flax", "rapeseed", "sunflower"):
        p = rules.crop(cid)["price_kzt_t"]
        assert p.source_id == "moa_prices_2026" and p.status == "verified", cid
    assert rules.crop("wheat")["price_kzt_t"].value == 104000  # 3 класс, клейковина до 25 %


def test_every_param_has_evidence_class(rules):
    from app.model.rules import EVIDENCE

    for p in rules.all_params():
        assert p.evidence in EVIDENCE, p.path
        if p.status == "verified":
            assert p.evidence in ("literature", "definition"), p.path
        if p.evidence == "preliminary":
            assert p.status == "assumption", p.path


def test_fao_ky_values_match_fao56_table24(rules):
    # FAO-56, табл. 24 (сверено с текстом FAO): Spring wheat 1.15, Peas 1.15, Sunflower 0.95;
    # для культур без данных FAO рекомендует Ky = 1
    expected = {"wheat": 1.15, "pea": 1.15, "sunflower": 0.95, "lentil": 1.0, "chickpea": 1.0, "flax": 1.0, "rapeseed": 1.0}
    for cid, ky in expected.items():
        assert rules.crop(cid)["ky"].value == ky, cid


def test_region_reference_is_computed_from_power(rules):
    for rid, region in rules.regions.items():
        ref = region["reference_season_precip_mm"]
        assert ref.value is not None and 80 < ref.value < 400, rid
        assert ref.source_id == "nasa_power"


def test_predecessor_lookup_prefers_specific_rule(rules):
    assert rules.predecessor_effect("pea", "wheat")[0] == 26
    assert rules.predecessor_effect("lentil", "wheat")[0] == 18
    assert rules.predecessor_effect("wheat", "wheat")[0] == 0
    assert rules.predecessor_effect("sunflower", "wheat")[0] == -10  # конкретное правило сильнее группового
    assert rules.predecessor_effect("flax", "wheat")[0] == 10
    assert rules.predecessor_effect("pea", "pea")[0] == -15
    assert rules.predecessor_effect("pea", "lentil")[0] == -10
    assert rules.predecessor_effect(None, "wheat") == (0.0, None)
    assert rules.predecessor_effect("wheat", "fallow") == (0.0, None)


def _copy_rules(tmp_path):
    for f in RULES_DIR.glob("*.yaml"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def test_loader_rejects_number_without_source(tmp_path):
    d = _copy_rules(tmp_path)
    text = (d / "crops.yaml").read_text(encoding="utf-8")
    (d / "crops.yaml").write_text(text.replace("source: expert_guess, status: assumption", "status: assumption", 1), encoding="utf-8")
    with pytest.raises(RulesError, match="missing fields"):
        load_rules(d)


def test_loader_rejects_missing_evidence(tmp_path):
    d = _copy_rules(tmp_path)
    text = (d / "crops.yaml").read_text(encoding="utf-8")
    (d / "crops.yaml").write_text(text.replace(" evidence: preliminary,", "", 1), encoding="utf-8")
    with pytest.raises(RulesError, match="evidence"):
        load_rules(d)


def test_loader_rejects_unknown_source_and_status(tmp_path):
    d = _copy_rules(tmp_path)
    text = (d / "crops.yaml").read_text(encoding="utf-8")
    (d / "crops.yaml").write_text(text.replace("source: expert_guess", "source: made_up", 1), encoding="utf-8")
    with pytest.raises(RulesError, match="unknown source"):
        load_rules(d)
    (d / "crops.yaml").write_text(text.replace("source: stat_gov_kz, status: assumption", "source: stat_gov_kz, status: sure", 1), encoding="utf-8")
    with pytest.raises(RulesError, match="status"):
        load_rules(d)


# ---------------------------------------------------------------- erosion.yaml («Часы голой почвы»)
EXCERPT_ONLY = "проверено только по выдержке, полный текст не прочитан"


def test_erosion_thresholds_are_the_agreed_values(rules):
    e = rules.erosion
    ndvi = e["bare_soil"]["ndvi_max"]
    assert (ndvi.value, ndvi.range, ndvi.status, ndvi.evidence) == (0.30, (0.20, 0.30), "assumption", "agronomist_review")
    assert e["bare_soil"]["sensitivity_values"] == [0.25, 0.30]
    wind = e["erosive_wind"]
    assert (wind["speed_ms"].value, wind["reference_height_m"], wind["power_parameter"]) == (5.0, 2, "WS2M_MAX")
    assert wind["speed_ms"].source_id == "rweq_1998" and wind["context_range_10m_ms"] == [6, 10]
    assert "Зайцев" in wind["speed_ms"].note and "ru-ecology.info" in wind["speed_ms"].note
    dry = e["dry_topsoil"]
    assert dry["smap_wilting_point_factor"].source_id == "chepil_1956"
    assert dry["gwettop_method"] == "cdf_match" and dry["gwettop_month_quality"] == "partial"
    assert dry["gwettop_fallback"].evidence == "preliminary"
    assert e["snow"]["modis_reliability_snow"].value == 2
    # Зайцева упомянута только в пояснении: источника, на который ссылалось бы значение, нет
    assert not any("zaitseva" in sid or "ru_ecology" in sid for sid in rules.sources)


def test_erosion_params_are_in_the_catalogue(rules):
    paths = {p.path for p in rules.all_params()}
    assert {"erosion.bare_soil.ndvi_max", "erosion.erosive_wind.speed_ms", "erosion.dry_topsoil.smap_wilting_point_factor",
            "erosion.snow.power_snodp_min_cm"} <= paths


def test_literature_used_for_erosion_is_marked_excerpt_only(rules):
    """Источники, проверенные только по выдержке, должны говорить это в note — и ни одно правило на них не verified."""
    excerpt = {sid for sid, s in rules.sources.items() if EXCERPT_ONLY in str(s.get("note", "")).lower()}
    assert {"rweq_1998", "chepil_1956", "sobrino_2004", "lamb_2022", "reichle_koster_2004"} <= excerpt
    for p in rules.all_params():
        if p.source_id in excerpt:
            assert p.status == "assumption", p.path


def _replace(d, name, old, new):
    text = (d / name).read_text(encoding="utf-8")
    assert old in text, old
    (d / name).write_text(text.replace(old, new, 1), encoding="utf-8")


def test_loader_requires_erosion_file_and_groups(tmp_path):
    d = _copy_rules(tmp_path)
    _replace(d, "erosion.yaml", "\nsnow:\n", "\nsnow_renamed:\n")
    with pytest.raises(RulesError, match="erosion.snow"):
        load_rules(d)
    (d / "erosion.yaml").unlink()
    with pytest.raises(FileNotFoundError):
        load_rules(d)


@pytest.mark.parametrize(("old", "new", "match"), [
    ("value: 0.30, range: [0.20, 0.30]", "value: 0.35, range: [0.20, 0.30]", "outside range"),
    ("range: [0.20, 0.30]", "range: [0.30, 0.20]", "exceeds upper bound"),
    ("range: [0.20, 0.30]", "range: [0.20]", "two numbers"),
    ("reference_height_m: 2", "reference_height_m: 3", "reference_height_m"),
    ("power_parameter: WS2M_MAX", "power_parameter: WS10M_MAX", "power_parameter"),
    ("sensitivity_values: [0.25, 0.30]", "sensitivity_values: [0.25]", "sensitivity_values"),
    ("gwettop_method: cdf_match", "gwettop_method: linear", "gwettop_method"),
    ("{value: 0.70, range: [0.70, 0.79]", "{value: 1.5, range: [0.70, 1.79]", "gwettop_fallback"),
    ("{value: 2, unit:", "{value: 7, unit:", "pixel_reliability"),
    ("ndvi_bare: bare_soil.ndvi_max", "ndvi_bare: bare_soil.ndvi_missing", "contract_thresholds"),
    ('akmola:\n      {value: "10-01"', 'akmola:\n      {value: "10-32"', "harvest_end.akmola"),
    ('akmola:\n      {value: "10-01"', 'akmola:\n      {value: "05-15"', "after season_split_month"),
    ("    north_kazakhstan:\n      {value:", "    nko_renamed:\n      {value:", "no date for regions"),
    ("no_window_advice_source: bilbro_fryrear_1994", "no_window_advice_source: nobody_2026", "no_window_advice_source"),
])
def test_loader_rejects_bad_erosion_values(tmp_path, old, new, match):
    d = _copy_rules(tmp_path)
    _replace(d, "erosion.yaml", old, new)
    with pytest.raises(RulesError, match=match):
        load_rules(d)


def test_cover_crop_harvest_end_for_every_region(rules):
    he = rules.erosion["cover_crop"]["harvest_end"]
    assert set(he) == set(rules.regions)
    for p in he.values():
        assert p.status == "assumption" and p.note  # не агрономическая рекомендация: агроному проверить
