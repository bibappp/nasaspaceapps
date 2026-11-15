"""Источники данных: кэш, fallback, офлайн, разбор ответов API."""
from __future__ import annotations

import asyncio
import json
from datetime import date

import httpx
import pytest

from app import cache
from app.config import get_settings
from app.data_sources import base, power, soilgrids
from app.geometry import parse_field

FIELD = {"type": "Polygon", "coordinates": [[[70.0, 52.0], [70.02, 52.0], [70.02, 52.01], [70.0, 52.01], [70.0, 52.0]]]}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _reset_failures():
    base._failures.clear()
    yield
    base._failures.clear()


def _mock_transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(base.httpx, "AsyncClient", factory)


def test_power_response_is_parsed_and_cached(tmp_data, monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        assert request.url.params["community"] == "AG"
        body = {
            "geometry": {"coordinates": [70.01, 52.0, 300.0]},
            "header": {"api": {"version": "test"}, "sources": ["MERRA2"]},
            "parameters": {"PRECTOTCORR": {"units": "mm/day"}},
            "properties": {"parameter": {p: {"20200101": 1.5, "20200102": -999.0} for p in power.PARAMETERS}},
        }
        return httpx.Response(200, json=body)

    _mock_transport(monkeypatch, handler)
    f = parse_field(FIELD)
    src = power.PowerSource()
    r1 = run(src.fetch(f, date(2020, 1, 1), date(2020, 1, 2)))
    assert r1.origin == "live"
    assert r1.data["daily"]["PRECTOTCORR"] == [1.5, None]  # -999 -> пропуск
    r2 = run(src.fetch(f, date(2020, 1, 1), date(2020, 1, 2)))
    assert r2.origin == "cache" and len(calls) == 1


def test_soilgrids_failure_falls_back_to_demo_with_warning(tmp_data, monkeypatch):
    (tmp_data / "demo" / "soilgrids.json").write_text(json.dumps({"properties": {"x": 1}}), encoding="utf-8")
    _mock_transport(monkeypatch, lambda req: httpx.Response(503, text="Service Temporarily Unavailable"))
    res = run(soilgrids.SoilGridsSource().fetch(parse_field(FIELD), date(2020, 1, 1), date(2020, 1, 2)))
    assert res.origin == "fallback"
    codes = [w.code for w in res.warnings]
    assert "source_unavailable" in codes and "soil_fallback_demo" in codes


def test_failed_source_is_not_retried_immediately(tmp_data, monkeypatch):
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    _mock_transport(monkeypatch, handler)
    src = soilgrids.SoilGridsSource()
    run(src.fetch(parse_field(FIELD), date(2020, 1, 1), date(2020, 1, 2)))
    run(src.fetch(parse_field(FIELD), date(2020, 1, 1), date(2020, 1, 2)))
    assert len(calls) == 1  # пауза после сбоя: пользователь не ждёт тайм-аут повторно


def test_offline_mode_makes_no_requests(tmp_data, monkeypatch):
    monkeypatch.setattr(get_settings(), "offline", True)

    def handler(req):
        raise AssertionError("network used in offline mode")

    _mock_transport(monkeypatch, handler)
    res = run(power.PowerSource().fetch(parse_field(FIELD), date(2020, 1, 1), date(2020, 1, 2)))
    assert res.origin == "unavailable"
    assert [w.code for w in res.warnings] == ["offline_no_cache"]


def test_demo_field_reads_saved_demo_data(tmp_data):
    (tmp_data / "demo" / "field.json").write_text(json.dumps({"geometry": FIELD}), encoding="utf-8")
    (tmp_data / "demo" / "power.json").write_text(json.dumps({"daily": {}, "cached_at": "x"}), encoding="utf-8")
    res = run(power.PowerSource().fetch(parse_field(FIELD), date(2020, 1, 1), date(2020, 1, 2)))
    assert res.origin == "demo"


def test_cache_key_depends_on_geometry_and_period():
    f1 = parse_field(FIELD)
    other = json.loads(json.dumps(FIELD))
    other["coordinates"][0][1][0] = 70.03
    f2 = parse_field(other)
    src = soilgrids.SoilGridsSource()
    k = src.cache_key(f1, date(2020, 1, 1), date(2020, 1, 2))
    assert k != cache.make_key("modis", geometry=f1.canonical())
    assert len(k) == 32
    m = __import__("app.data_sources.modis", fromlist=["ModisSource"]).ModisSource()
    assert m.cache_key(f1, date(2000, 1, 1), date(2020, 1, 1)) != m.cache_key(f2, date(2000, 1, 1), date(2020, 1, 1))
    assert m.cache_key(f1, date(2000, 1, 1), date(2020, 1, 1)) != m.cache_key(f1, date(2000, 1, 1), date(2021, 1, 1))


def test_planned_sources_are_registered_but_disabled():
    from app.data_sources.registry import SOURCES, describe_sources

    assert not SOURCES["gpm"].enabled and not SOURCES["landsat"].enabled
    states = {s["id"]: s["state"] for s in describe_sources()}
    assert states["gpm"] == states["landsat"] == "planned"
    for s in describe_sources():
        for key in ("spatial_resolution", "temporal_coverage", "provenance", "access", "limitations"):
            assert s[key]["ru"] and s[key]["kk"], (s["id"], key)
