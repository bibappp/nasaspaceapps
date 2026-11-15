"""API на сохранённых демо-данных в режиме OFFLINE (без сети)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.data_sources.base import demo_field_record
from app.main import app

pytestmark = pytest.mark.skipif(demo_field_record() is None, reason="нет data/demo: запустите scripts/build_demo.py")


@pytest.fixture(scope="module")
def client():
    settings = get_settings()
    old = settings.offline
    settings.offline = True
    try:  # вернуть настройку, даже если запуск приложения упал: иначе следующие модули тестов идут в OFFLINE
        with TestClient(app) as c:
            yield c
    finally:
        settings.offline = old


@pytest.fixture(scope="module")
def demo(client):
    return client.get("/api/demo").json()


def _req(demo, **extra):
    return {"geometry": demo["geometry"], "region": demo["region"], "history": demo["history"],
            "priority": demo["priority"], "horizon_years": demo["horizon_years"], **extra}


def test_health_and_config(client):
    assert client.get("/api/health").json()["offline"] is True
    cfg = client.get("/api/config").json()
    assert len(cfg["default_variants"]) == 4 and len(cfg["crops"]) == 8


def test_analyze_demo_offline(client, demo):
    r = client.post("/api/field/analyze", json=_req(demo))
    assert r.status_code == 200
    a = r.json()
    assert {s["source"]: s["origin"] for s in a["sources"]} == {"power": "demo", "soilgrids": "demo", "modis": "demo", "smap": "demo"}
    assert a["field"]["is_demo"] and 250 < a["field"]["area_ha"] < 500
    assert a["drought"]["window"]["n_years"] == 25
    assert a["ndvi"]["trend"]["label"] in ("rising", "declining", "stable")
    assert a["soil_moisture"]["basis"] == "smap"
    codes = {w["code"] for w in a["warnings"]}
    assert {"resolution_power", "resolution_smap", "soil_is_model_map"} <= codes


def test_compare_demo_and_custom_variant(client, demo):
    variants = [{"id": "a", "crops": ["wheat"] * 4}, {"id": "b", "crops": ["wheat", "pea", "wheat", "flax"], "custom": True}]
    r = client.post("/api/rotations/compare", json=_req(demo, variants=variants))
    assert r.status_code == 200
    c = r.json()
    assert [v["id"] for v in c["variants"]] == ["a", "b"]
    assert sum(v["fits_priority"] for v in c["variants"]) == 1
    for v in c["variants"]:
        assert set(v["scores"]) == {"soil", "water", "income", "risk"}
        assert v["explanation"] and all(e["ru"] and e["kk"] for e in v["explanation"])


@pytest.mark.parametrize("kind", ["ndvi", "soil_moisture", "precip"])
def test_layers(client, demo, kind):
    bbox = client.post("/api/field/analyze", json=_req(demo)).json()["field"]["bbox"]
    r = client.get(f"/api/layers/{kind}", params={"bbox": ",".join(map(str, bbox))})
    assert r.status_code == 200
    layer = r.json()
    assert layer["features"] and layer["meta"]["dates"] and layer["meta"]["spatial_resolution"]["ru"]


def test_pdf_endpoint(client, demo):
    r = client.post("/api/report/pdf", json=_req(demo, lang="kk", farm_name="Қарағай"))
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_rules_catalog(client):
    r = client.get("/api/rules").json()
    assert r["counts"]["total"] == r["counts"]["verified"] + r["counts"]["assumption"]
    assert {s["id"] for s in r["data_sources"]} >= {"power", "modis", "smap", "soilgrids", "gpm", "landsat"}


@pytest.mark.parametrize(
    "patch, status",
    [
        ({"region": "mars"}, 422),
        ({"priority": "nope"}, 422),
        ({"horizon_years": 9}, 422),
        ({"history": [{"year": 2025, "crop": "banana"}]}, 422),
        ({"geometry": {"type": "Point", "coordinates": [70, 52]}}, 422),
    ],
)
def test_validation_errors(client, demo, patch, status):
    assert client.post("/api/rotations/compare", json={**_req(demo), **patch}).status_code == status


def test_unknown_layer_404(client):
    assert client.get("/api/layers/lava?bbox=70,51,71,52").status_code == 404


def test_retro_submission_saved_as_unverified(client, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    body = {"farm_name": "Тест", "contact": "test@example.com", "region": "akmola",
            "history": [{"year": 2023, "crop": "pea"}, {"year": 2024, "crop": "wheat"}], "consent": True}
    r = client.post("/api/retro/submissions", json=body)
    assert r.status_code == 201
    saved = list((tmp_path / "retro" / "submissions").glob("*.json"))
    assert len(saved) == 1 and json.loads(saved[0].read_text(encoding="utf-8"))["status"] == "unverified"
    assert client.get("/api/retro").json()["fields"] == []  # неподтверждённые заявки не публикуются
