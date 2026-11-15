"""Модель сравнения севооборотов: простая, детерминированная, на правилах из YAML.

Для каждого года варианта:

    урожайность = база культуры x индекс области
                  x (1 + эффект предшественника) x (1 + штраф за монокультуру)
                  x коэффициент влаги поля

    коэффициент влаги = RY(W поля) / RY(W области),   не больше moisture_coef_max
    RY(W) = 1 − Ky x (1 − min(1, W / потребность культуры))        (FAO-33)
    W = осадки за май–август + запас продуктивной влаги к посеву

    доход = урожайность x цена − затраты

Никаких случайных величин и машинного обучения: одни и те же входные данные
всегда дают один и тот же результат.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from .rules import Param, Rules


@dataclass(frozen=True)
class FieldConditions:
    """Условия увлажнения поля, полученные из данных (см. services/analysis.py)."""

    region: str
    area_ha: float
    p_season_normal: float      # осадки май–август в обычный год, мм (медиана)
    stock_normal: float         # запас влаги к посеву в обычный год, мм
    p_season_dry: float         # то же для засушливого года стресс-теста
    stock_dry: float
    dry_year: int
    p_season_ref: float         # опорные осадки области, мм
    stock_ref: float            # обычный запас влаги области, мм
    awc_mm: float | None = None  # влагоёмкость метрового слоя почвы поля, мм
    moisture_basis: str = "power"  # чем уточнён запас влаги: "smap" или "power"

    def as_dict(self) -> dict:
        return asdict(self)


def relative_yield(rules: Rules, crop_id: str, water_mm: float) -> float:
    """Относительный урожай по FAO-33 при доступной влаге ``water_mm``."""
    crop = rules.crop(crop_id)
    need = float(crop["water_need_mm"].value)
    if need <= 0:
        return 1.0
    ratio = min(1.0, max(0.0, water_mm) / need)
    ry = 1.0 - float(crop["ky"].value) * (1.0 - ratio)
    return max(float(rules.model["water"]["relative_yield_min"].value), ry)


def moisture_coefficient(rules: Rules, crop_id: str, water_mm: float, reference_mm: float) -> float:
    if rules.group(crop_id) == "fallow":
        return 1.0
    coef = relative_yield(rules, crop_id, water_mm) / relative_yield(rules, crop_id, reference_mm)
    return min(float(rules.model["water"]["moisture_coef_max"].value), coef)


def default_start_year(today: date | None = None) -> int:
    """Первый год плана: ближайший сезон, посев которого ещё впереди."""
    today = today or date.today()
    return today.year if today.month < 6 else today.year + 1


def _cereal_run(rules: Rules, sequence: list[str]) -> int:
    """Сколько лет подряд (включая последний) идёт одна и та же зерновая культура."""
    if not sequence or rules.group(sequence[-1]) != "cereal":
        return 0
    run = 0
    for crop in reversed(sequence):
        if crop != sequence[-1]:
            break
        run += 1
    return run


def simulate(
    rules: Rules,
    cond: FieldConditions,
    crops: list[str],
    history: list[str],
    horizon: int,
    start_year: int | None = None,
) -> dict:
    """Прогноз по годам для одного варианта севооборота."""
    if not crops:
        raise ValueError("rotation must contain at least one crop")
    for c in [*crops, *history]:
        rules.crop(c)
    model = rules.model
    region = rules.region(cond.region)
    yield_index: Param = region["yield_index"]
    fallow_gain: Param = model["water"]["fallow_stock_gain_pct"]
    mono_cfg = model["monoculture"]
    soil_cfg = model["soil_index"]
    start_year = start_year or default_start_year()

    w_ref = cond.p_season_ref + cond.stock_ref
    sequence = list(history)
    soil_index = float(soil_cfg["start"])
    years: list[dict] = []
    used: dict[str, Param] = {}

    def use(p: Param) -> Param:
        used[p.path] = p
        return p

    use(yield_index)
    use(region["presowing_stock_norm_mm"])
    use(region["reference_season_precip_mm"])
    use(model["water"]["moisture_coef_max"])
    use(soil_cfg["nitrogen_kg_per_point"])
    use(soil_cfg["humus_t_per_point"])

    for i in range(horizon):
        crop_id = crops[i % len(crops)]
        crop = rules.crop(crop_id)
        prev = sequence[-1] if sequence else None
        is_fallow = crop["group"] == "fallow"

        # --- влага ---------------------------------------------------------
        def stock_for(base_stock: float) -> float:
            if prev is not None and rules.group(prev) == "fallow":
                use(fallow_gain)
                gained = base_stock * (1 + float(fallow_gain.value) / 100)
                return min(gained, cond.awc_mm) if cond.awc_mm else gained
            return base_stock

        stock, stock_dry = stock_for(cond.stock_normal), stock_for(cond.stock_dry)
        water, water_dry = cond.p_season_normal + stock, cond.p_season_dry + stock_dry
        need = float(use(crop["water_need_mm"]).value)
        use(crop["ky"])
        coef = moisture_coefficient(rules, crop_id, water, w_ref)
        coef_dry = moisture_coefficient(rules, crop_id, water_dry, w_ref)

        # --- предшественник и монокультура ---------------------------------
        pred_pct, pred_rule = rules.predecessor_effect(prev, crop_id)
        if pred_rule is not None:
            use(pred_rule["yield_effect_pct"])
        run = _cereal_run(rules, [*sequence, crop_id])
        mono = run >= int(mono_cfg["min_run_years"])
        mono_pct = float(use(mono_cfg["yield_penalty_pct"]).value) if mono else 0.0

        # --- урожайность и доход ------------------------------------------
        base = float(use(crop["base_yield_t_ha"]).value) * float(yield_index.value)
        agronomic = base * (1 + pred_pct / 100) * (1 + mono_pct / 100)
        yld, yld_dry = agronomic * coef, agronomic * coef_dry
        price, cost = float(use(crop["price_kzt_t"]).value), float(use(crop["cost_kzt_ha"]).value)
        income, income_dry = yld * price - cost, yld_dry * price - cost

        # --- почва ----------------------------------------------------------
        n_bal = float(use(crop["nitrogen_balance_kg_ha"]).value)
        h_bal = float(use(crop["humus_balance_t_ha"]).value)
        soil_delta = n_bal / float(soil_cfg["nitrogen_kg_per_point"].value) + h_bal / float(
            soil_cfg["humus_t_per_point"].value
        )
        if mono:
            soil_delta += float(use(mono_cfg["soil_penalty_points"]).value)
        soil_index += soil_delta

        years.append(
            {
                "index": i + 1,
                "year": start_year + i,
                "crop": crop_id,
                "group": crop["group"],
                "predecessor": prev,
                "base_yield_t_ha": round(base, 3),
                "predecessor_effect_pct": pred_pct,
                "predecessor_rule": pred_rule["id"] if pred_rule else None,
                "monoculture": mono,
                "monoculture_run": run,
                "monoculture_penalty_pct": mono_pct,
                "after_fallow": prev is not None and rules.group(prev) == "fallow",
                "stock_mm": round(stock, 1),
                "water_available_mm": round(water, 1),
                "water_need_mm": need,
                "water_deficit_mm": 0.0 if is_fallow else round(max(0.0, need - water), 1),
                "moisture_coef": round(coef, 3),
                "moisture_coef_dry": round(coef_dry, 3),
                "yield_t_ha": round(yld, 3),
                "yield_dry_t_ha": round(yld_dry, 3),
                "yield_loss_dry_pct": 0.0 if yld <= 0 else round((1 - yld_dry / yld) * 100, 1),
                "price_kzt_t": price,
                "revenue_kzt_ha": round(yld * price),
                "revenue_dry_kzt_ha": round(yld_dry * price),
                "cost_kzt_ha": cost,
                "income_kzt_ha": round(income),
                "income_dry_kzt_ha": round(income_dry),
                "nitrogen_kg_ha": n_bal,
                "humus_t_ha": h_bal,
                "soil_delta": round(soil_delta, 2),
                "soil_index": round(soil_index, 2),
            }
        )
        sequence.append(crop_id)

    n = len(years)
    revenue_total = sum(y["revenue_kzt_ha"] for y in years)
    losses = [y["income_kzt_ha"] - y["income_dry_kzt_ha"] for y in years]
    income_total = sum(y["income_kzt_ha"] for y in years)
    totals = {
        "income_kzt_ha": income_total,
        "income_per_year_kzt_ha": round(income_total / n),
        "income_field_kzt": round(income_total * cond.area_ha),
        "revenue_kzt_ha": revenue_total,
        "nitrogen_kg_ha": round(sum(y["nitrogen_kg_ha"] for y in years), 1),
        "humus_t_ha": round(sum(y["humus_t_ha"] for y in years), 2),
        "soil_index_end": years[-1]["soil_index"],
        "soil_index_change": round(years[-1]["soil_index"] - float(soil_cfg["start"]), 2),
        "water_deficit_mean_mm": round(sum(y["water_deficit_mm"] for y in years) / n, 1),
        "monoculture_years": sum(1 for y in years if y["monoculture"]),
        # доля выручки, которая теряется, если год оказывается засушливым (в среднем по годам плана)
        "drought_loss_pct": round(100 * sum(losses) / revenue_total, 1) if revenue_total > 0 else 0.0,
        "drought_loss_mean_kzt_ha": round(sum(losses) / n),
    }
    worst = max(range(n), key=lambda k: losses[k])
    stress = {
        "per_year": [
            {
                "index": y["index"],
                "year": y["year"],
                "crop": y["crop"],
                "income_normal_kzt_ha": y["income_kzt_ha"],
                "income_dry_kzt_ha": y["income_dry_kzt_ha"],
                "loss_kzt_ha": losses[k],
                "total_if_dry_kzt_ha": income_total - losses[k],
            }
            for k, y in enumerate(years)
        ],
        "total_normal_kzt_ha": income_total,
        "worst_year_index": worst + 1,
        "worst_loss_kzt_ha": losses[worst],
        "mean_loss_kzt_ha": totals["drought_loss_mean_kzt_ha"],
        "loss_pct_of_revenue": totals["drought_loss_pct"],
    }
    return {"crops": [y["crop"] for y in years], "years": years, "totals": totals, "stress": stress, "_used": used}


# ---------------------------------------------------------------- оценки 1–5
SCORE_KEYS = ("soil", "water", "income", "risk")

#: какая метрика стоит за каждой оценкой и в какую сторону «лучше»
METRICS = {
    "soil": ("soil_index_end", +1, "пункты"),
    "water": ("water_deficit_mean_mm", -1, "мм"),
    "income": ("income_kzt_ha", +1, "тенге/га"),
    "risk": ("drought_loss_pct", -1, "%"),
}

#: какие правила относятся к какой оценке (для подсказок с источниками)
_SCORE_PARAM_KEYS = {
    "soil": ("nitrogen_balance_kg_ha", "humus_balance_t_ha", "soil_index", "monoculture.soil_penalty_points"),
    "water": ("water_need_mm", "presowing_stock_norm_mm", "fallow_stock_gain_pct"),
    "income": (
        "base_yield_t_ha",
        "yield_index",
        "price_kzt_t",
        "cost_kzt_ha",
        "yield_effect_pct",
        "yield_penalty_pct",
        "water_need_mm",
        ".ky",
        "moisture_coef_max",
        "reference_season_precip_mm",
        "presowing_stock_norm_mm",
        "fallow_stock_gain_pct",
    ),
    "risk": ("water_need_mm", ".ky", "price_kzt_t", "base_yield_t_ha", "fallow_stock_gain_pct"),
}


def _score_params(used: dict[str, Param], key: str) -> list[dict]:
    refs = [p.ref() for path, p in sorted(used.items()) if any(k in path for k in _SCORE_PARAM_KEYS[key])]
    return refs


def _normalize(value: float, lo: float, hi: float, direction: int, neutral: float) -> float:
    if hi - lo < 1e-9:
        return neutral
    share = (value - lo) / (hi - lo)
    if direction < 0:
        share = 1 - share
    return round(1 + 4 * share, 1)


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    if set(weights) != set(SCORE_KEYS):
        raise ValueError(f"weights must have keys {list(SCORE_KEYS)}")
    if any(w < 0 for w in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("weights must be non-negative and not all zero")
    total = sum(weights.values())
    return {k: round(weights[k] / total, 4) for k in SCORE_KEYS}


#: Уровни уверенности по доле параметров с опорой на источник или определение (конструкция модели, docs/MODEL_AUDIT.md)
CONFIDENCE_LEVELS = ((0.6, "high"), (0.3, "medium"), (0.0, "low"))


def parameter_confidence(params: list[dict]) -> dict:
    """Доля использованных параметров класса literature/definition — простая прозрачная мера обоснованности."""
    supported = sum(1 for p in params if p.get("evidence") in ("literature", "definition"))
    by_class: dict[str, int] = {}
    for p in params:
        by_class[p.get("evidence", "")] = by_class.get(p.get("evidence", ""), 0) + 1
    share = supported / len(params) if params else 0.0
    level = next(lvl for cut, lvl in CONFIDENCE_LEVELS if share >= cut)
    return {"params_total": len(params), "params_supported": supported, "share": round(share, 3),
            "level": level, "by_evidence": by_class}


def economics(result: dict) -> dict:
    """Выручка, затраты, валовая маржа и чувствительность маржи к цене (все цены ±20 %)."""
    years = result["years"]
    revenue = sum(y["revenue_kzt_ha"] for y in years)
    cost = sum(y["cost_kzt_ha"] for y in years)
    margin = revenue - cost
    return {
        "revenue_kzt_ha": round(revenue),
        "cost_kzt_ha": round(cost),
        "gross_margin_kzt_ha": round(margin),
        "margin_price_minus20_kzt_ha": round(revenue * 0.8 - cost),
        "margin_price_plus20_kzt_ha": round(revenue * 1.2 - cost),
        "breakeven_price_factor": round(cost / revenue, 3) if revenue > 0 else None,
        "per_year": [
            {"year": y["year"], "crop": y["crop"], "revenue_kzt_ha": y["revenue_kzt_ha"], "cost_kzt_ha": y["cost_kzt_ha"],
             "gross_margin_kzt_ha": y["income_kzt_ha"]}
            for y in years
        ],
    }


def compare(
    rules: Rules,
    cond: FieldConditions,
    variants: list[dict],
    history: list[str],
    horizon: int,
    priority: str,
    start_year: int | None = None,
    weights: dict[str, float] | None = None,
) -> dict:
    """Сравнение вариантов: прогноз, оценки 1–5, взвешенный балл, стресс-тест.

    ``weights`` — веса оценок, заданные фермером (почва, вода, доход, риск); нормируются к сумме 1.
    Если не заданы, берутся веса приоритета из model.yaml.
    """
    model = rules.model
    h_cfg = model["horizon"]
    if not (int(h_cfg["min_years"]) <= horizon <= int(h_cfg["max_years"])):
        raise ValueError(f"horizon_years must be between {h_cfg['min_years']} and {h_cfg['max_years']}")
    if priority not in model["priorities"]:
        raise ValueError(f"unknown priority '{priority}'")
    if not variants:
        raise ValueError("at least one rotation variant is required")
    start_year = start_year or default_start_year()

    results = []
    for v in variants:
        sim = simulate(rules, cond, v["crops"], history, horizon, start_year)
        results.append({"id": v["id"], "name": v.get("name"), "custom": bool(v.get("custom")), **sim})

    # Пул для шкалы: сравниваемые варианты + опорные (варианты по умолчанию)
    pool = [r["totals"] for r in results]
    pool_names = [r["id"] for r in results]
    scoring = model["scoring"]
    if scoring.get("include_reference_variants", True):
        known = {tuple(r["crops"]) for r in results}
        for ref in model["default_variants"]:
            sim = simulate(rules, cond, ref["crops"], history, horizon, start_year)
            if tuple(sim["crops"]) not in known:
                pool.append(sim["totals"])
                pool_names.append(f"ref:{ref['id']}")
    neutral = float(scoring.get("neutral_score", 3.0))

    weights_param: Param = model["priorities"][priority]["weights"]
    if weights:
        weights = normalize_weights(weights)
        weights_ref = {
            "path": "user.weights", "value": weights, "unit": "доля", "status": "assumption",
            "evidence": "preliminary", "source": "Веса, заданные пользователем", "url": "",
        }
    else:
        weights = weights_param.value
        weights_ref = weights_param.ref()
    for r in results:
        used = r.pop("_used")
        scores = {}
        for key in SCORE_KEYS:
            metric, direction, unit = METRICS[key]
            values = [t[metric] for t in pool]
            lo, hi = min(values), max(values)
            params = _score_params(used, key)
            scores[key] = {
                "score": _normalize(r["totals"][metric], lo, hi, direction, neutral),
                "metric": metric,
                "value": r["totals"][metric],
                "unit": unit,
                "better": "higher" if direction > 0 else "lower",
                "scale_min": lo,
                "scale_max": hi,
                "pool_size": len(pool),
                "params": params,
                "assumptions": sum(1 for p in params if p["status"] == "assumption"),
            }
        r["scores"] = scores
        r["weighted_score"] = round(sum(weights[k] * scores[k]["score"] for k in SCORE_KEYS), 2)
        all_params = [p.ref() for _, p in sorted(used.items())]
        r["params_used"] = len(all_params)
        r["assumptions_used"] = sum(1 for p in all_params if p["status"] == "assumption")
        r["confidence"] = parameter_confidence(all_params)
        r["economics"] = economics(r)

    best = max(results, key=lambda r: r["weighted_score"])
    for r in results:
        r["fits_priority"] = r is best

    return {
        "start_year": start_year,
        "horizon_years": horizon,
        "priority": priority,
        "weights": {**weights, "_rule": weights_ref},
        "weights_custom": bool(weights) and weights_ref["path"] == "user.weights",
        "conditions": cond.as_dict(),
        "reference_water_mm": round(cond.p_season_ref + cond.stock_ref, 1),
        "normal_water_mm": round(cond.p_season_normal + cond.stock_normal, 1),
        "dry_water_mm": round(cond.p_season_dry + cond.stock_dry, 1),
        "scale_pool": pool_names,
        "variants": results,
        "best_variant_id": best["id"],
    }
