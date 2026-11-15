"""Поля и сохранённые анализы пользователя. Все запросы фильтруются по user_id:
чужое поле или анализ для пользователя не существуют (ответ 404, без раскрытия факта существования)."""
from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

from .. import db
from ..auth import hash_password
from ..data_sources.base import demo_field_records
from ..geometry import parse_field
from ..model.rules import get_rules
from ..schemas import AnalysisIn, CompareRequest, FieldIn
from .comparison import run_compare

FIELD_JSON = ("geometry", "soil", "history")


class NotFound(LookupError):
    pass


def _field_out(row: dict) -> dict:
    d = db.row_to_dict(row, FIELD_JSON)
    d["history_is_scenario"] = bool(d["history_is_scenario"])
    d.pop("user_id", None)
    return d


def validate_field(data: FieldIn) -> dict:
    rules = get_rules()
    rules.region(data.region)
    for h in data.history:
        rules.crop(h.crop)
    f = parse_field(data.geometry)
    return {
        "name": data.name.strip(),
        "region": data.region,
        "geometry": json.dumps(f.geojson()),
        "area_ha": round(f.area_ha, 2),
        "centroid_lat": round(f.centroid_lat, 6),
        "centroid_lon": round(f.centroid_lon, 6),
        "soil": json.dumps(data.soil.model_dump()),
        "notes": data.notes,
        "history": json.dumps([h.model_dump() for h in data.history]),
        "history_is_scenario": int(data.history_is_scenario),
    }


