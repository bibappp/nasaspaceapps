"""Сбор данных для PDF- и XLSX-отчётов: одни и те же числа в обоих форматах."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date

from ..data_sources.registry import SOURCES
from ..geometry import parse_field
from ..model.rules import get_rules
from ..schemas import CompareRequest
from . import monitoring as mon
from .analysis import MODIS_START
from .comparison import run_compare


@dataclass
class ReportData:
    comparison: dict
    analysis: dict
    seasons: dict
    risk: dict
    climate_monthly: dict
    ndvi: dict
    smap: dict
    field_info: dict
    modis: dict | None = None
    generated: date = dc_field(default_factory=date.today)


async def gather(req: CompareRequest, field_info: dict | None = None) -> ReportData:
    rules = get_rules()
    comparison, analysis = await run_compare(req)
    analysis_obj, df, modis, smap, power = await mon.load(req.geometry, req.region, rules)
    seasons = mon.seasons_from(rules, analysis_obj, df, modis, smap)
    risk = await mon.risk(req.geometry, req.region)
    hot_c = float(rules.model["risk"]["hot_day_threshold_c"].value)
    end = df.index.max().strftime("%Y-%m")
    climate = mon.climate_timeseries(df, "2000-01", end, hot_c)
    ndvi = mon.ndvi_timeseries(modis, "2000-01", end, float(rules.model["ndvi_trend"]["min_valid_fraction"]))
    smap_ts = mon.smap_timeseries(smap, "2015-01", end)
    info = {"name": "", "farm_name": "", "notes": "", "soil": {}, "history_is_scenario": False, **(field_info or {})}
    if not modis:
        res = SOURCES["modis"].read_cached(parse_field(req.geometry), MODIS_START, date.today())
        modis = res.data if res else None
    return ReportData(comparison=comparison, analysis=analysis.response, seasons=seasons, risk=risk,
                      climate_monthly=climate, ndvi=ndvi, smap=smap_ts, field_info=info, modis=modis)
