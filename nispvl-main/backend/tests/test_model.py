"""Модель сравнения севооборотов."""
from __future__ import annotations

import dataclasses

import pytest

from app.model import explain, rotation
from app.model.rules import Param, Rules

WHEAT_HISTORY = ["wheat"] * 5


def defaults(rules: Rules) -> list[dict]:
    return [{"id": v["id"], "name": v["name"], "crops": list(v["crops"])} for v in rules.model["default_variants"]]


def run(rules, cond, priority="max_income", history=WHEAT_HISTORY, horizon=4, variants=None):
    return rotation.compare(rules, cond, variants or defaults(rules), history, horizon, priority, start_year=2027)


def by_id(result: dict) -> dict[str, dict]:
    return {v["id"]: v for v in result["variants"]}


def patched(rules: Rules, crop_id: str, key: str, value) -> Rules:
    """Копия правил с изменённым значением одного параметра культуры."""
    crop = dict(rules.crops[crop_id])
    crop[key] = dataclasses.replace(crop[key], value=value)
    return dataclasses.replace(rules, crops={**rules.crops, crop_id: crop})


# ---- обязательные проверки из постановки ---------------------------------------
def test_wheat_monoculture_never_gets_top_soil_score(rules, cond):
    for priority in rules.model["priorities"]:
        res = by_id(run(rules, cond, priority))
        mono = res["wheat_mono"]["scores"]["soil"]["score"]
        assert mono < 5.0
        assert mono == min(v["scores"]["soil"]["score"] for v in res.values())


def test_wheat_monoculture_not_top_even_against_a_worse_looking_set(rules, cond):
    """Шкала опирается и на опорные варианты: монокультура не станет «лучшей по почве»,
    даже если пользователь сравнивает её только с собой."""
    res = run(rules, cond, variants=[{"id": "only", "crops": ["wheat"]}])
    assert res["variants"][0]["scores"]["soil"]["score"] < 5.0


def test_legume_predecessor_raises_wheat_yield(rules, cond):
    after_wheat = rotation.simulate(rules, cond, ["wheat", "wheat"], [], 3, 2027)["years"][1]
    for legume in ("pea", "lentil", "chickpea"):
        after_legume = rotation.simulate(rules, cond, [legume, "wheat"], [], 3, 2027)["years"][1]
        assert after_legume["crop"] == "wheat"
        assert after_legume["predecessor_effect_pct"] > 0
        assert after_legume["yield_t_ha"] > after_wheat["yield_t_ha"]


def test_drought_hits_low_tolerance_crops_harder(rules, cond):
    """Чем выше Ky (ниже засухоустойчивость), тем сильнее падает доход в засушливый год."""
    losses = []
    for ky in (0.8, 1.0, 1.2):
        r = patched(rules, "wheat", "ky", ky)
        y = rotation.simulate(r, cond, ["wheat"], [], 3, 2027)["years"][0]
        assert y["income_dry_kzt_ha"] < y["income_kzt_ha"]
        losses.append((y["income_kzt_ha"] - y["income_dry_kzt_ha"]) / y["revenue_kzt_ha"])
    assert losses[0] < losses[1] < losses[2]


def test_drought_reduces_income_of_every_crop(rules, cond):
    for crop_id, crop in rules.crops.items():
        y = rotation.simulate(rules, cond, [crop_id], [], 3, 2027)["years"][0]
        if crop["group"] == "fallow":
            assert y["income_dry_kzt_ha"] == y["income_kzt_ha"]
        else:
            assert y["income_dry_kzt_ha"] < y["income_kzt_ha"], crop_id


def test_priority_changes_weights(rules, cond):
    results = {p: run(rules, cond, p) for p in rules.model["priorities"]}
    weights = [tuple(sorted((k, v) for k, v in r["weights"].items() if k != "_rule")) for r in results.values()]
    assert len(set(weights)) == len(weights)
    for p, res in results.items():
        w = rules.model["priorities"][p]["weights"].value
        assert abs(sum(w.values()) - 1) < 1e-9
        top = {"max_income": "income", "save_moisture": "water", "restore_soil": "soil", "minimize_risk": "risk"}.get(p)
        if top:
            assert max(w, key=w.get) == top
        else:  # balanced: равные веса
            assert len(set(w.values())) == 1
        for v in res["variants"]:
            expected = sum(w[k] * v["scores"][k]["score"] for k in rotation.SCORE_KEYS)
            assert v["weighted_score"] == pytest.approx(expected, abs=0.01)
    # отдельные оценки от приоритета не зависят — меняются только веса
    a, b = by_id(results["max_income"]), by_id(results["restore_soil"])
    for vid in a:
        assert {k: s["score"] for k, s in a[vid]["scores"].items()} == {k: s["score"] for k, s in b[vid]["scores"].items()}
    ranks = {p: [v["weighted_score"] for v in r["variants"]] for p, r in results.items()}
    assert len({tuple(x) for x in ranks.values()}) == len(ranks)


