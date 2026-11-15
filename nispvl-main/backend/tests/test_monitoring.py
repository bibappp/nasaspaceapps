"""Мониторинг, история сезонов, риски, пригодность культур и слои карты по сохранённому полю."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.data_sources.base import demo_field_record
from app.main import app

pytestmark = pytest.mark.skipif(demo_field_record() is None, reason="нет data/demo")
H = {"X-Requested-With": "agro"}


@pytest.fixture(scope="module")
def ctx(tmp_path_factory):
    s = get_settings()
    old = (s.db_path, s.offline)
    s.db_path = tmp_path_factory.mktemp("db") / "t.db"
    s.offline = True
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "m@example.org", "password": "password-123"}, headers=H)
        demo = demo_field_record()
        f = c.post("/api/fields", json={"name": "Демо", "region": "akmola", "geometry": demo["geometry"],
                                        "history": demo["history"]}, headers=H).json()
        yield c, f["id"]
    s.db_path, s.offline = old


def test_monitoring_monthly_climate_and_anomalies(ctx):
    c, fid = ctx
    m = c.get(f"/api/fields/{fid}/monitoring", params={"start": "2021-01", "end": "2021-12"}).json()
    months = m["climate"]["months"]
    assert [r["month"] for r in months] == [f"2021-{i:02d}" for i in range(1, 13)]
    for r in months:
        assert r["t_anomaly"] == pytest.approx(r["t_mean"] - r["t_normal"], abs=0.11)
        if r["precip_normal_mm"]:
            assert r["precip_pct_of_normal"] == pytest.approx(100 * r["precip_mm"] / r["precip_normal_mm"], abs=1)
    assert sum(r["precip_mm"] for r in months if r["month"][5:] in ("05", "06", "07", "08")) == pytest.approx(122.0, abs=0.6)
    assert m["climate"]["baseline"] == [1991, 2020]
    assert m["kind"]["climate"] == "reanalysis" and m["kind"]["ndvi"] == "observation"
    nd = m["ndvi"]["composites"]
    assert nd and all(x["date"].startswith("2021") for x in nd)
    for x in nd:
        if x["anomaly"] is not None:
            assert x["anomaly"] == pytest.approx(x["ndvi"] - x["median"], abs=0.002)
    assert all(d["date"][5:7] in ("04", "05") for d in m["soil_moisture"]["days"])
    assert m["sources"]["gpm"]["state"] == "not_available"


def test_monitoring_validates_range(ctx):
    c, fid = ctx
    assert c.get(f"/api/fields/{fid}/monitoring", params={"start": "2021"}).status_code == 422
    assert c.get(f"/api/fields/{fid}/monitoring", params={"start": "2022-01", "end": "2021-01"}).status_code == 422


def test_seasons_table_matches_drought_definition(ctx):
    c, fid = ctx
    s = c.get(f"/api/fields/{fid}/seasons").json()
    dry = [r["year"] for r in s["years"] if r["is_dry"] and r["year"] >= 2002]
    assert dry == [2008, 2010, 2017, 2021, 2022, 2023]
    r2021 = next(r for r in s["years"] if r["year"] == 2021)
    assert r2021["precip_mm"] == 122.0 and r2021["ndvi_max"] is not None and r2021["smap_spring"] is not None
    assert s["ndvi_curves"]["2021"] and s["ndvi_climatology"]
    assert s["caveat"] == "ndvi_not_yield"


def test_risk_items_are_typed_and_levelled(ctx):
    c, fid = ctx
    r = c.get(f"/api/fields/{fid}/risk").json()
    ids = {i["id"] for i in r["items"]}
    assert ids == {"precip_season", "temperature_season", "heat_days", "vegetation", "soil_moisture",
                   "drought_frequency", "model_drought_exposure"}
    kinds = {i["id"]: i["kind"] for i in r["items"]}
    assert kinds["vegetation"] == "observation" and kinds["model_drought_exposure"] == "model"
    assert kinds["precip_season"] == "reanalysis" and kinds["drought_frequency"] == "statistic"
    order = {"unknown": -1, "low": 0, "moderate": 1, "high": 2}
    assert r["overall"] == max((i["level"] for i in r["items"]), key=lambda x: order[x])
    freq = next(i for i in r["items"] if i["id"] == "drought_frequency")
    assert freq["value"] == 0.24 and freq["level"] == "moderate"  # 0,2 ≤ 0,24 < 0,3
    assert all(t["status"] in ("verified", "assumption") for t in r["thresholds"].values())


def test_suitability_flags_follow_rules(ctx):
    c, fid = ctx
    s = c.get(f"/api/fields/{fid}/suitability").json()
    assert s["scope"] == "general_model_based"
    crops = {x["crop"]: x for x in s["crops"]}
    assert "fallow" not in crops and len(crops) == 7
    assert "monoculture" in crops["wheat"]["flags"]  # история: пшеница 5 лет подряд
    for x in crops.values():
        n = len(x["flags"])
        assert x["category"] == ("favourable" if n == 0 else "conditional" if n == 1 else "limited")
    assert s["context"]["gdd5_may_sep_mean"] > 1000


def test_field_layers_with_summary_and_ndvi_anomaly(ctx):
    c, fid = ctx
    for kind in ("ndvi", "ndvi_anomaly", "soil_moisture", "precip"):
        r = c.get(f"/api/fields/{fid}/layers/{kind}")
        assert r.status_code == 200, kind
        meta = r.json()["meta"]
        assert meta["summary"]["cells_in_field"] >= 1
        assert meta["summary"]["coarser_than_field"] is (kind in ("soil_moisture", "precip"))
    an = c.get(f"/api/fields/{fid}/layers/ndvi_anomaly", params={"date": "2021-07-12"}).json()
    assert an["meta"]["date"].startswith("2021") and len(an["meta"]["reference_dates"]) >= 2
    assert c.get(f"/api/fields/{fid}/layers/lava").status_code == 404
