"""Сравнение севооборотов для поля: анализ данных -> модель -> объяснения."""
from __future__ import annotations

from ..analytics import scenario_exposure
from ..model import explain, rotation
from ..model.rules import Rules, get_rules
from ..schemas import CompareRequest
from .analysis import Analysis, analyze
from .bare_soil import planner_climate


def default_variants(rules: Rules) -> list[dict]:
    return [{"id": v["id"], "name": v["name"], "crops": list(v["crops"])} for v in rules.model["default_variants"]]


def validate_request(req: CompareRequest, rules: Rules) -> list[dict]:
    rules.region(req.region)
    for crop in req.history_crops():
        rules.crop(crop)
    if req.priority not in rules.model["priorities"]:
        raise ValueError(f"unknown priority '{req.priority}'")
    if req.weights is not None:
        rotation.normalize_weights(req.weights)
    variants = [v.model_dump() for v in req.variants] if req.variants else default_variants(rules)
    ids = [v["id"] for v in variants]
    if len(set(ids)) != len(ids):
        raise ValueError("variant ids must be unique")
    for v in variants:
        for crop in v["crops"]:
            rules.crop(crop)
    return variants


async def run_compare(req: CompareRequest, *, start_jobs: bool = False) -> tuple[dict, Analysis]:
    rules = get_rules()
    variants = validate_request(req, rules)
    analysis = await analyze(req.geometry, req.region, start_jobs=start_jobs, rules=rules, stress_year=req.stress_year)
    result = rotation.compare(
        rules,
        analysis.conditions,
        variants,
        req.history_crops(),
        req.horizon_years,
        req.priority,
        req.start_year,
        weights=req.weights,
    )
    explain.attach_explanations(rules, result)
    # дни без покрова и индекс опасности эрозии: только показываются, в балл и рейтинг не входят (MODEL_AUDIT.md § 7)
    scenario_exposure.attach(rules, result, await planner_climate(analysis.field, rules), req.region)
    result["priority_name"] = rules.model["priorities"][req.priority]["name"]
    result["history"] = [h.model_dump() for h in sorted(req.history, key=lambda h: h.year)]
    result["field"] = analysis.response["field"]
    result["drought"] = {
        "stress_year": analysis.response["drought"]["stress_year"],
        "stress_year_reason": analysis.response["drought"]["stress_year_reason"],
        "dry_years": analysis.response["drought"]["dry_years"],
        "share": analysis.response["drought"]["share"],
        "every_nth": analysis.response["drought"]["every_nth"],
    }
    result["moisture_state"] = analysis.response["soil_moisture"]["state"]
    result["warnings"] = analysis.response["warnings"]
    return result, analysis