def list_fields(user_id: int) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT f.*, (SELECT COUNT(*) FROM analyses a WHERE a.field_id = f.id) AS n_analyses,
                      (SELECT MAX(created_at) FROM analyses a WHERE a.field_id = f.id) AS last_analysis_at
               FROM fields f WHERE f.user_id = ? ORDER BY f.updated_at DESC""",
            (user_id,),
        ).fetchall()
    return [_field_out(r) for r in rows]


def get_field(user_id: int, field_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM fields WHERE id = ? AND user_id = ?", (field_id, user_id)).fetchone()
    if row is None:
        raise NotFound("field")
    return _field_out(row)


def create_field(user_id: int, data: FieldIn) -> dict:
    v = validate_field(data)
    now = db.now_iso()
    with db.connect() as conn:
        cur = conn.execute(
            f"""INSERT INTO fields (user_id, {", ".join(v)}, created_at, updated_at)
                VALUES (?, {", ".join("?" for _ in v)}, ?, ?)""",
            (user_id, *v.values(), now, now),
        )
        field_id = cur.lastrowid
    return get_field(user_id, field_id)


def update_field(user_id: int, field_id: int, data: FieldIn) -> dict:
    get_field(user_id, field_id)
    v = validate_field(data)
    with db.connect() as conn:
        conn.execute(
            f"UPDATE fields SET {', '.join(f'{k} = ?' for k in v)}, updated_at = ? WHERE id = ? AND user_id = ?",
            (*v.values(), db.now_iso(), field_id, user_id),
        )
    return get_field(user_id, field_id)


def delete_field(user_id: int, field_id: int) -> None:
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM fields WHERE id = ? AND user_id = ?", (field_id, user_id))
    if cur.rowcount == 0:
        raise NotFound("field")


# ---------------------------------------------------------------- анализы
def compare_request(field: dict, a: AnalysisIn) -> CompareRequest:
    return CompareRequest(
        geometry=field["geometry"],
        region=field["region"],
        history=field["history"],
        priority=a.priority,
        horizon_years=a.horizon_years,
        variants=a.variants,
        start_year=a.start_year,
        weights=a.weights,
        stress_year=a.stress_year,
    )


def _summary(result: dict) -> dict:
    best = next(v for v in result["variants"] if v["id"] == result["best_variant_id"])
    return {
        "best_variant_id": best["id"],
        "best_variant_name": best.get("name"),
        "best_crops": best["crops"],
        "priority": result["priority"],
        "weights": {k: v for k, v in result["weights"].items() if k != "_rule"},
        "weights_custom": result.get("weights_custom", False),
        "horizon_years": result["horizon_years"],
        "start_year": result["start_year"],
        "stress_year": result["drought"]["stress_year"],
        "variants": [
            {"id": v["id"], "name": v.get("name"), "crops": v["crops"], "weighted_score": v["weighted_score"],
             "gross_margin_kzt_ha": v["economics"]["gross_margin_kzt_ha"], "confidence": v["confidence"]["level"]}
            for v in result["variants"]
        ],
    }


async def create_analysis(user_id: int, field_id: int, a: AnalysisIn) -> dict:
    field = get_field(user_id, field_id)
    req = compare_request(field, a)
    result, _ = await run_compare(req)
    summary = _summary(result)
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO analyses (user_id, field_id, title, request, summary, result, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, field_id, a.title, a.model_dump_json(), json.dumps(summary, ensure_ascii=False),
             json.dumps(result, ensure_ascii=False), db.now_iso()),
        )
        aid = cur.lastrowid
    return get_analysis(user_id, aid)


def list_analyses(user_id: int, field_id: int | None = None, limit: int = 50) -> list[dict]:
    q = """SELECT a.id, a.field_id, a.title, a.summary, a.created_at, f.name AS field_name
           FROM analyses a JOIN fields f ON f.id = a.field_id WHERE a.user_id = ?"""
    args: list = [user_id]
    if field_id is not None:
        q += " AND a.field_id = ?"
        args.append(field_id)
    q += " ORDER BY a.created_at DESC, a.id DESC LIMIT ?"
    args.append(limit)
    with db.connect() as conn:
        rows = conn.execute(q, args).fetchall()
    return [db.row_to_dict(r, ("summary",)) for r in rows]


def get_analysis(user_id: int, analysis_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            """SELECT a.*, f.name AS field_name FROM analyses a JOIN fields f ON f.id = a.field_id
               WHERE a.id = ? AND a.user_id = ?""",
            (analysis_id, user_id),
        ).fetchone()
    if row is None:
        raise NotFound("analysis")
    d = db.row_to_dict(row, ("request", "summary", "result"))
    d.pop("user_id", None)
    return d


def delete_analysis(user_id: int, analysis_id: int) -> None:
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM analyses WHERE id = ? AND user_id = ?", (analysis_id, user_id))
    if cur.rowcount == 0:
        raise NotFound("analysis")


# ---------------------------------------------------------------- демо-песочница
def cleanup_demo_users(ttl_days: int) -> int:
    cutoff = (datetime.now(UTC) - timedelta(days=ttl_days)).isoformat(timespec="seconds")
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE is_demo = 1 AND created_at < ?", (cutoff,))
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now_iso(),))
    return cur.rowcount


async def create_demo_user(lang: str = "ru") -> dict:
    """Отдельная песочница для каждого посетителя: демо-поля с сохранёнными данными и по одному анализу."""
    email = f"demo-{secrets.token_hex(6)}@demo.invalid"
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, name, farm_name, lang, password_hash, is_demo, created_at) VALUES (?,?,?,?,?,1,?)",
            (email, "Demo", "", lang, hash_password(secrets.token_urlsafe(24)), db.now_iso()),
        )
        user_id = cur.lastrowid
    for rec in demo_field_records():
        name = rec["name"].get(lang) or rec["name"]["ru"]
        note = rec.get("history_note", {}).get(lang) or rec.get("history_note", {}).get("ru", "")
        field = create_field(
            user_id,
            FieldIn(name=name, region=rec["region"], geometry=rec["geometry"], history=rec["history"],
                    history_is_scenario=bool(rec.get("history_is_scenario")), notes=note),
        )
        await create_analysis(user_id, field["id"], AnalysisIn(priority=rec.get("priority", "max_income"),
                                                                horizon_years=rec.get("horizon_years", 4)))
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row)
