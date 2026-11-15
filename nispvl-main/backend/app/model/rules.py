"""Загрузка и проверка YAML-правил.

Каждое числовое правило — это ``Param``: значение, единица, источник (название + ссылка)
и статус ``verified`` / ``assumption``. Загрузчик отказывается работать с правилом
без источника или статуса: так нельзя случайно добавить «голую» цифру.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
STATUSES = {"verified", "assumption"}
#: Класс обоснованности значения (аудит модели, docs/MODEL_AUDIT.md):
#:   literature        — значение (или диапазон, в который оно входит) есть в научном/официальном источнике;
#:   agronomist_review — есть косвенная опора (другой регион, аналог, один год, расчёт), нужна проверка агрономом;
#:   preliminary       — предварительное допущение без источника или параметр конструкции модели;
#:   definition        — определение, тривиальное значение или величина, рассчитанная из данных.
EVIDENCE = {"literature", "agronomist_review", "preliminary", "definition"}
GROUPS = {"cereal", "legume", "oilseed", "fallow"}
#: Обязательные правила erosion.yaml («Часы голой почвы») по группам.
EROSION_REQUIRED = {
    "bare_soil": ("ndvi_max", "min_field_fraction"),
    "erosive_wind": ("speed_ms",),
    "dry_topsoil": ("smap_wilting_point_factor", "smap_fallback_m3m3", "gwettop_min_pairs", "gwettop_fallback"),
    "snow": ("modis_reliability_snow", "modis_min_field_fraction", "power_frsno_min", "power_snodp_min_cm",
             "month_snow_day_fraction"),
    "ndvi_daily": ("min_valid_fraction", "max_interp_gap_days"),
    "month": ("min_known_fraction",),
    "climatology": ("min_years",),
    "headline": ("top_n",),
    "cover_crop": ("min_median_exposure", "frost_t2m_min_c", "min_frost_free_days", "min_years_medium_uncertainty",
                   "min_years_low_uncertainty", "max_partial_share_low_uncertainty"),
    "planner": ("canopy_start", "canopy_end"),
}
#: Границы периода покрова культуры в планировщике (erosion.planner): какой день окна сева / уборки.
CANOPY_START = ("sowing_start", "sowing_mid", "sowing_end")
CANOPY_END = ("harvest_start", "harvest_mid", "harvest_end")
#: Окна сева и уборки культуры (crops.yaml): {start, end} в формате «ММ-ДД».
CROP_WINDOWS = ("sowing_window", "harvest_window")
#: Параметр POWER для ветра должен соответствовать высоте, к которой относится порог.
WIND_PARAMETERS = {2: ("WS2M", "WS2M_MAX"), 10: ("WS10M", "WS10M_MAX")}


class RulesError(ValueError):
    pass


@dataclass(frozen=True)
class Param:
    path: str
    value: Any
    unit: str
    source_id: str
    source_name: str
    source_url: str
    status: str
    note: str = ""
    evidence: str = ""
    #: диапазон из литературы ``(нижняя, верхняя)``, если он указан в YAML (``range: [lo, hi]``)
    range: tuple[float, float] | None = None

    @property
    def is_assumption(self) -> bool:
        return self.status == "assumption"

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "value": self.value,
            "unit": self.unit,
            "source": {"id": self.source_id, "name": self.source_name, "url": self.source_url},
            "status": self.status,
            "evidence": self.evidence,
            "note": self.note,
            "range": list(self.range) if self.range else None,
        }

    def ref(self) -> dict:
        """Короткая ссылка на правило для подсказок интерфейса."""
        return {
            "path": self.path,
            "value": self.value,
            "unit": self.unit,
            "status": self.status,
            "evidence": self.evidence,
            "source": self.source_name,
            "url": self.source_url,
        }


def _is_param(node: Any) -> bool:
    return isinstance(node, dict) and "value" in node and ("status" in node or "source" in node)


def _convert(node: Any, path: str, sources: dict[str, dict]) -> Any:
    if _is_param(node):
        missing = {"value", "unit", "source", "status"} - set(node)
        if missing:
            raise RulesError(f"{path}: missing fields {sorted(missing)}")
        if node["status"] not in STATUSES:
            raise RulesError(f"{path}: status must be one of {sorted(STATUSES)}")
        if node.get("evidence") not in EVIDENCE:
            raise RulesError(f"{path}: evidence must be one of {sorted(EVIDENCE)}")
        if node["status"] == "verified" and node["evidence"] not in ("literature", "definition"):
            raise RulesError(f"{path}: a verified value must have evidence 'literature' or 'definition'")
        src = sources.get(node["source"])
        if src is None:
            raise RulesError(f"{path}: unknown source id '{node['source']}'")
        rng = _range(node, path)
        return Param(
            path=path,
            value=node["value"],
            unit=str(node["unit"]),
            source_id=node["source"],
            source_name=src["name"],
            source_url=src["url"],
            status=node["status"],
            note=str(node.get("note", "")),
            evidence=str(node.get("evidence", "")),
            range=rng,
        )
    if isinstance(node, dict):
        return {k: _convert(v, f"{path}.{k}" if path else str(k), sources) for k, v in node.items()}
    if isinstance(node, list):
        out = []
        for i, v in enumerate(node):
            key = v.get("id", i) if isinstance(v, dict) else i
            out.append(_convert(v, f"{path}.{key}", sources))
        return out
    return node


def _range(node: dict, path: str) -> tuple[float, float] | None:
    """Проверить необязательное поле ``range: [lo, hi]``: числа, lo ≤ hi, значение внутри диапазона."""
    if "range" not in node:
        return None
    rng = node["range"]
    if not (isinstance(rng, list) and len(rng) == 2 and all(_is_number(x) for x in rng)):
        raise RulesError(f"{path}: range must be a list of two numbers [lo, hi]")
    lo, hi = float(rng[0]), float(rng[1])
    if lo > hi:
        raise RulesError(f"{path}: range lower bound {lo} exceeds upper bound {hi}")
    if not _is_number(node["value"]) or not lo <= node["value"] <= hi:
        raise RulesError(f"{path}: value {node['value']} is outside range [{lo}, {hi}]")
    return lo, hi


def parse_mmdd(x: Any) -> date | None:
    """«ММ-ДД» → дата в невисокосном опорном году 2001 (как даты заморозков) или None."""
    try:
        m, d = str(x).split("-")
        return date(2001, int(m), int(d)) if len(m) == len(d) == 2 else None
    except ValueError:
        return None


def parse_window(p: Any) -> tuple[date, date] | None:
    """Правило-окно ``{start: "ММ-ДД", end: "ММ-ДД"}`` → (начало, конец) в опорном году или None."""
    val = p.value if isinstance(p, Param) else None
    if not isinstance(val, dict) or set(val) != {"start", "end"}:
        return None
    a, b = parse_mmdd(val["start"]), parse_mmdd(val["end"])
    return (a, b) if a is not None and b is not None and a <= b else None


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def _walk(node: Any) -> Iterator[Param]:
    if isinstance(node, Param):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


@dataclass(frozen=True)
class Rules:
    sources: dict[str, dict]
    crops: dict[str, dict]
    predecessors: list[dict]
    regions: dict[str, dict]
    model: dict[str, Any]
    #: пороги «Часов голой почвы» (erosion.yaml)
    erosion: dict[str, Any] = field(default_factory=dict)

    # ---- культуры --------------------------------------------------------
    def crop(self, crop_id: str) -> dict:
        try:
            return self.crops[crop_id]
        except KeyError as exc:
            raise RulesError(f"unknown crop '{crop_id}'") from exc

    def group(self, crop_id: str) -> str:
        return self.crop(crop_id)["group"]

    def crop_name(self, crop_id: str, lang: str = "ru", short: bool = False) -> str:
        c = self.crop(crop_id)
        return c["short" if short else "name"].get(lang) or c["name"]["ru"]

    def region(self, region_id: str) -> dict:
        try:
            return self.regions[region_id]
        except KeyError as exc:
            raise RulesError(f"unknown region '{region_id}'") from exc

    # ---- предшественники -------------------------------------------------
    def predecessor_effect(self, predecessor: str | None, crop: str) -> tuple[float, dict | None]:
        """(эффект в %, сработавшее правило). Самое конкретное правило побеждает."""
        if predecessor is None or self.group(crop) == "fallow":
            return 0.0, None
        pg, cg = self.group(predecessor), self.group(crop)

        def match(pattern: str, crop_id: str, group: str) -> int:
            if pattern == crop_id:
                return 2
            if pattern == f"group:{group}":
                return 1
            return 0 if pattern == "any" else -1

        best: tuple[int, dict] | None = None
        for rule in self.predecessors:
            mp, mc = match(rule["predecessor"], predecessor, pg), match(rule["crop"], crop, cg)
            if mp < 0 or mc < 0:
                continue
            if rule.get("same") and predecessor != crop:
                continue
            score = mp * 4 + mc * 2 + (1 if rule.get("same") else 0)
            if best is None or score > best[0]:
                best = (score, rule)
        if best is None:
            return 0.0, None
        return float(best[1]["yield_effect_pct"].value), best[1]

    # ---- сервис -----------------------------------------------------------
    def all_params(self) -> list[Param]:
        return [*_walk(self.crops), *_walk(self.predecessors), *_walk(self.regions), *_walk(self.model),
                *_walk(self.erosion)]

    def todo_sources(self) -> list[dict]:
        return [{"id": k, **v} for k, v in self.sources.items() if str(v.get("url", "")).startswith("TODO")]


def load_rules(directory: Path | None = None) -> Rules:
    d = directory or RULES_DIR

    def read(name: str) -> Any:
        return yaml.safe_load((d / name).read_text(encoding="utf-8"))

    sources = read("sources.yaml")
    for sid, src in sources.items():
        if not src.get("name") or not src.get("url"):
            raise RulesError(f"sources.{sid}: name and url are required (use 'TODO: ссылка' if unknown)")
    crops = _convert(read("crops.yaml")["crops"], "crops", sources)
    preds = _convert(read("predecessors.yaml")["effects"], "predecessors", sources)
    regions = _convert(read("regions.yaml")["regions"], "regions", sources)
    model = _convert(read("model.yaml"), "model", sources)
    erosion = _convert(read("erosion.yaml"), "erosion", sources)
    _validate_erosion(erosion)
    if erosion["cover_crop"].get("no_window_advice_source") not in sources:
        raise RulesError("erosion.cover_crop.no_window_advice_source: must be a source id from sources.yaml")
    missing_harvest = set(regions) - set(erosion["cover_crop"]["harvest_end"])
    if missing_harvest:
        raise RulesError(f"erosion.cover_crop.harvest_end: no date for regions {sorted(missing_harvest)}")

    required = (
        "base_yield_t_ha",
        "price_kzt_t",
        "cost_kzt_ha",
        "water_need_mm",
        "ky",
        "nitrogen_balance_kg_ha",
        "humus_balance_t_ha",
    )
    for cid, crop in crops.items():
        if crop.get("group") not in GROUPS:
            raise RulesError(f"crops.{cid}: group must be one of {sorted(GROUPS)}")
        for key in required:
            if not isinstance(crop.get(key), Param):
                raise RulesError(f"crops.{cid}.{key}: must be a rule with value/unit/source/status")
    _validate_crop_windows(crops, erosion)
    rules = Rules(sources=sources, crops=crops, predecessors=preds, regions=regions, model=model, erosion=erosion)
    for rule in preds:
        for side in ("predecessor", "crop"):
            pat = rule[side]
            if pat != "any" and not pat.startswith("group:") and pat not in crops:
                raise RulesError(f"predecessors.{rule.get('id')}: unknown crop '{pat}'")
    for variant in model["default_variants"]:
        for cid in variant["crops"]:
            rules.crop(cid)
    for pid, pr in model["priorities"].items():
        total = sum(pr["weights"].value.values())
        if abs(total - 1.0) > 1e-6:
            raise RulesError(f"model.priorities.{pid}: weights must sum to 1 (got {total})")
    return rules


def _validate_erosion(e: Any) -> None:
    """erosion.yaml: все группы и правила на месте, значения в физически осмысленных пределах."""
    if not isinstance(e, dict):
        raise RulesError("erosion: must be a mapping")
    for group, keys in EROSION_REQUIRED.items():
        if not isinstance(e.get(group), dict):
            raise RulesError(f"erosion.{group}: group is missing")
        for key in keys:
            if not isinstance(e[group].get(key), Param):
                raise RulesError(f"erosion.{group}.{key}: must be a rule with value/unit/source/status")

    def num(group: str, key: str, lo: float, hi: float, *, open_lo: bool = False) -> float:
        val = e[group][key].value
        ok = _is_number(val) and (lo < val if open_lo else lo <= val) and val <= hi
        if not ok:
            raise RulesError(f"erosion.{group}.{key}: value {val!r} must be in {'(' if open_lo else '['}{lo}, {hi}]")
        return float(val)

    bare, wind, dry, snow = e["bare_soil"], e["erosive_wind"], e["dry_topsoil"], e["snow"]
    ndvi = num("bare_soil", "ndvi_max", -1.0, 1.0)
    num("bare_soil", "min_field_fraction", 0.0, 1.0, open_lo=True)
    sens = bare.get("sensitivity_values", [])
    if not (isinstance(sens, list) and sens and all(_is_number(x) and -1 <= x <= 1 for x in sens)):
        raise RulesError("erosion.bare_soil.sensitivity_values: must be a non-empty list of NDVI values")
    if ndvi not in sens:
        raise RulesError("erosion.bare_soil.sensitivity_values: must include the value of ndvi_max")

    height = wind.get("reference_height_m")
    if height not in WIND_PARAMETERS:
        raise RulesError(f"erosion.erosive_wind.reference_height_m: must be one of {sorted(WIND_PARAMETERS)}")
    if wind.get("power_parameter") not in WIND_PARAMETERS[height]:
        raise RulesError(f"erosion.erosive_wind.power_parameter: for {height} m use one of {WIND_PARAMETERS[height]}")
    num("erosive_wind", "speed_ms", 0.0, 30.0, open_lo=True)
    ctx = wind.get("context_range_10m_ms")
    if ctx is not None and not (isinstance(ctx, list) and len(ctx) == 2 and all(_is_number(x) for x in ctx) and ctx[0] <= ctx[1]):
        raise RulesError("erosion.erosive_wind.context_range_10m_ms: must be [lo, hi]")

    num("dry_topsoil", "smap_wilting_point_factor", 0.0, 2.0, open_lo=True)
    num("dry_topsoil", "smap_fallback_m3m3", 0.0, 0.6, open_lo=True)
    num("dry_topsoil", "gwettop_fallback", 0.0, 1.0, open_lo=True)
    if num("dry_topsoil", "gwettop_min_pairs", 1, 10_000) != int(dry["gwettop_min_pairs"].value):
        raise RulesError("erosion.dry_topsoil.gwettop_min_pairs: must be an integer")
    if dry.get("gwettop_method") != "cdf_match":
        raise RulesError("erosion.dry_topsoil.gwettop_method: only 'cdf_match' is supported")
    if dry.get("gwettop_month_quality") not in ("ok", "partial"):
        raise RulesError("erosion.dry_topsoil.gwettop_month_quality: must be 'ok' or 'partial'")

    if snow["modis_reliability_snow"].value not in (0, 1, 2, 3):
        raise RulesError("erosion.snow.modis_reliability_snow: must be a MOD13Q1 pixel_reliability code 0–3")
    num("snow", "modis_min_field_fraction", 0.0, 1.0, open_lo=True)
    num("snow", "power_frsno_min", 0.0, 1.0, open_lo=True)
    num("snow", "power_snodp_min_cm", 0.0, 100.0)
    num("snow", "month_snow_day_fraction", 0.0, 1.0, open_lo=True)

    num("ndvi_daily", "min_valid_fraction", 0.0, 1.0, open_lo=True)
    num("ndvi_daily", "max_interp_gap_days", 16, 366)
    num("month", "min_known_fraction", 0.0, 1.0, open_lo=True)
    for group, key in (("climatology", "min_years"), ("headline", "top_n"), ("cover_crop", "min_frost_free_days"),
                       ("cover_crop", "min_years_medium_uncertainty"), ("cover_crop", "min_years_low_uncertainty")):
        if num(group, key, 1, 366) != int(e[group][key].value):
            raise RulesError(f"erosion.{group}.{key}: must be an integer")
    if e["cover_crop"]["min_years_medium_uncertainty"].value > e["cover_crop"]["min_years_low_uncertainty"].value:
        raise RulesError("erosion.cover_crop: min_years_medium_uncertainty must not exceed min_years_low_uncertainty")
    num("cover_crop", "min_median_exposure", 0.0, 1.0)
    num("cover_crop", "frost_t2m_min_c", -10.0, 5.0)
    num("cover_crop", "max_partial_share_low_uncertainty", 0.0, 1.0)
    if e["cover_crop"].get("season_split_month") not in range(1, 12):
        raise RulesError("erosion.cover_crop.season_split_month: must be a month number 1–11")
    harvest = e["cover_crop"].get("harvest_end")
    if not isinstance(harvest, dict) or not harvest:
        raise RulesError("erosion.cover_crop.harvest_end: must map region ids to rules with an 'MM-DD' value")
    for rid, p in harvest.items():
        d = parse_mmdd(p.value) if isinstance(p, Param) else None
        if d is None:
            raise RulesError(f"erosion.cover_crop.harvest_end.{rid}: value must be a valid 'MM-DD' date")
        if d.month <= e["cover_crop"]["season_split_month"]:
            raise RulesError(f"erosion.cover_crop.harvest_end.{rid}: harvest end must fall after season_split_month")

    pl = e["planner"]
    for key, allowed in (("canopy_start", CANOPY_START), ("canopy_end", CANOPY_END)):
        if pl[key].value not in allowed:
            raise RulesError(f"erosion.planner.{key}: must be one of {list(allowed)}")
        sens = pl.get(f"sensitivity_{key}", [])
        if not (isinstance(sens, list) and sens and set(sens) <= set(allowed) and pl[key].value in sens):
            raise RulesError(f"erosion.planner.sensitivity_{key}: must list values of {list(allowed)} including the current one")

    for cid, ref in (e.get("contract_thresholds") or {}).items():
        node: Any = e
        for part in str(ref).split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if not isinstance(node, Param):
            raise RulesError(f"erosion.contract_thresholds.{cid}: '{ref}' is not a rule in erosion.yaml")
    if set(e.get("contract_thresholds") or {}) != {"ndvi_bare", "erosive_wind_ms", "dry_topsoil"}:
        raise RulesError("erosion.contract_thresholds: must map ndvi_bare, erosive_wind_ms and dry_topsoil")


def _validate_crop_windows(crops: dict, e: dict) -> None:
    """Окна сева и уборки (планировщик): у каждой культуры, кроме пара; сев раньше уборки; уборка зерновых
    кончается не позже erosion.cover_crop.harvest_end каждой области — иначе окно покровной культуры в «Часах»
    начиналось бы, пока зерновые ещё стоят."""
    for cid, crop in crops.items():
        if crop["group"] == "fallow":
            flag = crop.get("bare_whole_season")
            if not (isinstance(flag, Param) and isinstance(flag.value, bool)):
                raise RulesError(f"crops.{cid}.bare_whole_season: fallow must have a true/false rule")
            for key in CROP_WINDOWS:
                if key in crop:
                    raise RulesError(f"crops.{cid}.{key}: fallow has no {key}; use bare_whole_season")
            continue
        windows = {}
        for key in CROP_WINDOWS:
            w = parse_window(crop.get(key))
            if w is None:
                raise RulesError(f"crops.{cid}.{key}: must be a rule with value {{start: 'MM-DD', end: 'MM-DD'}}, start ≤ end")
            windows[key] = w
        if windows["sowing_window"][1] >= windows["harvest_window"][0]:
            raise RulesError(f"crops.{cid}: sowing_window must end before harvest_window starts")
        if crop["group"] == "cereal":
            for rid, p in e["cover_crop"]["harvest_end"].items():
                if windows["harvest_window"][1] > parse_mmdd(p.value):
                    raise RulesError(f"crops.{cid}.harvest_window: cereal harvest must end no later than "
                                     f"erosion.cover_crop.harvest_end.{rid} ({p.value})")


@lru_cache
def get_rules() -> Rules:
    return load_rules()
