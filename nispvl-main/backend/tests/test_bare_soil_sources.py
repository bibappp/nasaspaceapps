"""Источники «Часов голой почвы» на записанных (синтетических) ответах: MODIS межсезонье и SMAP апрель–октябрь.
Сеть не используется: ответы — tests/fixtures/bare_soil (см. README там же)."""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.config import get_settings
from app.data_sources import base, modis, smap
from app.geometry import parse_field

FIX = Path(__file__).parent / "fixtures" / "bare_soil"
FIELD = {"type": "Polygon", "coordinates": [[[70.0, 52.0], [70.02, 52.0], [70.02, 52.01], [70.0, 52.01], [70.0, 52.0]]]}


@pytest.fixture(autouse=True)
def _reset_failures():
    base._failures.clear()
    yield
    base._failures.clear()


def _mock(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(base.httpx, "AsyncClient",
                        lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))


def _doy(param: str) -> tuple[int, int]:
    return int(param[1:5]), int(param[5:])


def modis_handler(calls: list[dict]):
    bodies = {band: json.loads((FIX / f"modis_subset_{band}.json").read_text()) for band in (modis.BAND_NDVI, modis.BAND_REL)}

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params
        (y0, d0), (y1, d1) = _doy(q["startDate"]), _doy(q["endDate"])
        calls.append({"band": q["band"], "year": y0, "window": (d0, d1)})
        assert y0 == y1
        body = dict(bodies[q["band"]])
        subset = []
        for s in body["subset"]:
            d = int(s["modis_date"][5:])
            if d0 <= d <= d1:
                cal = (date(y0, 1, 1).toordinal() + d - 1)
                subset.append({**s, "modis_date": f"A{y0}{d:03d}", "calendar_date": date.fromordinal(cal).isoformat()})
        return httpx.Response(200, json={**body, "subset": subset})

    return handler


def test_composite_chunks_respect_the_10_date_limit():
    assert modis.composite_chunks(list(modis.COMPOSITE_DOYS)) == [(1, 145), (161, 305), (321, 353)]
    for w in modis.composite_chunks(list(modis.COMPOSITE_DOYS)):
        assert modis.n_composites(w) <= modis.MAX_DATES_PER_REQUEST
    assert modis.shoulder_windows() == ((81, 113), (289, 305))
    assert modis.n_composites(modis.SEASON_DOY) == modis.MAX_DATES_PER_REQUEST


def test_request_with_too_many_dates_is_refused():
    with pytest.raises(ValueError):
        asyncio.run(modis._request_subset(None, 52.0, 70.0, 1, 1, 2024, modis.BAND_NDVI, (1, 177)))  # type: ignore[arg-type]


def test_modis_shoulder_requests_and_snow_cloud_separation(tmp_data, monkeypatch):
    calls: list[dict] = []
    _mock(monkeypatch, modis_handler(calls))
    src = modis.ModisShoulderSource()
    res = asyncio.run(src.fetch(parse_field(FIELD), date(2022, 1, 1), date(2024, 12, 31)))
    assert res.origin == "live" and res.data["season_doy"] == [[81, 113], [289, 305]]
    # два окна на год и слой, каждое ≤ 10 дат, ни одного запроса в сезон 129–273
    assert len(calls) == 3 * 2 * 2
    assert {c["window"] for c in calls} == {(81, 113), (289, 305)}
    assert all(modis.n_composites(c["window"]) <= modis.MAX_DATES_PER_REQUEST for c in calls)
    by_doy = {date.fromisoformat(r["date"]).timetuple().tm_yday: r for r in res.data["series"] if r["date"][:4] == "2023"}
    assert sorted(by_doy) == [81, 97, 113, 289, 305]
    assert res.data["n_field_pixels"] == 9
    snow, cloud, good = by_doy[81], by_doy[97], by_doy[113]
    assert snow["snow_fraction"] == pytest.approx(6 / 9, abs=1e-3) and snow["cloud_fraction"] == 0
    assert cloud["cloud_fraction"] == pytest.approx(6 / 9, abs=1e-3) and cloud["snow_fraction"] == 0
    assert snow["reliability_counts"]["2"] == 6 and cloud["reliability_counts"]["3"] == 6
    assert by_doy[305]["snow_fraction"] == 1.0 and by_doy[305]["ndvi"] is None
    assert good["valid_fraction"] == 1.0 and good["ndvi_q"][4] == pytest.approx(0.16)  # медиана 9 пикселей
    assert res.data["rasters"] == {}  # растры карты для межсезонья не хранятся
    # повторный запрос — из кэша, без сети
    calls.clear()
    again = asyncio.run(modis.ModisShoulderSource().fetch(parse_field(FIELD), date(2022, 1, 1), date(2024, 12, 31)))
    assert again.origin == "cache" and calls == []


