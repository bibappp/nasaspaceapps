"""Маршруты учётных записей, полей и сохранённых анализов."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import auth, db
from ..config import get_settings
from ..geometry import GeometryError, parse_field
from ..model.rules import RulesError
from ..schemas import AnalysisIn, BareSoilOut, FieldIn, LoginIn, ProfileIn, RegisterIn
from ..services import bare_soil as bare_soil_svc
from ..services import fields as fs
from ..services import layers as layer_svc
from ..services import monitoring as mon
from ..services.analysis import AnalysisError, analyze

router = APIRouter(prefix="/api")


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, fs.NotFound):
        return HTTPException(404, detail=f"{exc}_not_found")
    if isinstance(exc, AnalysisError | layer_svc.LayerError):
        return HTTPException(503, detail=str(exc))
    return HTTPException(422, detail=str(exc))


HANDLED = (fs.NotFound, GeometryError, RulesError, ValueError, AnalysisError, layer_svc.LayerError)


# ---------------------------------------------------------------- auth
@router.post("/auth/register", status_code=201)
async def register(body: RegisterIn, response: Response, _: None = Depends(auth.require_csrf)) -> dict:
    if not get_settings().allow_registration:
        raise HTTPException(403, detail="registration_disabled")
    email = auth.validate_credentials(body.email, body.password)
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, name, farm_name, lang, password_hash, created_at) VALUES (?,?,?,?,?,?)",
                (email, body.name.strip(), body.farm_name.strip(), body.lang, auth.hash_password(body.password), db.now_iso()),
            )
            uid = cur.lastrowid
            row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, detail="email_taken") from exc
    auth.create_session(response, uid)
    return auth.public_user(dict(row))


@router.post("/auth/login")
async def login(body: LoginIn, response: Response, _: None = Depends(auth.require_csrf)) -> dict:
    email = body.email.strip().lower()
    auth.check_rate(email)
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ? AND is_demo = 0", (email,)).fetchone()
    # проверяем хэш даже для несуществующего адреса, чтобы время ответа не выдавало наличие учётной записи
    stored = row["password_hash"] if row else auth.hash_password("timing-equaliser")
    if not auth.verify_password(body.password, stored) or row is None:
        auth.record_failure(email)
        raise HTTPException(401, detail="invalid_credentials")
    auth.clear_failures(email)
    auth.create_session(response, row["id"])
    return auth.public_user(dict(row))


@router.post("/auth/logout")
async def logout(request: Request, response: Response, _: None = Depends(auth.require_csrf)) -> dict:
    auth.destroy_session(request, response)
    return {"status": "ok"}


@router.post("/auth/demo", status_code=201)
async def demo_login(request: Request, response: Response, _: None = Depends(auth.require_csrf)) -> dict:
    """Демо без регистрации: отдельная песочница с демо-полями (удаляется через несколько дней)."""
    settings = get_settings()
    fs.cleanup_demo_users(settings.demo_ttl_days)
    lang = request.query_params.get("lang", "ru")
    if lang not in ("ru", "kk", "en"):
        lang = "ru"
    try:
        user = await fs.create_demo_user(lang)
    except HANDLED as exc:
        raise _err(exc) from exc
    auth.create_session(response, user["id"])
    return auth.public_user(user)


@router.get("/auth/me")
async def me(user: dict = Depends(auth.current_user)) -> dict:
    return auth.public_user(user)


@router.put("/auth/me")
async def update_me(body: ProfileIn, user: dict = Depends(auth.authed)) -> dict:
    with db.connect() as conn:
        conn.execute(
            "UPDATE users SET name = ?, farm_name = ?, lang = ? WHERE id = ?",
            (body.name.strip(), body.farm_name.strip(), body.lang, user["id"]),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return auth.public_user(dict(row))


# ---------------------------------------------------------------- поля
@router.get("/fields")
async def fields_list(user: dict = Depends(auth.current_user)) -> dict:
    return {"fields": fs.list_fields(user["id"])}


@router.post("/fields", status_code=201)
async def fields_create(body: FieldIn, user: dict = Depends(auth.authed)) -> dict:
    try:
        return fs.create_field(user["id"], body)
    except HANDLED as exc:
        raise _err(exc) from exc


@router.get("/fields/{field_id}")
async def fields_get(field_id: int, user: dict = Depends(auth.current_user)) -> dict:
    try:
        return fs.get_field(user["id"], field_id)
    except HANDLED as exc:
        raise _err(exc) from exc


@router.put("/fields/{field_id}")
async def fields_update(field_id: int, body: FieldIn, user: dict = Depends(auth.authed)) -> dict:
    try:
        return fs.update_field(user["id"], field_id, body)
    except HANDLED as exc:
        raise _err(exc) from exc


@router.delete("/fields/{field_id}", status_code=204)
async def fields_delete(field_id: int, user: dict = Depends(auth.authed)) -> Response:
    try:
        fs.delete_field(user["id"], field_id)
    except HANDLED as exc:
        raise _err(exc) from exc
    return Response(status_code=204)


# ---------------------------------------------------------------- анализы
@router.get("/analyses")
async def analyses_recent(limit: int = 20, user: dict = Depends(auth.current_user)) -> dict:
    return {"analyses": fs.list_analyses(user["id"], limit=min(max(limit, 1), 100))}


@router.get("/fields/{field_id}/analyses")
async def analyses_list(field_id: int, user: dict = Depends(auth.current_user)) -> dict:
    try:
        fs.get_field(user["id"], field_id)
    except HANDLED as exc:
        raise _err(exc) from exc
    return {"analyses": fs.list_analyses(user["id"], field_id)}


@router.post("/fields/{field_id}/analyses", status_code=201)
async def analyses_create(field_id: int, body: AnalysisIn, user: dict = Depends(auth.authed)) -> dict:
    try:
        return await fs.create_analysis(user["id"], field_id, body)
    except HANDLED as exc:
        raise _err(exc) from exc


@router.get("/analyses/{analysis_id}")
async def analyses_get(analysis_id: int, user: dict = Depends(auth.current_user)) -> dict:
    try:
        return fs.get_analysis(user["id"], analysis_id)
    except HANDLED as exc:
        raise _err(exc) from exc


@router.delete("/analyses/{analysis_id}", status_code=204)
async def analyses_delete(analysis_id: int, user: dict = Depends(auth.authed)) -> Response:
    try:
        fs.delete_analysis(user["id"], analysis_id)
    except HANDLED as exc:
        raise _err(exc) from exc
    return Response(status_code=204)


# ---------------------------------------------------------------- данные поля: обзор, мониторинг, история, риски
@router.get("/fields/{field_id}/overview")
async def field_overview(field_id: int, user: dict = Depends(auth.current_user)) -> dict:
    """Анализ данных поля (как /api/field/analyze) для сохранённого поля; запускает фоновые загрузки."""
    try:
        f = fs.get_field(user["id"], field_id)
        return (await analyze(f["geometry"], f["region"], start_jobs=True)).response
    except HANDLED as exc:
        raise _err(exc) from exc


@router.get("/fields/{field_id}/monitoring")
async def field_monitoring(field_id: int, start: str | None = None, end: str | None = None,
                           user: dict = Depends(auth.current_user)) -> dict:
    for v in (start, end):
        if v is not None and not (len(v) == 7 and v[4] == "-" and v[:4].isdigit() and v[5:].isdigit()):
            raise HTTPException(422, detail="start/end must be YYYY-MM")
    try:
        f = fs.get_field(user["id"], field_id)
        return await mon.monitoring(f["geometry"], f["region"], start, end)
    except HANDLED as exc:
        raise _err(exc) from exc


@router.get("/fields/{field_id}/bare-soil", response_model=BareSoilOut)
async def field_bare_soil(field_id: int, start_year: int | None = None, end_year: int | None = None,
                          user: dict = Depends(auth.current_user)) -> dict:
    """Часы голой почвы по месяцам. Форма ответа — docs/contracts/bare_soil.example.json."""
    try:
        f = fs.get_field(user["id"], field_id)
        return await bare_soil_svc.bare_soil(f["id"], f["geometry"], start_year, end_year,
                                            region=f["region"])
    except HANDLED as exc:
        raise _err(exc) from exc


@router.get("/fields/{field_id}/seasons")
async def field_seasons(field_id: int, user: dict = Depends(auth.current_user)) -> dict:
    try:
        f = fs.get_field(user["id"], field_id)
        return await mon.seasons(f["geometry"], f["region"])
    except HANDLED as exc:
        raise _err(exc) from exc


@router.get("/fields/{field_id}/risk")
async def field_risk(field_id: int, user: dict = Depends(auth.current_user)) -> dict:
    try:
        f = fs.get_field(user["id"], field_id)
        return await mon.risk(f["geometry"], f["region"])
    except HANDLED as exc:
        raise _err(exc) from exc


@router.get("/fields/{field_id}/suitability")
async def field_suitability(field_id: int, user: dict = Depends(auth.current_user)) -> dict:
    try:
        f = fs.get_field(user["id"], field_id)
        return await mon.suitability(f["geometry"], f["region"], f["history"])
    except HANDLED as exc:
        raise _err(exc) from exc


@router.get("/fields/{field_id}/layers/{kind}")
async def field_layer(field_id: int, kind: str, date: str | None = None, user: dict = Depends(auth.current_user)) -> dict:
    if kind not in layer_svc.KINDS:
        raise HTTPException(404, detail=f"unknown layer '{kind}'")
    try:
        f = fs.get_field(user["id"], field_id)
        return await layer_svc.build_layer_for_field(kind, parse_field(f["geometry"]), date)
    except HANDLED as exc:
        raise _err(exc) from exc


# ---------------------------------------------------------------- экспорт PDF и XLSX
async def _report_data(user: dict, field_id: int, analysis_id: int | None):
    from ..services.report_data import gather

    f = fs.get_field(user["id"], field_id)
    a_in = AnalysisIn()
    if analysis_id is not None:
        saved = fs.get_analysis(user["id"], analysis_id)
        if saved["field_id"] != field_id:
            raise fs.NotFound("analysis")
        a_in = AnalysisIn(**saved["request"])
    info = {"name": f["name"], "farm_name": user.get("farm_name", ""), "notes": f["notes"], "soil": f["soil"],
            "history_is_scenario": f["history_is_scenario"]}
    return await gather(fs.compare_request(f, a_in), info), f


@router.get("/fields/{field_id}/report.pdf")
async def field_report_pdf(field_id: int, lang: str = "ru", analysis_id: int | None = None, variant: str | None = None,
                           user: dict = Depends(auth.current_user)) -> Response:
    from ..report.pdf import build_report
    from .routes import report_filename

    if lang not in ("ru", "kk", "en"):
        raise HTTPException(422, detail="lang must be ru, kk or en")
    try:
        data, _ = await _report_data(user, field_id, analysis_id)
    except HANDLED as exc:
        raise _err(exc) from exc
    pdf = build_report(data, lang=lang, selected_variant_id=variant)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{report_filename(lang, "pdf")}"'})


@router.get("/fields/{field_id}/report.xlsx")
async def field_report_xlsx(field_id: int, lang: str = "ru", analysis_id: int | None = None,
                            user: dict = Depends(auth.current_user)) -> Response:
    from ..report.xlsx import build_workbook
    from .routes import report_filename

    if lang not in ("ru", "kk", "en"):
        raise HTTPException(422, detail="lang must be ru, kk or en")
    try:
        data, _ = await _report_data(user, field_id, analysis_id)
    except HANDLED as exc:
        raise _err(exc) from exc
    xlsx = build_workbook(data, lang=lang)
    return Response(xlsx, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{report_filename(lang, "xlsx")}"'})
