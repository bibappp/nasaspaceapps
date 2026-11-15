#!/usr/bin/env python
"""Воспроизводимый аудит модели на демо-поле.

    cd backend && .venv/bin/python ../scripts/audit_model.py

Что делает (без сети, только data/demo и правила YAML):
  1. Независимо от кода приложения пересчитывает засушливые годы, запас влаги к посеву,
     урожайность, доход, баланс азота и гумуса по годам и сравнивает с ответом модели.
  2. Строит матрицу эффектов предшественников 8x8 и проверяет её на агрономическую
     согласованность.
  3. Сверяет водный индекс модели с независимым наблюдением — максимумом NDVI MODIS по годам.
  4. Анализ чувствительности: как меняются доход и ранжирование вариантов при правдоподобных
     диапазонах ключевых допущений (цены, эффекты предшественников, потребность во влаге, затраты).
  5. «Часы голой почвы» на обоих демо-полях: результат при каждом пороге NDVI из erosion.yaml
     (bare_soil.sensitivity_values), какие месяцы ждут загрузки MODIS межсезонья и сколько месяцев
     посчитано по среднему NDVI поля (proxy).
  6. Планировщик: дни без покрова и индекс опасности эрозии по сценариям на обоих демо-полях; как изменился
     бы рейтинг, если бы индекс входил в балл пятой оценкой «эрозия» (половина веса почвы, вариант «а»,
     docs/MODEL_AUDIT.md § 7); чувствительность к границам периода покрова (erosion.planner).

Пишет docs/audit/audit_results.json и docs/audit/AUDIT_TABLES.md. Результат детерминирован:
повторный запуск на тех же данных даёт те же файлы (кроме даты запуска).
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import statistics
import sys
from datetime import date
from pathlib import Path

import numpy as np
import yaml
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["OFFLINE"] = "1"

from app.data_sources.base import demo_field_record  # noqa: E402
from app.model import rotation  # noqa: E402
from app.model.rules import get_rules  # noqa: E402
from app.schemas import CompareRequest  # noqa: E402
from app.services.comparison import run_compare  # noqa: E402

DEMO = ROOT / "data" / "demo"
RULES = ROOT / "backend" / "app" / "rules"
OUT = ROOT / "docs" / "audit"
START_YEAR = 2027  # фиксируем год начала плана, чтобы результат не зависел от даты запуска
BARE_SOIL_PERIOD = (2015, 2025)  # «Часы голой почвы»: фиксированный период из полных лет
TOL = 1e-6


def load_yaml(name: str) -> dict:
    return yaml.safe_load((RULES / name).read_text(encoding="utf-8"))


def v(node) -> float:
    return node["value"]


# ---------------------------------------------------------------- 1. независимый пересчёт
def independent_drought(power: dict, model_cfg: dict) -> dict:
    """Засушливые годы напрямую из суточного ряда POWER (без pandas и кода приложения)."""
    dates, pr = power["daily"]["date"], power["daily"]["PRECTOTCORR"]
    months = set(model_cfg["season"]["months"])
    by_year: dict[int, list] = {}
    for d, p in zip(dates, pr):
        y, m = int(d[:4]), int(d[5:7])
        if m in months:
            by_year.setdefault(y, []).append(p)
    season = {}
    for y, vals in by_year.items():
        n_days = sum(1 for m in months for _ in range([31, 28 + (y % 4 == 0), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]))
        ok = [x for x in vals if x is not None]
        if len(vals) == n_days and len(ok) / n_days >= 0.95:
            season[y] = sum(ok) * n_days / len(ok)
    dcfg = model_cfg["drought"]
    b0, b1 = dcfg["baseline_years"]
    base = [season[y] for y in season if b0 <= y <= b1]
    mean, sd = statistics.mean(base), statistics.stdev(base)
    p_cut = float(np.percentile(base, v(dcfg["percentile"])))
    years = sorted(season)[-dcfg["window_years"]:]
    dry = [y for y in years if season[y] < p_cut or (season[y] - mean) / sd <= v(dcfg["anomaly_threshold"])]
    return {"season": season, "p_cut": p_cut, "mean": mean, "sd": sd, "window": years, "dry": dry,
            "median": statistics.median(season[y] for y in years)}


def independent_stock(smap: dict, power_season_off: dict, norm: float, awc: float | None, window: list[int], bounds) -> dict:
    acc: dict[int, list[float]] = {}
    for row in smap["daily"]:
        if row["sm"] is not None and int(row["date"][5:7]) in (4, 5):
            acc.setdefault(int(row["date"][:4]), []).append(row["sm"])
    sm = {y: sum(x) / len(x) for y, x in acc.items() if len(x) >= 5}
    med = statistics.median(sm.values())
    off_med = statistics.median(power_season_off[y] for y in window if y in power_season_off)
    stock = {}
    for y in sorted(set(sm) | set(power_season_off)):
        if y in sm:
            r = sm[y] / med
        elif y in power_season_off:
            r = power_season_off[y] / off_med
        else:
            continue
        r = min(max(r, bounds[0]), bounds[1])
        s = norm * r
        stock[y] = min(s, awc) if awc else s
    normal = statistics.median(stock[y] for y in window if y in stock)
    return {"smap_mean": sm, "stock": stock, "normal": normal}


def offseason_sums(power: dict) -> dict[int, float]:
    """Осадки сентября прошлого года – апреля (как в модели), только полные периоды."""
    from collections import defaultdict

    acc: dict[int, list] = defaultdict(list)
    for d, p in zip(power["daily"]["date"], power["daily"]["PRECTOTCORR"]):
        y, m = int(d[:4]), int(d[5:7])
        if m >= 9:
            acc[y + 1].append(p)
        elif m <= 4:
            acc[y].append(p)
    out = {}
    for y, vals in acc.items():
        expected = (date(y, 5, 1) - date(y - 1, 9, 1)).days
        ok = [x for x in vals if x is not None]
        if len(vals) == expected and len(ok) / expected >= 0.95:
            out[y] = sum(ok) * expected / len(ok)
    return out


def independent_simulation(crops_yaml, preds_yaml, regions_yaml, model_yaml, cond, crops, history, horizon):
    """Та же модель, написанная заново прямо по формулам README, без кода приложения."""
    C = crops_yaml["crops"]
    region = regions_yaml["regions"][cond["region"]]
    water = model_yaml["water"]
    mono = model_yaml["monoculture"]
    si = model_yaml["soil_index"]

    def group(c):
        return C[c]["group"]

    def pred_effect(prev, crop):
        if prev is None or group(crop) == "fallow":
            return 0.0
        best = None
        for r in preds_yaml["effects"]:
            def m(pat, cid):
                if pat == cid:
                    return 2
                if pat == f"group:{group(cid)}":
                    return 1
                return 0 if pat == "any" else -1
            mp, mc = m(r["predecessor"], prev), m(r["crop"], crop)
            if mp < 0 or mc < 0 or (r.get("same") and prev != crop):
                continue
            sc = mp * 4 + mc * 2 + (1 if r.get("same") else 0)
            if best is None or sc > best[0]:
                best = (sc, v(r["yield_effect_pct"]))
        return best[1] if best else 0.0

    def ry(crop, w):
        need = v(C[crop]["water_need_mm"])
        if need <= 0:
            return 1.0
        return max(v(water["relative_yield_min"]), 1 - v(C[crop]["ky"]) * (1 - min(1.0, max(0.0, w) / need)))

    w_ref = v(region["reference_season_precip_mm"]) + v(region["presowing_stock_norm_mm"])
    seq = list(history)
    soil = si["start"]
    out = []
    for i in range(horizon):
        crop = crops[i % len(crops)]
        prev = seq[-1] if seq else None
        gain = 1 + v(water["fallow_stock_gain_pct"]) / 100 if prev and group(prev) == "fallow" else 1.0
        stock = cond["stock_normal"] * gain
        stock_dry = cond["stock_dry"] * gain
        if prev and group(prev) == "fallow" and cond["awc_mm"]:
            stock, stock_dry = min(stock, cond["awc_mm"]), min(stock_dry, cond["awc_mm"])
        if group(crop) == "fallow":
            coef = coef_dry = 1.0
        else:
            cmax = v(water["moisture_coef_max"])
            coef = min(cmax, ry(crop, cond["p_season_normal"] + stock) / ry(crop, w_ref))
            coef_dry = min(cmax, ry(crop, cond["p_season_dry"] + stock_dry) / ry(crop, w_ref))
        run = 0
        if group(crop) == "cereal":
            for c in reversed([*seq, crop]):
                if c != crop:
                    break
                run += 1
        is_mono = run >= mono["min_run_years"]
        mono_pct = v(mono["yield_penalty_pct"]) if is_mono else 0.0
        base = v(C[crop]["base_yield_t_ha"]) * v(region["yield_index"])
        y = base * (1 + pred_effect(prev, crop) / 100) * (1 + mono_pct / 100) * coef
        y_dry = base * (1 + pred_effect(prev, crop) / 100) * (1 + mono_pct / 100) * coef_dry
        price, cost = v(C[crop]["price_kzt_t"]), v(C[crop]["cost_kzt_ha"])
        n, h = v(C[crop]["nitrogen_balance_kg_ha"]), v(C[crop]["humus_balance_t_ha"])
        soil += n / v(si["nitrogen_kg_per_point"]) + h / v(si["humus_t_per_point"]) + (v(mono["soil_penalty_points"]) if is_mono else 0)
        out.append({"crop": crop, "yield": y, "yield_dry": y_dry, "income": y * price - cost,
                    "income_dry": y_dry * price - cost, "n": n, "humus": h, "soil_index": soil})
        seq.append(crop)
    return out


# ---------------------------------------------------------------- 3. NDVI как независимое наблюдение
def ndvi_validation(modis: dict, season: dict, stock: dict) -> dict:
    yearly: dict[int, float] = {}
    counts: dict[int, int] = {}
    for r in modis["series"]:
        if r["ndvi"] is None or r["valid_fraction"] < 0.5:
            continue
        y = int(r["date"][:4])
        counts[y] = counts.get(y, 0) + 1
        yearly[y] = max(yearly.get(y, -1), r["ndvi"])
    yearly = {y: x for y, x in yearly.items() if counts[y] >= 5}
    ys = [y for y in sorted(yearly) if y in season]
    precip = [season[y] for y in ys]
    nd = [yearly[y] for y in ys]
    r_p, p_p = stats.pearsonr(precip, nd)
    rho_p, prho_p = stats.spearmanr(precip, nd)
    ys_w = [y for y in ys if y in stock]
    w = [season[y] + stock[y] for y in ys_w]
    r_w, p_w = stats.pearsonr(w, [yearly[y] for y in ys_w])
    return {"years": ys, "ndvi_max": nd, "precip": precip,
            "pearson_precip_ndvi": [round(r_p, 3), round(p_p, 4)],
            "spearman_precip_ndvi": [round(rho_p, 3), round(prho_p, 4)],
            "pearson_water_ndvi": [round(r_w, 3), round(p_w, 4)], "n_water": len(ys_w)}


def hindcast(crops_yaml: dict, dr: dict, st: dict, nd: dict) -> dict:
    """Ретро-прогон: водный коэффициент модели для пшеницы по годам 2002–2026 против NDVI поля."""
    wheat = crops_yaml["crops"]["wheat"]
    need, ky = v(wheat["water_need_mm"]), v(wheat["ky"])

    def ry(w):
        return max(0.05, 1 - ky * (1 - min(1.0, w / need)))

    ndvi = dict(zip(nd["years"], nd["ndvi_max"]))
    years = [y for y in dr["window"] if y in st["stock"] and y in ndvi]
    w_norm = dr["median"] + st["normal"]
    model = [ry(dr["season"][y] + st["stock"][y]) / ry(w_norm) for y in years]
    med = statistics.median(ndvi[y] for y in years)
    obs = [ndvi[y] / med for y in years]
    cv = lambda xs: statistics.pstdev(xs) / statistics.mean(xs)  # noqa: E731
    dry = [i for i, y in enumerate(years) if y in dr["dry"]]
    return {
        "years": years,
        "model_rel": [round(x, 3) for x in model],
        "ndvi_rel": [round(x, 3) for x in obs],
        "pearson": round(float(stats.pearsonr(obs, model)[0]), 3),
        "cv_model": round(cv(model), 3),
        "cv_ndvi": round(cv(obs), 3),
        "dry_mean_model": round(statistics.mean(model[i] for i in dry), 3),
        "dry_mean_ndvi": round(statistics.mean(obs[i] for i in dry), 3),
    }


# ---------------------------------------------------------------- 4. чувствительность
def patch_crop(rules, crop_id, key, value):
    crop = dict(rules.crops[crop_id])
    crop[key] = dataclasses.replace(crop[key], value=value)
    return dataclasses.replace(rules, crops={**rules.crops, crop_id: crop})


def patch_pred(rules, rule_id, value):
    preds = []
    for r in rules.predecessors:
        if r["id"] == rule_id:
            r = {**r, "yield_effect_pct": dataclasses.replace(r["yield_effect_pct"], value=value)}
        preds.append(r)
    return dataclasses.replace(rules, predecessors=preds)


def scale_all(rules, key, factor):
    crops = {}
    for cid, c in rules.crops.items():
        c = dict(c)
        c[key] = dataclasses.replace(c[key], value=c[key].value * factor)
        crops[cid] = c
    return dataclasses.replace(rules, crops=crops)


def summarize(rules, cond, history, priority="max_income"):
    variants = [{"id": x["id"], "name": x["name"], "crops": list(x["crops"])} for x in rules.model["default_variants"]]
    res = rotation.compare(rules, cond, variants, history, 4, priority, start_year=START_YEAR)
    inc = {x["id"]: x["totals"]["income_kzt_ha"] for x in res["variants"]}
    ranking = [x["id"] for x in sorted(res["variants"], key=lambda r: -r["totals"]["income_kzt_ha"])]
    return {"income": inc, "best_weighted": res["best_variant_id"], "income_ranking": ranking,
            "loss_pct": {x["id"]: x["totals"]["drought_loss_pct"] for x in res["variants"]}}


def horizon_effect(rules, cond, history) -> dict:
    """Средний доход в год при горизонте 4 и 5 лет: проверка эффекта обрезки горизонта."""
    variants = [{"id": x["id"], "name": x["name"], "crops": list(x["crops"])} for x in rules.model["default_variants"]]
    out = {}
    for h in (4, 5):
        res = rotation.compare(rules, cond, variants, history, h, "max_income", start_year=START_YEAR)
        out[h] = {x["id"]: {"per_year": x["totals"]["income_per_year_kzt_ha"], "crops": x["crops"],
                            "soil_index_end": x["totals"]["soil_index_end"]} for x in res["variants"]}
    return out


def sensitivity(rules, cond, history) -> list[dict]:
    wheat_price = rules.crop("wheat")["price_kzt_t"].value
    cases = [("Базовые правила", rules)]
    for p in (67500, 92000, 104000, 115000):
        if p != wheat_price:
            cases.append((f"Цена пшеницы {p // 1000} тыс. тг/т", patch_crop(rules, "wheat", "price_kzt_t", p)))
    for pct in (0, 15, 36):
        cases.append((f"Пшеница после гороха {pct:+d} %", patch_pred(rules, "wheat_after_pea", pct)))
    cases.append(("Пшеница после чечевицы 0 % (полное азотное питание, Zentner 1997)", patch_pred(rules, "wheat_after_lentil", 0)))
    r0 = patch_pred(patch_pred(patch_pred(rules, "wheat_after_pea", 0), "wheat_after_lentil", 0), "wheat_after_chickpea", 0)
    cases.append(("Эффекты бобовых предшественников = 0", r0))
    cases.append(("Потребность пшеницы во влаге 400 мм", patch_crop(rules, "wheat", "water_need_mm", 400)))
    cases.append(("Затраты всех культур +30 %", scale_all(rules, "cost_kzt_ha", 1.3)))
    cases.append(("Урожайность всех культур −20 %", scale_all(rules, "base_yield_t_ha", 0.8)))
    alt = rules
    for cid in ("lentil", "pea", "chickpea", "flax", "rapeseed", "sunflower"):
        alt = patch_crop(alt, cid, "base_yield_t_ha", alt.crop(cid)["base_yield_t_ha"].value * 0.8)
    cases.append(("Урожайность всех культур, кроме пшеницы, −20 %", alt))
    cons = r0
    for cid in ("lentil", "pea", "chickpea", "flax", "rapeseed", "sunflower"):
        cons = patch_crop(cons, cid, "base_yield_t_ha", cons.crop(cid)["base_yield_t_ha"].value * 0.8)
        cons = patch_crop(cons, cid, "cost_kzt_ha", cons.crop(cid)["cost_kzt_ha"].value * 1.3)
    cases.append(("Консервативный: без эффекта бобовых, альтернативы −20 % урожая и +30 % затрат", cons))
    out = []
    for name, r in cases:
        s = summarize(r, cond, history)
        out.append({"case": name, **s})
    return out


# ---------------------------------------------------------------- 5. «Часы голой почвы»
def patch_erosion(rules, group, key, value):
    g = dict(rules.erosion[group])
    g[key] = dataclasses.replace(g[key], value=value)
    return dataclasses.replace(rules, erosion={**rules.erosion, group: g})


MONTH_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def _bare_soil_case(body: dict, t: float, current: float) -> dict:
    months = [m for y in body["years"] for m in y["months"]]
    ok = [m for m in months if m["state"] == "ok"]
    missing = [m for m in months if m["state"] == "missing"]
    reasons: dict[str, int] = {}
    for m in missing:
        reasons[m["missing_reason"]] = reasons.get(m["missing_reason"], 0) + 1
    pending = {mo: sum(1 for y in body["years"] for m in y["months"]
                       if m["month"] == mo and m["missing_reason"] == "ndvi_pending_fetch") for mo in range(1, 13)}
    proxy = next((w["params"]["months"] for w in body["warnings"] if w["code"] == "ndvi_field_mean_proxy"), 0)
    known = sum(m["known_days"] for m in ok)
    joint = sum(m["joint_days"] for m in ok)
    return {
        "ndvi_max": t,
        "is_rule_value": t == current,
        "status": body["status"],
        "months_ok": len(ok),
        "months_partial": sum(m["quality"] == "partial" for m in ok),
        "months_snow": sum(m["state"] == "snow" for m in months),
        "months_missing": len(missing),
        "months_total": len(months),
        "missing_by_reason": dict(sorted(reasons.items())),
        "pending_fetch_by_month": {mo: n for mo, n in pending.items() if n},
        "proxy_months": proxy,
        "bare_days": sum(m["bare_days"] for m in ok),
        "joint_days": joint,
        "known_days": known,
        "pooled_exposure": round(joint / known, 4) if known else None,
        "top_months": body["headline"]["top_months"],
        "max_median_exposure": body["headline"]["max_median_exposure"],
        "climatology_median": {c["month"]: c["exposure_median"] for c in body["climatology"]},
        "cover_crop_windows": [{k: w[k] for k in ("start", "end", "uncertainty")} for w in body["cover_crop_windows"]],
        "cover_crop_note": body["cover_crop_note"],
        "effective_thresholds": body["effective_thresholds"],
    }


def gwettop_vs_smap_by_month(directory: Path, eff: dict, rules) -> list[dict]:
    """Доля сухих дней по месяцам: SMAP (< θ_wp) и GWETTOP (< порога поля, подобранного по всем месяцам сразу).
    Показывает, совпадает ли GWETTOP с SMAP в каждом месяце, а не только в среднем за апрель–октябрь."""
    from app.analytics import bare_soil as bs

    def read(name):
        p = directory / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    power = read("power.json")
    if not power or not eff:
        return []
    df = bs.power_frame(power)
    years = range(BARE_SOIL_PERIOD[0], BARE_SOIL_PERIOD[1] + 1)
    df = df[df.index.year.isin(years)]
    sm = bs.smap_days(read("smap.json"), read("smap_season.json"))
    sm = sm[sm.index.year.isin(years)]
    snow = bs.power_snow(df, rules.erosion)
    gw = df["GWETTOP"].astype(float)
    common = sm.index.intersection(gw.dropna().index)
    common = common[~snow.reindex(common, fill_value=False).to_numpy(dtype=bool)]
    out = []
    for m in range(4, 11):
        days = df.index[(df.index.month == m) & ~snow.to_numpy(dtype=bool)]
        c = common[common.month == m]
        if len(days) == 0 or len(c) == 0:
            continue
        smap_dry = float((sm.loc[c] < eff["smap_m3m3"]).mean())
        out.append({"month": m, "days": len(days), "smap_days": int(sm.index.isin(days).sum()), "pairs": len(c),
                    "smap_dry_share": round(smap_dry, 3),
                    "gwettop_dry_share_same_days": round(float((gw.loc[c] < eff["gwettop"]).mean()), 3),
                    "gwettop_month_threshold": round(float(np.quantile(gw.loc[c], smap_dry)) if smap_dry > 0
                                                     else float(gw.loc[c].min()), 3)})
    return out


async def bare_soil_sensitivity(rules) -> list[dict]:
    """Ответ /bare-soil для обоих демо-полей при каждом пороге NDVI из bare_soil.sensitivity_values."""
    from app.data_sources.base import demo_field_records
    from app.services.bare_soil import bare_soil

    current = rules.erosion["bare_soil"]["ndvi_max"].value
    out = []
    for rec in demo_field_records():
        cases = []
        for t in rules.erosion["bare_soil"]["sensitivity_values"]:
            body = await bare_soil(0, rec["geometry"], *BARE_SOIL_PERIOD,
                                   rules=patch_erosion(rules, "bare_soil", "ndvi_max", t), start_jobs=False,
                                   region=rec["region"])
            cases.append(_bare_soil_case(body, t, current))
        eff = next(c for c in cases if c["is_rule_value"])["effective_thresholds"]
        out.append({"id": rec["id"], "name": rec["name"]["ru"], "area_ha": rec.get("area_ha"), "cases": cases,
                    "dry_by_month": gwettop_vs_smap_by_month(Path(rec["_dir"]), eff, rules)})
    return out


# ---------------------------------------------------------------- планировщик: дни без покрова (задача 5)
def erosion_option_a(res: dict, exposure: dict[str, float], weights: dict[str, float]) -> dict:
    """Вариант «а» (только аудит): пятая оценка «эрозия» 1–5 по exposure_index (меньше — лучше), вес — половина
    веса почвы; остальные веса как в приоритете. Шкала — по тем же вариантам, что и остальные оценки."""
    neutral = float(res_scoring_neutral())
    vals = [exposure[v["id"]] for v in res["variants"]]
    lo, hi = min(vals), max(vals)
    w = {**weights, "soil": weights["soil"] / 2, "erosion": weights["soil"] / 2}
    out = {}
    for v in res["variants"]:
        e = rotation._normalize(exposure[v["id"]], lo, hi, -1, neutral)
        score = sum(w[k] * v["scores"][k]["score"] for k in rotation.SCORE_KEYS) + w["erosion"] * e
        out[v["id"]] = {"erosion_score": e, "weighted": round(score, 2), "weighted_now": v["weighted_score"]}
    return out


def res_scoring_neutral() -> float:
    return float(get_rules().model["scoring"].get("neutral_score", 3.0))


def _ranking(scores: dict[str, float]) -> list[str]:
    return [k for k, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


async def planner_bare_soil(rules) -> dict:
    """Дни без покрова и exposure по сценариям обоих демо-полей; рейтинг сейчас и при варианте «а»;
    чувствительность к границам покрова. Климатология — полные годы BARE_SOIL_PERIOD."""
    from app.analytics import scenario_exposure as se
    from app.data_sources.base import demo_field_records
    from app.geometry import parse_field
    from app.model.rotation import FieldConditions
    from app.services.bare_soil import planner_climate

    pl = rules.erosion["planner"]
    variants = [{"id": x["id"], "name": x["name"], "crops": list(x["crops"])} for x in rules.model["default_variants"]]
    fields = []
    for rec in demo_field_records():
        history = [h["crop"] for h in sorted(rec["history"], key=lambda h: h["year"])]
        comp, _ = await run_compare(CompareRequest(geometry=rec["geometry"], region=rec["region"], history=rec["history"],
                                                   horizon_years=4, start_year=START_YEAR))
        cond = FieldConditions(**comp["conditions"])
        climate = await planner_climate(parse_field(rec["geometry"]), rules,
                                        today=date(BARE_SOIL_PERIOD[1] + 1, 6, 1))
        by_priority = {}
        for pid, pr in rules.model["priorities"].items():
            res = rotation.compare(rules, cond, variants, history, 4, pid, start_year=START_YEAR)
            sc = {v["id"]: se.scenario(rules, v["years"], climate) for v in res["variants"]}
            a = erosion_option_a(res, {k: x["mean_exposure"] for k, x in sc.items()}, pr["weights"].value)
            by_priority[pid] = {"now": _ranking({k: x["weighted_now"] for k, x in a.items()}),
                                "option_a": _ranking({k: x["weighted"] for k, x in a.items()}), "scores": a}
        res = rotation.compare(rules, cond, variants, history, 4, "balanced", start_year=START_YEAR)
        base = {v["id"]: se.scenario(rules, v["years"], climate) for v in res["variants"]}
        sens = []
        for c0 in pl["sensitivity_canopy_start"]:
            for c1 in pl["sensitivity_canopy_end"]:
                cases = {}
                for pid, pr in rules.model["priorities"].items():
                    r2 = rotation.compare(rules, cond, variants, history, 4, pid, start_year=START_YEAR)
                    sc = {v["id"]: se.scenario(rules, v["years"], climate, start=c0, end=c1) for v in r2["variants"]}
                    a = erosion_option_a(r2, {k: x["mean_exposure"] for k, x in sc.items()}, pr["weights"].value)
                    cases[pid] = _ranking({k: x["weighted"] for k, x in a.items()})[0]
                sc = {v["id"]: se.scenario(rules, v["years"], climate, start=c0, end=c1) for v in res["variants"]}
                sens.append({"canopy_start": c0, "canopy_end": c1,
                             "is_rule_value": c0 == pl["canopy_start"].value and c1 == pl["canopy_end"].value,
                             "bare_days": {k: x["bare_days_per_year"] for k, x in sc.items()},
                             "exposure": {k: x["mean_exposure"] for k, x in sc.items()},
                             "best_option_a": cases})
        fields.append({"id": rec["id"], "name": rec["name"]["ru"], "season": se.season_out(climate),
                       "variants": {k: {"crops": next(v["crops"] for v in res["variants"] if v["id"] == k),
                                        "bare_days_per_year": x["bare_days_per_year"],
                                        "exposure_index": x["mean_exposure"],
                                        "risky_days_per_year": x["risky_days_per_year"],
                                        "per_year": [(y["crop"], y["bare_days"], y["risky_days"]) for y in x["per_year"]]}
                                    for k, x in base.items()},
                       "by_priority": by_priority, "sensitivity": sens})
    return {"period": list(BARE_SOIL_PERIOD), "canopy_start": pl["canopy_start"].value,
            "canopy_end": pl["canopy_end"].value, "fields": fields}


# ---------------------------------------------------------------- main
async def main() -> None:
    rules = get_rules()
    demo = demo_field_record()
    req = CompareRequest(geometry=demo["geometry"], region=demo["region"], history=demo["history"],
                         priority=demo["priority"], horizon_years=demo["horizon_years"], start_year=START_YEAR)
    comparison, analysis = await run_compare(req)
    a = analysis.response
    cond = comparison["conditions"]
    power = json.loads((DEMO / "power.json").read_text(encoding="utf-8"))
    smap = json.loads((DEMO / "smap.json").read_text(encoding="utf-8"))
    modis = json.loads((DEMO / "modis.json").read_text(encoding="utf-8"))
    cy, py_, ry_, my = load_yaml("crops.yaml"), load_yaml("predecessors.yaml"), load_yaml("regions.yaml"), load_yaml("model.yaml")
    checks: list[dict] = []

    def check(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1a. засушливые годы
    dr = independent_drought(power, my)
    check("Засушливые годы: независимый пересчёт совпадает", dr["dry"] == a["drought"]["dry_years"],
          f"пересчёт {dr['dry']} / модель {a['drought']['dry_years']}; порог P20 = {dr['p_cut']:.1f} мм; "
          f"норма {dr['mean']:.1f} ± {dr['sd']:.1f} мм")
    check("Осадки май–август в обычный год (медиана 25 лет)", abs(dr["median"] - cond["p_season_normal"]) < 0.06,
          f"пересчёт {dr['median']:.1f} мм / модель {cond['p_season_normal']} мм")
    check("Год стресс-теста засушлив по данным поля", cond["dry_year"] in dr["dry"],
          f"{cond['dry_year']}: {dr['season'][cond['dry_year']]:.1f} мм")
    # 1b. запас влаги
    off = offseason_sums(power)
    awc = a["soil"]["summary"]["awc_mm"] if a["soil"]["summary"] else None
    st = independent_stock(smap, off, v(ry_["regions"][cond["region"]]["presowing_stock_norm_mm"]), awc, dr["window"],
                           my["water"]["smap_ratio_bounds"])
    check("Обычный запас влаги к посеву", abs(st["normal"] - cond["stock_normal"]) < 0.06,
          f"пересчёт {st['normal']:.1f} мм / модель {cond['stock_normal']} мм (основа: SMAP апрель–май)")
    check("Запас влаги в засушливый год", abs(st["stock"][cond["dry_year"]] - cond["stock_dry"]) < 0.06,
          f"пересчёт {st['stock'][cond['dry_year']]:.1f} мм / модель {cond['stock_dry']} мм")
    # 1c. урожайность, доход, азот, гумус по годам
    history = [h["crop"] for h in sorted(demo["history"], key=lambda h: h["year"])]
    worst = 0.0
    for var in comparison["variants"]:
        ind = independent_simulation(cy, py_, ry_, my, cond, var["crops"], history, len(var["years"]))
        for mine, model in zip(ind, var["years"]):
            worst = max(worst, abs(mine["yield"] - model["yield_t_ha"]), abs(mine["income"] - model["income_kzt_ha"]) / 1000,
                        abs(mine["soil_index"] - model["soil_index"]))
        n_sum, h_sum = sum(x["n"] for x in ind), sum(x["humus"] for x in ind)
        check(f"Баланс азота и гумуса: {var['id']}",
              abs(n_sum - var["totals"]["nitrogen_kg_ha"]) < 0.06 and abs(h_sum - var["totals"]["humus_t_ha"]) < 0.006,
              f"N {n_sum:+.0f} кг/га, гумус {h_sum:+.2f} т/га за 4 года")
    check("Урожайность, доход и индекс почвы по годам совпадают с независимым пересчётом", worst < 0.01,
          f"максимальное расхождение {worst:.4f} (т/га, тыс. тг/га или пункты; округление модели)")

    # 2. матрица предшественников
    crops = list(rules.crops)
    matrix = {p: {c: rules.predecessor_effect(p, c)[0] for c in crops} for p in crops}
    legumes = [c for c in crops if rules.group(c) == "legume"]
    check("После любой бобовой пшеница не хуже, чем по пшенице", all(matrix[l]["wheat"] > 0 for l in legumes),
          ", ".join(f"{l}: {matrix[l]['wheat']:+.0f} %" for l in legumes))
    check("Повтор той же культуры (кроме зерновых — для них штраф монокультуры) не даёт прибавки",
          all(matrix[c][c] <= 0 for c in crops), ", ".join(f"{c}: {matrix[c][c]:+.0f}" for c in crops))
    check("Пар как предшественник не задан эффектом урожайности (учтён через влагу)", all(matrix["fallow"][c] == 0 for c in crops), "")

    # 3. NDVI
    nd = ndvi_validation(modis, dr["season"], st["stock"])
    dry_nd = [x for y, x in zip(nd["years"], nd["ndvi_max"]) if y in dr["dry"]]
    wet_nd = [x for y, x in zip(nd["years"], nd["ndvi_max"]) if y not in dr["dry"]]
    t = stats.mannwhitneyu(dry_nd, wet_nd, alternative="less")
    nd["dry_vs_other"] = {"dry_mean": round(statistics.mean(dry_nd), 3), "other_mean": round(statistics.mean(wet_nd), 3),
                          "n_dry": len(dry_nd), "n_other": len(wet_nd), "mannwhitney_p_less": round(float(t.pvalue), 4)}

    hc = hindcast(cy, dr, st, nd)

    # 4. чувствительность (модель приложения с изменёнными правилами)
    from app.model.rotation import FieldConditions

    fc = FieldConditions(**cond)
    sens = sensitivity(rules, fc, history)
    hz = horizon_effect(rules, fc, history)
    bs = await bare_soil_sensitivity(rules)
    pbs = await planner_bare_soil(rules)

    result = {
        "run_date": date.today().isoformat(),
        "start_year": START_YEAR,
        "field": {"area_ha": a["field"]["area_ha"], "centroid": a["field"]["centroid"]},
        "conditions": cond,
        "drought": {"dry_years": dr["dry"], "window": [dr["window"][0], dr["window"][-1]], "p20_mm": round(dr["p_cut"], 1),
                    "share": round(len(dr["dry"]) / len(dr["window"]), 3)},
        "checks": checks,
        "predecessor_matrix": matrix,
        "ndvi_validation": nd,
        "hindcast": hc,
        "sensitivity": sens,
        "horizon_effect": hz,
        "bare_soil_ndvi_sensitivity": {"period": list(BARE_SOIL_PERIOD), "fields": bs},
        "planner_bare_soil": pbs,
        "variants": {x["id"]: {"crops": x["crops"], "totals": x["totals"],
                               "years": [{k: y[k] for k in ("year", "crop", "yield_t_ha", "yield_dry_t_ha", "income_kzt_ha",
                                                             "moisture_coef", "predecessor_effect_pct", "monoculture_penalty_pct")}
                                         for y in x["years"]]}
                     for x in comparison["variants"]},
        "rule_counts": {"total": len(rules.all_params()),
                        "verified": sum(p.status == "verified" for p in rules.all_params()),
                        "by_evidence": {e: sum(p.evidence == e for p in rules.all_params())
                                        for e in ("literature", "agronomist_review", "preliminary", "definition")}},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    write_markdown(result, rules)
    write_parameters(rules)
    failed = [c for c in checks if not c["ok"]]
    for c in checks:
        print(("OK  " if c["ok"] else "FAIL") + f" {c['check']}: {c['detail']}")
    print(f"NDVI ~ осадки: Pearson r = {nd['pearson_precip_ndvi'][0]} (p = {nd['pearson_precip_ndvi'][1]}); "
          f"засушливые годы NDVI {nd['dry_vs_other']['dry_mean']} против {nd['dry_vs_other']['other_mean']}")
    for f in bs:
        for c in f["cases"]:
            print(f"Часы голой почвы, {f['id']}, NDVI < {c['ndvi_max']:.2f}: status {c['status']}, посчитано "
                  f"{c['months_ok']} из {c['months_total']} мес. (снег {c['months_snow']}, ждут MODIS межсезонья "
                  f"{c['missing_by_reason'].get('ndvi_pending_fetch', 0)}, по среднему NDVI {c['proxy_months']}), "
                  f"макс. медиана exposure {c['max_median_exposure']}")
    for f in pbs["fields"]:
        changed = [p for p, x in f["by_priority"].items() if x["now"][0] != x["option_a"][0]]
        print(f"Планировщик, {f['id']}: без покрова " + ", ".join(
            f"{k} {x['bare_days_per_year']} дн. / {x['exposure_index']}" for k, x in f["variants"].items())
            + f"; вариант «а» меняет лучший сценарий для приоритетов: {changed or 'нет'}")
    print(f"Записано: {OUT / 'audit_results.json'}, {OUT / 'AUDIT_TABLES.md'}")
    if failed:
        raise SystemExit(f"{len(failed)} проверок не прошли")


def fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ").replace("-", "−")


def write_markdown(r: dict, rules) -> None:
    planner = r["planner_bare_soil"]  # ниже имя r переиспользуется в циклах
    names = {v["id"]: v["name"]["ru"] for v in rules.model["default_variants"]}
    L = ["# Таблицы аудита модели (сгенерировано `scripts/audit_model.py`)", "",
         f"Демо-поле {r['field']['area_ha']} га, план с {r['start_year']} г., данные `data/demo/`. Дата запуска: {r['run_date']}.", "",
         "## Независимые проверки расчёта", "", "| Проверка | Итог | Детали |", "|---|---|---|"]
    for c in r["checks"]:
        L.append(f"| {c['check']} | {'✅' if c['ok'] else '❌'} | {c['detail']} |")
    L += ["", "## Урожайность и доход по годам (базовые правила)", ""]
    for vid, x in r["variants"].items():
        L.append(f"**{names.get(vid, vid)}** — доход за 4 года {fmt(x['totals']['income_kzt_ha'])} тг/га, "
                 f"N {x['totals']['nitrogen_kg_ha']:+.0f} кг/га, гумус {x['totals']['humus_t_ha']:+.2f} т/га, "
                 f"индекс почвы {x['totals']['soil_index_end']}")
        L.append("")
        L.append("| Год | Культура | Урожайность, т/га | В засуху, т/га | Коэф. влаги | Предшественник, % | Монокультура, % | Доход, тг/га |")
        L.append("|---|---|---|---|---|---|---|---|")
        for y in x["years"]:
            L.append(f"| {y['year']} | {y['crop']} | {y['yield_t_ha']:.2f} | {y['yield_dry_t_ha']:.2f} | {y['moisture_coef']:.3f} | "
                     f"{y['predecessor_effect_pct']:+.0f} | {y['monoculture_penalty_pct']:+.0f} | {fmt(y['income_kzt_ha'])} |")
        L.append("")
    crops = list(r["predecessor_matrix"])
    L += ["## Матрица эффектов предшественников, % к урожайности по зерновому предшественнику", "",
          "Строка — предшественник, столбец — культура.", "", "| | " + " | ".join(crops) + " |", "|---" * (len(crops) + 1) + "|"]
    for p in crops:
        L.append(f"| **{p}** | " + " | ".join(f"{r['predecessor_matrix'][p][c]:+.0f}" for c in crops) + " |")
    nd = r["ndvi_validation"]
    L += ["", "## Независимое наблюдение: NDVI MODIS и влага", "",
          f"- Связь осадков май–август и максимума NDVI за сезон, {nd['years'][0]}–{nd['years'][-1]}: "
          f"Pearson r = {nd['pearson_precip_ndvi'][0]} (p = {nd['pearson_precip_ndvi'][1]}), "
          f"Spearman ρ = {nd['spearman_precip_ndvi'][0]} (p = {nd['spearman_precip_ndvi'][1]}).",
          f"- Водный индекс модели (осадки + запас влаги, {nd['n_water']} лет с SMAP или POWER) и NDVI: "
          f"r = {nd['pearson_water_ndvi'][0]} (p = {nd['pearson_water_ndvi'][1]}).",
          f"- Максимум NDVI в засушливые годы {nd['dry_vs_other']['dry_mean']} (n = {nd['dry_vs_other']['n_dry']}) против "
          f"{nd['dry_vs_other']['other_mean']} в остальные (n = {nd['dry_vs_other']['n_other']}); "
          f"Манн–Уитни, односторонний p = {nd['dry_vs_other']['mannwhitney_p_less']}.", "",
          "## Ретро-прогон 2002–2026: водный коэффициент пшеницы в модели против NDVI поля", "",
          f"- Корреляция по годам r = {r['hindcast']['pearson']}; изменчивость (CV) модели {r['hindcast']['cv_model']}, "
          f"NDVI {r['hindcast']['cv_ndvi']}.",
          f"- В засушливые годы: модель {r['hindcast']['dry_mean_model']} от обычного года, NDVI {r['hindcast']['dry_mean_ndvi']} от медианы.",
          "- NDVI отражает зелёную массу, а не урожай, поэтому величину потерь по нему откалибровать нельзя; "
          "согласованность направления и порядка изменчивости — необходимая, но не достаточная проверка.", "",
          "## Чувствительность к допущениям (приоритет «максимальный доход», доход за 4 года, тг/га)", "",
          "| Сценарий | " + " | ".join(names[k] for k in names) + " | Лучший по доходу | Лучший по взвешенному баллу |",
          "|---" * (len(names) + 3) + "|"]
    for s in r["sensitivity"]:
        L.append(f"| {s['case']} | " + " | ".join(fmt(s["income"][k]) for k in names) +
                 f" | {names[s['income_ranking'][0]]} | {names[s['best_weighted']]} |")
    hz = r["horizon_effect"]
    L += ["", "## Эффект горизонта: средний доход в год, тг/га", "",
          "Пар или бобовая культура в последнем году плана несут затраты, а прибавка следующей культуры выходит за горизонт.", "",
          "| Вариант | 4 года | 5 лет | Культуры 5-летнего плана |", "|---|---|---|---|"]
    for k in names:
        L.append(f"| {names[k]} | {fmt(hz[4][k]['per_year'])} | {fmt(hz[5][k]['per_year'])} | {' → '.join(hz[5][k]['crops'])} |")
    bsr = r["bare_soil_ndvi_sensitivity"]
    p0, p1 = bsr["period"]

    def num(x, digits=2):
        return "—" if x is None else f"{x:.{digits}f}".replace(".", ",")

    L += ["", "## «Часы голой почвы»: чувствительность к порогу NDVI", "",
          f"Оба демо-поля, {p0}–{p1}, `OFFLINE=1` (только `data/demo`). Класс — «нет зелёного покрова (открытая почва "
          "или стерня)»; exposure — верхняя оценка риска там, где стерня оставлена стоять. "
          "exposure месяца = joint_days / known_days (known_days — дни, когда известны все три условия). "
          "Порог 0,30 в `erosion.yaml` подобран по этим же демо-полям, поэтому сравнение порогов здесь — "
          "не независимая проверка.", "",
          "| Поле | Порог NDVI | В правилах | Статус | Посчитано мес. | из них partial | Снег | Нет данных | "
          "Ждут MODIS межсезонья | По среднему NDVI | Дней без покрова | Опасных дней | Известных дней | "
          "Доля опасных (все месяцы) | Самые опасные месяцы | Макс. медиана exposure |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in bsr["fields"]:
        for c in f["cases"]:
            top = ", ".join(MONTH_RU[m - 1] for m in c["top_months"]) or "—"
            L.append(f"| {f['name']} | < {num(c['ndvi_max'])} | {'да' if c['is_rule_value'] else 'нет'} | {c['status']} | "
                     f"{c['months_ok']} из {c['months_total']} | {c['months_partial']} | {c['months_snow']} | "
                     f"{c['months_missing']} | {c['missing_by_reason'].get('ndvi_pending_fetch', 0)} | {c['proxy_months']} | "
                     f"{c['bare_days']} | {c['joint_days']} | {c['known_days']} | {num(c['pooled_exposure'], 3)} | {top} | "
                     f"{num(c['max_median_exposure'])} |")
    L += ["", "Медиана exposure по месяцам (только месяцы, посчитанные не меньше чем в `climatology.min_years` годах):", "",
          "| Поле | Порог NDVI | " + " | ".join(MONTH_RU) + " |", "|---|---|" + "---|" * 12]
    for f in bsr["fields"]:
        for c in f["cases"]:
            med = c["climatology_median"]
            L.append(f"| {f['name']} | < {num(c['ndvi_max'])} | " +
                     " | ".join(num(med.get(m, med.get(str(m)))) for m in range(1, 13)) + " |")
    rule_cases = [next(x for x in f["cases"] if x["is_rule_value"]) for f in bsr["fields"]]
    n_pending = sum(c["missing_by_reason"].get("ndvi_pending_fetch", 0) for c in rule_cases)
    n_proxy = sum(c["proxy_months"] for f in bsr["fields"] for c in f["cases"])
    L += ["", "### Месяцы, которые ждут загрузки MODIS межсезонья (`missing_reason: ndvi_pending_fetch`)", "",
          ("Весенние (DOY 81–113, ≈ 22 марта – 8 мая) и осенние (DOY 289–305, ≈ 16 октября – 16 ноября) композиты "
           "MOD13Q1 (`modis_shoulder`) в `data/demo` ещё не скачаны (TODO в `docs/HACKATHON_LOG.md`). Пока их нет, эти "
           "месяцы — `state: missing`, а не 0." if n_pending else
           "Весенние (DOY 81–113) и осенние (DOY 289–305) композиты MOD13Q1 (`modis_shoulder`) в `data/demo` загружены "
           "для обоих полей; месяцев, ждущих загрузки, нет.") +
          " Число лет периода, в которых месяц не посчитан по этой причине:", "",
          "| Поле | " + " | ".join(MONTH_RU) + " |", "|---|" + "---|" * 12]
    for f in bsr["fields"]:
        c = next(x for x in f["cases"] if x["is_rule_value"])
        pend = {int(k): n for k, n in c["pending_fetch_by_month"].items()}
        L.append(f"| {f['name']} | " + " | ".join(str(pend.get(m, 0) or "") for m in range(1, 13)) + " |")
    L += ["", "Все причины `missing` (порог из правил): " + "; ".join(
        f"{f['name']} — " + (", ".join(f"{k}: {n}" for k, n in next(x for x in f["cases"] if x["is_rule_value"])
                                       ["missing_by_reason"].items()) or "нет") for f in bsr["fields"]) + ".",
          "`future` — месяцы после последнего дня POWER, `ndvi_not_covered` — зима вне окон MODIS без снежного покрова "
          "(меньше половины дней со снегом), `ndvi_gap` — нет годного композита (облака).", "",
          "### Месяцы, где «нет зелёного покрова» определено по среднему NDVI поля (proxy)", "",
          ("Если у композита нет квантилей NDVI (`ndvi_q`) и пиксельного растра, день считается «без покрова», когда "
           "ниже порога среднее NDVI поля. Такие месяцы — `quality: partial`, предупреждение `ndvi_field_mean_proxy`. "
           "Перезагрузите MODIS (`make demo ARGS=\"--only modis --refresh\"`), чтобы proxy исчез." if n_proxy else
           "У всех композитов MOD13Q1 в `data/demo` есть квантили NDVI (`ndvi_q`), поэтому среднее NDVI поля "
           "(proxy, предупреждение `ndvi_field_mean_proxy`) нигде не используется."), "",
          "| Поле | Порог NDVI | Месяцев по среднему NDVI |", "|---|---|---|"]
    for f in bsr["fields"]:
        for c in f["cases"]:
            L.append(f"| {f['name']} | < {num(c['ndvi_max'])} | {c['proxy_months']} |")
    L += ["", "Пороги, применённые к полям (порог из правил): " + "; ".join(
        (lambda eff: f"{f['name']} — SMAP < {num(eff['smap_m3m3'], 3)} м³/м³ ({eff['smap_basis']}), GWETTOP < "
                     f"{num(eff['gwettop'], 2)} ({eff['gwettop_basis']}, {eff['gwettop_pairs']} общих дней), "
                     f"медианы заморозков {eff['last_frost_spring']} / {eff['first_frost_autumn']}")
        (next(x for x in f["cases"] if x["is_rule_value"])["effective_thresholds"]) for f in bsr["fields"]) + "."]
    L += ["", "### Окна покровных культур (порог из правил)", "",
          "Окно начинается не раньше типичного окончания уборки в области (`cover_crop.harvest_end`) и кончается до "
          "медианы первого осеннего заморозка; от начала окна до заморозка — не меньше `cover_crop.min_frost_free_days`.",
          "", "| Поле | Уборка до | Первый заморозок | Окна | Почему окна нет |", "|---|---|---|---|---|"]
    for f in bsr["fields"]:
        c = next(x for x in f["cases"] if x["is_rule_value"])
        eff, note = c["effective_thresholds"], c["cover_crop_note"]
        wins = ", ".join(f"{w['start']}…{w['end']} ({w['uncertainty']})" for w in c["cover_crop_windows"]) or "нет"
        L.append(f"| {f['name']} | {eff.get('harvest_end')} | {eff['first_frost_autumn']} | {wins} | "
                 f"{(note['reason'] + ': ' + note['basis']['ru']) if note else ''} |")
    L += ["", "### Сухой верхний слой: GWETTOP и SMAP по месяцам", "",
          "Порог GWETTOP подобран по всем общим бесснежным дням апреля–октября сразу (`dry_topsoil.gwettop_method: "
          "cdf_match`). Таблица проверяет, совпадает ли доля сухих дней GWETTOP с SMAP **в каждом месяце** на общих днях; "
          "«порог при подборе по месяцу» — какой порог дал бы совпадение в этом месяце (справочно, в расчёте не "
          "используется). GWETTOP применяется только в дни без SMAP. См. `docs/MODEL_AUDIT.md`, раздел 6.", "",
          "| Поле | Месяц | Бесснежных дней | Из них со SMAP | Сухо по SMAP | Сухо по GWETTOP (порог поля) | "
          "Порог при подборе по месяцу |", "|---|---|---|---|---|---|---|"]
    for f in bsr["fields"]:
        for r in f.get("dry_by_month", []):
            L.append(f"| {f['name']} | {MONTH_RU[r['month'] - 1]} | {r['days']} | {r['smap_days']} | "
                     f"{r['smap_dry_share'] * 100:.0f} % | {r['gwettop_dry_share_same_days'] * 100:.0f} % | "
                     f"{num(r['gwettop_month_threshold'], 2)} |")
    L += planner_markdown(planner, rules, num)
    (OUT / "AUDIT_TABLES.md").write_text("\n".join(L) + "\n", encoding="utf-8")


PRIORITY_RU = {"max_income": "доход", "save_moisture": "влага", "restore_soil": "почва", "minimize_risk": "риск",
               "balanced": "баланс"}


def planner_markdown(pb: dict, rules, num) -> list[str]:
    """Раздел «Планировщик: дни без покрова» (docs/MODEL_AUDIT.md § 7)."""
    names = {v["id"]: v["name"]["ru"] for v in rules.model["default_variants"]}
    p0, p1 = pb["period"]
    L = ["", "## Планировщик: дни без покрова и индекс опасности эрозии по сценариям", "",
         f"Оба демо-поля, климатология {p0}–{p1}, `OFFLINE=1`. Покров: `{pb['canopy_start']}` → `{pb['canopy_end']}` "
         "(`erosion.planner`). Дни без покрова — дни бесснежного сезона вне периода покрова; exposure — доля дней "
         "сезона «без покрова, ветер и сухо». В балл модели **не входит**; вариант «а» ниже — только расчёт аудита: "
         "пятая оценка «эрозия» 1–5 по exposure (меньше — лучше), вес — половина веса почвы. План 4 года с "
         f"{START_YEAR} г., история — пшеница много лет подряд.", ""]
    for f in pb["fields"]:
        s = f["season"]
        L += [f"### {f['name']}", "",
              f"Бесснежный сезон {s['start']}–{s['end']} ({s['days']} дн., {s['n_years']} лет). Доля дней «ветер и "
              "сухо» по месяцам сезона: " + ", ".join(f"{MONTH_RU[m['month'] - 1]} {num(m['p_wind_dry'])}"
                                                    for m in s["months"]) + ".", "",
              "| Сценарий | Культуры | Дней без покрова в год | Опасных дней в год | exposure_index | По годам (культура: дни / опасные) |",
              "|---|---|---|---|---|---|"]
        for vid, x in f["variants"].items():
            L.append(f"| {names.get(vid, vid)} | {' → '.join(x['crops'])} | {num(x['bare_days_per_year'], 1)} | "
                     f"{num(x['risky_days_per_year'], 1)} | {num(x['exposure_index'], 3)} | "
                     + "; ".join(f"{c}: {b} / {num(rk, 1)}" for c, b, rk in x["per_year"]) + " |")
        L += ["", "Рейтинг по взвешенному баллу сейчас и при варианте «а» (балл сейчас → с эрозией):", "",
              "| Приоритет | Сейчас | Вариант «а» | Лучший меняется? | Баллы |", "|---|---|---|---|---|"]
        for pid, x in f["by_priority"].items():
            scores = "; ".join(f"{names.get(k, k)}: {num(v['weighted_now'])} → {num(v['weighted'])} "
                               f"(эрозия {num(v['erosion_score'], 1)})" for k, v in x["scores"].items())
            L.append(f"| {PRIORITY_RU.get(pid, pid)} | {' > '.join(names.get(k, k) for k in x['now'])} | "
                     f"{' > '.join(names.get(k, k) for k in x['option_a'])} | "
                     f"{'**да**' if x['now'][0] != x['option_a'][0] else 'нет'} | {scores} |")
        L += ["", "Чувствительность к границам периода покрова (дни без покрова в год / exposure; лучший сценарий "
                  "при варианте «а» по приоритетам):", "",
              "| Начало покрова | Конец покрова | В правилах | " + " | ".join(names.get(k, k) for k in f["variants"])
              + " | Лучший при «а» (доход / влага / почва / риск / баланс) |",
              "|---|---|---|" + "---|" * len(f["variants"]) + "---|"]
        for c in f["sensitivity"]:
            L.append(f"| {c['canopy_start']} | {c['canopy_end']} | {'да' if c['is_rule_value'] else ''} | "
                     + " | ".join(f"{num(c['bare_days'][k], 1)} / {num(c['exposure'][k], 3)}" for k in f["variants"])
                     + " | " + " / ".join(names.get(c["best_option_a"][p], c["best_option_a"][p])
                                          for p in ("max_income", "save_moisture", "restore_soil", "minimize_risk", "balanced"))
                     + " |")
        L.append("")
    return L


EVIDENCE_TITLES = {
    "literature": "1. Подтверждено научным или официальным источником",
    "agronomist_review": "2. Требует проверки агрономом (косвенная опора)",
    "preliminary": "3. Предварительное допущение (нет источника или параметр конструкции модели)",
    "definition": "Определения, тривиальные значения и величины, рассчитанные из данных",
}


def write_parameters(rules) -> None:
    """Реестр всех параметров по классам обоснованности — генерируется из YAML, не правится руками."""
    params = rules.all_params()
    L = ["# Реестр параметров модели по классам обоснованности", "",
         "Сгенерировано `scripts/audit_model.py` из `backend/app/rules/*.yaml`. Править нужно YAML, а не этот файл.", "",
         f"Всего {len(params)}: verified {sum(p.status == 'verified' for p in params)}, "
         f"assumption {sum(p.status == 'assumption' for p in params)}.", ""]
    for ev, title in EVIDENCE_TITLES.items():
        group = [p for p in params if p.evidence == ev]
        L += [f"## {title} — {len(group)}", "", "| Параметр | Значение | Статус | Источник | Обоснование |", "|---|---|---|---|---|"]
        for p in group:
            val = p.value if not isinstance(p.value, dict) else ", ".join(f"{k} {x}" for k, x in p.value.items())
            note = p.note.replace("|", "/")
            L.append(f"| `{p.path}` | {val} {p.unit} | {p.status} | {p.source_name.split(':')[0][:90]} | {note} |")
        L.append("")
    (OUT / "PARAMETERS.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