def test_main_season_request_cache_key_is_unchanged(tmp_data, monkeypatch):
    """Окно сезона запрашивается как раньше (A{год}129–A{год}273), прежние ответы в кэше остаются в силе."""
    calls: list[dict] = []
    _mock(monkeypatch, modis_handler(calls))
    asyncio.run(modis._request_subset(httpx.AsyncClient(), 52.0, 70.0, 1, 1, 2019, modis.BAND_NDVI))
    assert calls[0]["window"] == modis.SEASON_DOY
    key_parts = {"lat": 52.0, "lon": 70.0, "km_ab": 1, "km_lr": 1, "year": 2019, "band": modis.BAND_NDVI}
    assert modis.cache.read(modis.REQUEST_CACHE, modis.cache.make_key(modis.REQUEST_CACHE, **key_parts)) is not None


def smap_handler(calls: list[str], temporal: list[str]):
    cmr = json.loads((FIX / "cmr_granules_2024.json").read_text())
    csv = (FIX / "smap_opendap_window.dap.csv").read_text()

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "cmr.earthdata.nasa.gov" in url:
            temporal.append(request.url.params["temporal"])
            year = request.url.params["temporal"][:4]
            return httpx.Response(200, json=cmr if year == "2024" else {"feed": {"entry": []}})
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, text=csv)

    return handler


def test_smap_season_months_quality_and_shared_granule_cache(tmp_data, monkeypatch):
    monkeypatch.setattr(get_settings(), "earthdata_token", "test-token")
    calls: list[str] = []
    temporal: list[str] = []
    _mock(monkeypatch, smap_handler(calls, temporal))
    f = parse_field(FIELD)
    res = asyncio.run(smap.SmapSeasonSource().fetch(f, date(2024, 1, 1), date(2024, 12, 31)))
    assert res.origin == "live" and res.data["months"] == list(smap.SEASON_MONTHS)
    assert "2024-04-01T00:00:00Z,2024-10-31T23:59:59Z" in temporal  # каталог спрашивается за апрель–октябрь
    days = [r["date"] for r in res.data["daily"]]
    assert days == ["2024-04-15", "2024-05-20", "2024-07-10", "2024-10-31"]  # мартовская гранула отброшена
    w = res.data["daily"][0]["window"]
    assert w[4] == pytest.approx(0.18)  # центр: вечер с флагом качества (бит 0) отброшен, остаётся утро
    assert w[5] == pytest.approx(0.26)  # утро с флагом отброшено, остаётся вечер
    assert w[6] == pytest.approx(0.27)  # утро −9999 (заполнитель), вечер 0,27
    assert w[0] == pytest.approx(0.21) and res.data["daily"][0]["sm"] == pytest.approx(0.18)
    # источник smap (апрель–май) берёт уже скачанные гранулы из кэша: OPeNDAP повторно не запрашивается
    calls.clear()
    pre = asyncio.run(smap.SmapSource().fetch(f, date(2024, 1, 1), date(2024, 12, 31)))
    assert pre.ok and [r["date"] for r in pre.data["daily"]] == ["2024-04-15", "2024-05-20"]
    assert pre.data["months"] == list(smap.PRESOWING_MONTHS)
    assert not any("opendap" in c for c in calls)


def test_smap_season_without_token_is_not_configured(tmp_data, monkeypatch):
    for k in ("earthdata_token", "earthdata_username", "earthdata_password"):
        monkeypatch.setattr(get_settings(), k, None)
    res = asyncio.run(smap.SmapSeasonSource().fetch(parse_field(FIELD), date(2024, 1, 1), date(2024, 12, 31)))
    assert res.origin == "unavailable" and res.warnings[0].code == "source_not_configured"