def test_custom_weights_override_preset_and_are_normalized(rules, cond):
    res = rotation.compare(rules, cond, defaults(rules), WHEAT_HISTORY, 4, "max_income", start_year=2027,
                           weights={"soil": 3, "water": 1, "income": 0, "risk": 0})
    assert res["weights"]["soil"] == 0.75 and res["weights"]["water"] == 0.25 and res["weights_custom"]
    for v in res["variants"]:
        assert v["weighted_score"] == pytest.approx(0.75 * v["scores"]["soil"]["score"] + 0.25 * v["scores"]["water"]["score"], abs=0.01)
    for bad in ({"soil": 1}, {"soil": 0, "water": 0, "income": 0, "risk": 0}, {"soil": -1, "water": 2, "income": 0, "risk": 0}):
        with pytest.raises(ValueError):
            rotation.normalize_weights(bad)


# ---- остальная логика ------------------------------------------------------------
def test_exactly_one_variant_fits_priority_and_all_stay_visible(rules, cond):
    res = run(rules, cond)
    assert len(res["variants"]) == 4
    assert sum(v["fits_priority"] for v in res["variants"]) == 1
    best = max(res["variants"], key=lambda v: v["weighted_score"])
    assert best["fits_priority"] and res["best_variant_id"] == best["id"]


def test_scores_are_between_1_and_5(rules, cond):
    for v in run(rules, cond)["variants"]:
        for s in v["scores"].values():
            assert 1.0 <= s["score"] <= 5.0
            assert s["params"], "у каждой оценки должны быть правила-источники"


def test_monoculture_penalty_starts_on_third_year_and_counts_history(rules, cond):
    fresh = rotation.simulate(rules, cond, ["wheat"], [], 4, 2027)["years"]
    assert [y["monoculture"] for y in fresh] == [False, False, True, True]
    with_history = rotation.simulate(rules, cond, ["wheat"], ["wheat", "wheat"], 3, 2027)["years"]
    assert with_history[0]["monoculture"] and with_history[0]["monoculture_run"] == 3
    assert with_history[0]["yield_t_ha"] < fresh[0]["yield_t_ha"]
    broken = rotation.simulate(rules, cond, ["wheat", "lentil"], ["wheat", "wheat"], 4, 2027)["years"]
    assert [y["monoculture"] for y in broken] == [True, False, False, False]


def test_history_sets_first_year_predecessor(rules, cond):
    after_pea = rotation.simulate(rules, cond, ["wheat"], ["wheat", "pea"], 3, 2027)["years"][0]
    after_wheat = rotation.simulate(rules, cond, ["wheat"], ["pea", "wheat"], 3, 2027)["years"][0]
    assert after_pea["predecessor"] == "pea" and after_pea["predecessor_effect_pct"] == 26
    assert after_wheat["predecessor_effect_pct"] == 0
    assert after_pea["yield_t_ha"] > after_wheat["yield_t_ha"]


def test_fallow_adds_moisture_for_next_crop_but_capped_by_soil(rules, cond):
    years = rotation.simulate(rules, cond, ["fallow", "wheat"], [], 3, 2027)["years"]
    fallow, wheat = years[0], years[1]
    assert fallow["yield_t_ha"] == 0 and fallow["income_kzt_ha"] < 0
    gain = float(rules.model["water"]["fallow_stock_gain_pct"].value)
    assert wheat["stock_mm"] == pytest.approx(min(cond.awc_mm, cond.stock_normal * (1 + gain / 100)))
    assert wheat["stock_mm"] == 140.0  # ограничено влагоёмкостью почвы (120 x 1,25 = 150 > 140)
    plain = rotation.simulate(rules, cond, ["wheat", "wheat"], [], 3, 2027)["years"][1]
    assert wheat["yield_t_ha"] > plain["yield_t_ha"]
    sandy = dataclasses.replace(cond, awc_mm=125.0)
    assert rotation.simulate(rules, sandy, ["fallow", "wheat"], [], 3, 2027)["years"][1]["stock_mm"] == 125.0


