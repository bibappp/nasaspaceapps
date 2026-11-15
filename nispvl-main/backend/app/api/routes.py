"""Маршруты API."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .. import jobs
from ..config import get_settings
from ..data_sources.base import demo_field_record
from ..data_sources.registry import describe_sources
from ..geometry import GeometryError
from ..model.rules import EVIDENCE, RulesError, get_rules
from ..schemas import CompareRequest, FieldRequest, ReportRequest, RetroSubmission
from ..services import layers
from ..services.analysis import AnalysisError, analyze
from ..services.comparison import default_variants, run_compare

router = APIRouter(prefix="/api")


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    return {"status": "ok", "offline": s.offline, "earthdata": s.has_earthdata, "demo": demo_field_record() is not None}


@router.get("/config")
async def config() -> dict:
    """Справочники для интерфейса: культуры, области, приоритеты, варианты по умолчанию."""
    rules = get_rules()
    m = rules.model
    return {
        "crops": [
            {
                "id": cid,
                "name": c["name"],
                "short": c["short"],
                "group": c["group"],
                "nitrogen_fixing": c["nitrogen_fixing"],
            }
            for cid, c in rules.crops.items()
        ],
        "regions": [{"id": rid, "name": r["name"]} for rid, r in rules.regions.items()],
        "priorities": [
            {"id": pid, "name": p["name"], "weights": p["weights"].value} for pid, p in m["priorities"].items()
        ],
        "default_variants": default_variants(rules),
        "horizon": m["horizon"],
        "history": m["history"],
        "season_months": m["season"]["months"],
        "presowing_months": m["presowing"]["months"],
    }


@router.post("/field/analyze")
async def field_analyze(req: FieldRequest) -> dict:
    try:
        rules = get_rules()
        for crop in req.history_crops():
            rules.crop(crop)
        result = await analyze(req.geometry, req.region, start_jobs=True, rules=rules)
    except (GeometryError, RulesError, ValueError) as exc:
        raise _bad_request(exc) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return result.response


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.as_dict()


@router.post("/rotations/compare")
async def rotations_compare(req: CompareRequest) -> dict:
    try:
        result, _ = await run_compare(req)
    except (GeometryError, RulesError, ValueError) as exc:
        raise _bad_request(exc) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return result


@router.get("/layers/{kind}")
async def layer(
    kind: str,
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat"),
    date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict:
    if kind not in layers.KINDS:
        raise HTTPException(status_code=404, detail=f"unknown layer '{kind}'")
    try:
        return await layers.build_layer(kind, layers.parse_bbox(bbox), date)
    except GeometryError as exc:
        raise _bad_request(exc) from exc
    except layers.LayerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/report/pdf")
async def report_pdf(req: ReportRequest) -> Response:
    """PDF по контуру без учётной записи (совместимость с первой версией API)."""
    from ..report.pdf import build_report
    from ..services.report_data import gather

    try:
        data = await gather(req)
    except (GeometryError, RulesError, ValueError) as exc:
        raise _bad_request(exc) from exc
    except AnalysisError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    pdf = build_report(data, lang=req.lang, selected_variant_id=req.selected_variant_id, farm_name=req.farm_name)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{report_filename(req.lang, "pdf")}"'})


def report_filename(lang: str, ext: str, field_name: str = "") -> str:
    base = {"ru": "agro-sevooborot-report", "kk": "agro-auyspaly-egis-esep", "en": "agro-sevooborot-report"}.get(lang, "agro-sevooborot-report")
    return f"{base}.{ext}"


@router.get("/demo")
async def demo() -> dict:
    """Готовое демо-поле: контур, область, история, приоритет."""
    rec = demo_field_record()
    if rec is None:
        raise HTTPException(status_code=404, detail="demo field is not built yet: run scripts/build_demo.py")
    return rec


@router.get("/rules")
async def rules_catalog() -> dict:
    """Все правила модели со статусами и источниками — для страницы «Методика»."""
    rules = get_rules()
    params = [p.as_dict() for p in rules.all_params()]
    return {
        "params": params,
        "counts": {
            "total": len(params),
            "verified": sum(1 for p in params if p["status"] == "verified"),
            "assumption": sum(1 for p in params if p["status"] == "assumption"),
            "by_evidence": {e: sum(1 for p in params if p["evidence"] == e) for e in sorted(EVIDENCE)},
        },
        "predecessors": [
            {"id": r["id"], "predecessor": r["predecessor"], "crop": r["crop"], "same": bool(r.get("same")), **r["yield_effect_pct"].as_dict()}
            for r in rules.predecessors
        ],
        "rule_sources": [{"id": k, **v} for k, v in rules.sources.items()],
        "todo_sources": rules.todo_sources(),
        "data_sources": describe_sources(),
    }


@router.get("/content/landing")
async def landing_sources() -> dict:
    """Сноски лендинга из content/sources.yaml."""
    path = get_settings().content_dir / "sources.yaml"
    if not path.exists():
        return {"facts": {}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"facts": {}}


def _retro_dir():
    return get_settings().data_dir / "retro"


@router.get("/retro")
async def retro_fields() -> dict:
    """Поля с подтверждённой историей культур (кладутся вручную в data/retro/verified/*.json)."""
    out = []
    verified = _retro_dir() / "verified"
    if verified.exists():
        for path in sorted(verified.glob("*.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
    return {"fields": out}


@router.post("/retro/submissions", status_code=201)
async def retro_submit(sub: RetroSubmission) -> dict:
    """Заявка на добавление поля. Сохраняется как неподтверждённая и на сайте не показывается."""
    if not sub.consent:
        raise HTTPException(status_code=422, detail="consent is required")
    try:
        get_rules().region(sub.region)
    except RulesError as exc:
        raise _bad_request(exc) from exc
    folder = _retro_dir() / "submissions"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9]+", "-", sub.farm_name.lower())[:30].strip("-") or "field"
    path = folder / f"{stamp}-{slug}.json"
    path.write_text(
        json.dumps({"received_at": stamp, "status": "unverified", **sub.model_dump()}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return {"status": "received", "id": path.stem}
