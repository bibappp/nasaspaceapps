"""Учётные записи, поля, анализы: безопасность и изоляция данных пользователей."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.config import get_settings
from app.data_sources.base import demo_field_record
from app.main import app

pytestmark = pytest.mark.skipif(demo_field_record() is None, reason="нет data/demo")
H = {"X-Requested-With": "agro"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "db_path", tmp_path / "test.db")
    monkeypatch.setattr(s, "offline", True)
    auth._failed.clear()
    yield tmp_path


def client() -> TestClient:
    return TestClient(app)


def register(c: TestClient, email="farmer@example.org", password="correct horse 1"):
    return c.post("/api/auth/register", json={"email": email, "password": password, "name": "Айгерім"}, headers=H)


def field_body(**kw):
    demo = demo_field_record()
    body = {"name": "Северное поле", "region": "akmola", "geometry": demo["geometry"],
            "history": [{"year": y, "crop": "wheat"} for y in range(2022, 2027)], "notes": "Пробное поле",
            "soil": {"humus_pct": 4.2, "ph": 7.1, "texture": "loam"}}
    return {**body, **kw}


def test_register_login_logout_and_password_is_hashed(env):
    with client() as c:
        r = register(c)
        assert r.status_code == 201 and r.json()["email"] == "farmer@example.org"
        assert c.get("/api/auth/me").json()["name"] == "Айгерім"
        assert c.post("/api/auth/logout", headers=H).status_code == 200
        assert c.get("/api/auth/me").status_code == 401
        assert c.post("/api/auth/login", json={"email": "FARMER@example.org", "password": "correct horse 1"}, headers=H).status_code == 200
        assert c.get("/api/auth/me").status_code == 200
    with sqlite3.connect(env / "test.db") as conn:
        stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored.startswith("scrypt$") and "correct horse" not in stored
    assert auth.verify_password("correct horse 1", stored) and not auth.verify_password("wrong", stored)


def test_session_cookie_is_httponly(env):
    with client() as c:
        r = register(c)
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie


@pytest.mark.parametrize("email, password, code", [("bad-email", "longenough1", 422), ("a@b.org", "short", 422)])
def test_registration_validation(env, email, password, code):
    with client() as c:
        assert register(c, email, password).status_code == code


def test_duplicate_email_rejected(env):
    with client() as c:
        register(c)
    with client() as c2:
        assert register(c2).status_code == 409


def test_wrong_password_and_rate_limit(env):
    with client() as c:
        register(c)
        c.post("/api/auth/logout", headers=H)
        for _ in range(auth.MAX_FAILS):
            assert c.post("/api/auth/login", json={"email": "farmer@example.org", "password": "nope-nope"}, headers=H).status_code == 401
        r = c.post("/api/auth/login", json={"email": "farmer@example.org", "password": "correct horse 1"}, headers=H)
        assert r.status_code == 429


def test_csrf_header_required_for_changes(env):
    with client() as c:
        register(c)
        assert c.post("/api/fields", json=field_body()).status_code == 403
        assert c.post("/api/fields", json=field_body(), headers=H).status_code == 201


def test_unauthenticated_access_denied(env):
    with client() as c:
        assert c.get("/api/fields").status_code == 401
        assert c.get("/api/analyses").status_code == 401


def test_field_crud(env):
    with client() as c:
        register(c)
        f = c.post("/api/fields", json=field_body(), headers=H).json()
        assert 250 < f["area_ha"] < 400 and f["soil"]["ph"] == 7.1 and len(f["history"]) == 5
        fid = f["id"]
        assert [x["id"] for x in c.get("/api/fields").json()["fields"]] == [fid]
        upd = c.put(f"/api/fields/{fid}", json=field_body(name="Поле у дороги", history=[{"year": 2025, "crop": "pea"}]), headers=H).json()
        assert upd["name"] == "Поле у дороги" and upd["history"] == [{"year": 2025, "crop": "pea"}]
        bad = c.put(f"/api/fields/{fid}", json=field_body(history=[{"year": 2025, "crop": "banana"}]), headers=H)
        assert bad.status_code == 422
        assert c.delete(f"/api/fields/{fid}", headers=H).status_code == 204
        assert c.get(f"/api/fields/{fid}").status_code == 404


def test_users_cannot_see_each_others_data(env):
    with client() as a:
        register(a, "a@example.org")
        fid = a.post("/api/fields", json=field_body(), headers=H).json()["id"]
        aid = a.post(f"/api/fields/{fid}/analyses", json={"priority": "max_income"}, headers=H).json()["id"]
    with client() as b:
        register(b, "b@example.org")
        assert b.get("/api/fields").json()["fields"] == []
        assert b.get(f"/api/fields/{fid}").status_code == 404
        assert b.put(f"/api/fields/{fid}", json=field_body(), headers=H).status_code == 404
        assert b.delete(f"/api/fields/{fid}", headers=H).status_code == 404
        assert b.post(f"/api/fields/{fid}/analyses", json={}, headers=H).status_code == 404
        assert b.get(f"/api/analyses/{aid}").status_code == 404
        assert b.delete(f"/api/analyses/{aid}", headers=H).status_code == 404
        assert b.get("/api/analyses").json()["analyses"] == []
        assert b.get(f"/api/fields/{fid}/monitoring").status_code == 404


def test_saved_analysis_can_be_reopened(env):
    with client() as c:
        register(c)
        fid = c.post("/api/fields", json=field_body(), headers=H).json()["id"]
        r = c.post(f"/api/fields/{fid}/analyses", json={"priority": "restore_soil", "title": "Весна 2027"}, headers=H)
        assert r.status_code == 201
        a = r.json()
        assert a["summary"]["priority"] == "restore_soil" and a["result"]["variants"]
        again = c.get(f"/api/analyses/{a['id']}").json()
        assert again["result"] == a["result"] and again["title"] == "Весна 2027"
        assert c.get(f"/api/fields/{fid}/analyses").json()["analyses"][0]["id"] == a["id"]
        assert c.delete(f"/api/analyses/{a['id']}", headers=H).status_code == 204


def test_custom_weights_change_ranking_and_are_validated(env):
    with client() as c:
        register(c)
        fid = c.post("/api/fields", json=field_body(), headers=H).json()["id"]
        soil = c.post(f"/api/fields/{fid}/analyses", json={"weights": {"soil": 1, "water": 0, "income": 0, "risk": 0}}, headers=H).json()
        water = c.post(f"/api/fields/{fid}/analyses", json={"weights": {"soil": 0, "water": 1, "income": 0, "risk": 0}}, headers=H).json()
        assert soil["summary"]["weights"] == {"soil": 1.0, "water": 0.0, "income": 0.0, "risk": 0.0}
        assert soil["summary"]["weights_custom"] is True
        assert soil["summary"]["best_variant_id"] != water["summary"]["best_variant_id"]
        r = c.post(f"/api/fields/{fid}/analyses", json={"weights": {"soil": -1, "water": 1, "income": 0, "risk": 0}}, headers=H)
        assert r.status_code == 422


def test_stress_year_must_be_a_dry_year(env):
    with client() as c:
        register(c)
        fid = c.post("/api/fields", json=field_body(), headers=H).json()["id"]
        ok = c.post(f"/api/fields/{fid}/analyses", json={"stress_year": 2010}, headers=H).json()
        assert ok["result"]["drought"]["stress_year"] == 2010
        assert ok["result"]["conditions"]["dry_year"] == 2010
        assert c.post(f"/api/fields/{fid}/analyses", json={"stress_year": 2024}, headers=H).status_code == 422


def test_economics_and_confidence_in_results(env):
    with client() as c:
        register(c)
        fid = c.post("/api/fields", json=field_body(), headers=H).json()["id"]
        v = c.post(f"/api/fields/{fid}/analyses", json={}, headers=H).json()["result"]["variants"][1]
        e = v["economics"]
        assert e["gross_margin_kzt_ha"] == e["revenue_kzt_ha"] - e["cost_kzt_ha"] == v["totals"]["income_kzt_ha"]
        assert e["margin_price_plus20_kzt_ha"] - e["margin_price_minus20_kzt_ha"] == pytest.approx(0.4 * e["revenue_kzt_ha"], abs=2)
        conf = v["confidence"]
        assert conf["level"] in ("low", "medium", "high") and 0 <= conf["share"] <= 1
        assert conf["params_supported"] <= conf["params_total"] == v["params_used"]


def test_demo_sandbox_is_isolated_and_seeded(env):
    with client() as c:
        r = c.post("/api/auth/demo", headers=H)
        assert r.status_code == 201 and r.json()["is_demo"] is True
        fields = c.get("/api/fields").json()["fields"]
        assert len(fields) >= 1 and all(f["n_analyses"] == 1 for f in fields)
    with client() as other:
        other.post("/api/auth/demo", headers=H)
        assert {f["id"] for f in other.get("/api/fields").json()["fields"]}.isdisjoint({f["id"] for f in fields})