def test_moisture_coefficient_follows_field_water(rules, cond):
    wet = dataclasses.replace(cond, p_season_normal=220.0)
    dry = dataclasses.replace(cond, p_season_normal=110.0)
    y = lambda c: rotation.simulate(rules, c, ["wheat"], [], 3, 2027)["years"][0]
    assert y(dry)["yield_t_ha"] < y(cond)["yield_t_ha"] < y(wet)["yield_t_ha"]
    same = dataclasses.replace(cond, p_season_normal=cond.p_season_ref, stock_normal=cond.stock_ref)
    assert y(same)["moisture_coef"] == 1.0
    soaked = dataclasses.replace(cond, p_season_normal=900.0)
    assert y(soaked)["moisture_coef"] == float(rules.model["water"]["moisture_coef_max"].value)


def test_income_is_yield_times_price_minus_cost(rules, cond):
    for y in rotation.simulate(rules, cond, ["wheat", "lentil", "flax", "fallow"], [], 4, 2027)["years"]:
        crop = rules.crop(y["crop"])
        expected = y["yield_t_ha"] * crop["price_kzt_t"].value - crop["cost_kzt_ha"].value
        assert y["income_kzt_ha"] == pytest.approx(expected, abs=150)  # округление урожайности до кг


def test_stress_test_replaces_any_single_year(rules, cond):
    v = by_id(run(rules, cond))["lentil_flax"]
    total = v["totals"]["income_kzt_ha"]
    assert len(v["stress"]["per_year"]) == 4
    for row in v["stress"]["per_year"]:
        assert row["total_if_dry_kzt_ha"] == total - row["loss_kzt_ha"]
        assert row["loss_kzt_ha"] > 0
    worst = max(v["stress"]["per_year"], key=lambda r: r["loss_kzt_ha"])
    assert v["stress"]["worst_year_index"] == worst["index"]


def test_horizon_cycles_rotation_and_is_validated(rules, cond):
    v5 = run(rules, cond, horizon=5)["variants"][1]
    assert v5["crops"] == ["wheat", "lentil", "wheat", "flax", "wheat"]
    assert run(rules, cond, horizon=3)["variants"][1]["crops"] == ["wheat", "lentil", "wheat"]
    for bad in (2, 6):
        with pytest.raises(ValueError):
            run(rules, cond, horizon=bad)
    with pytest.raises(ValueError):
        run(rules, cond, priority="unknown")


def test_model_is_deterministic(rules, cond):
    assert run(rules, cond) == run(rules, cond)


def test_soil_index_combines_nitrogen_and_humus(rules, cond):
    years = rotation.simulate(rules, cond, ["pea"], [], 3, 2027)["years"]
    crop = rules.crop("pea")
    cfg = rules.model["soil_index"]
    step = crop["nitrogen_balance_kg_ha"].value / cfg["nitrogen_kg_per_point"].value + crop[
        "humus_balance_t_ha"
    ].value / cfg["humus_t_per_point"].value
    assert years[0]["soil_index"] == pytest.approx(cfg["start"] + step, abs=0.01)
    legumes = rotation.simulate(rules, cond, ["wheat", "pea"], [], 4, 2027)["totals"]
    mono = rotation.simulate(rules, cond, ["wheat"], [], 4, 2027)["totals"]
    assert legumes["nitrogen_kg_ha"] > mono["nitrogen_kg_ha"]
    assert legumes["soil_index_end"] > mono["soil_index_end"]


# ---- объяснения --------------------------------------------------------------------
def test_explanations_exist_in_both_languages(rules, cond):
    res = explain.attach_explanations(rules, run(rules, cond))
    kazakh_letters = set("әғқңөұүһі")
    for v in res["variants"]:
        assert v["explanation"], v["id"]
        for line in v["explanation"]:
            assert line["ru"] and line["kk"] and line["ru"] != line["kk"]
            assert "{" not in line["ru"] and "{" not in line["kk"]
        assert kazakh_letters & set("".join(line["kk"] for line in v["explanation"]).lower())
    codes = {line["code"] for line in by_id(res)["lentil_flax"]["explanation"]}
    assert {"legume_then_cereal", "drought_compare", "assumptions"} <= codes
    assert "monoculture" in {line["code"] for line in by_id(res)["wheat_mono"]["explanation"]}
    assert "fallow_last" in {line["code"] for line in by_id(res)["pea_rapeseed_fallow"]["explanation"]}


@pytest.mark.parametrize(
    "n, ru", [(1, "1 год"), (3, "3 года"), (4, "4 года"), (5, "5 лет"), (11, "11 лет"), (21, "21 год")]
)
def test_years_phrase(n, ru):
    assert explain.years_phrase(n)["ru"] == ru


def test_param_reference_keeps_source_and_status(rules):
    p: Param = rules.crop("wheat")["price_kzt_t"]
    ref = p.ref()
    assert ref["status"] in ("verified", "assumption") and ref["source"] and ref["url"]
