"""Объяснения простыми словами: шаблоны + сработавшие правила. Без LLM."""
from __future__ import annotations

import re
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

import yaml

from .rules import Rules

LANGS = ("ru", "kk", "en")
TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "locales" / "explain.yaml"
NBSP = " "


@lru_cache
def templates() -> dict[str, dict[str, str]]:
    return yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8"))


def fmt_int(value: float) -> str:
    """Целое с неразрывными пробелами между разрядами: 1 234 567."""
    return f"{round(value):,}".replace(",", NBSP).replace("-", "−")


# Десятичный разделитель для текущего документа: запятая (ru/kk) или точка (en, ставит построитель PDF).
DECIMAL_POINT: ContextVar[bool] = ContextVar("decimal_point", default=False)


def fmt_num(value: float, digits: int = 1) -> str:
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
    return (text if DECIMAL_POINT.get() else text.replace(".", ",")).replace("-", "−")


_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")


def _localize(lang: str, params: dict) -> dict:
    """Числа форматируются с десятичной запятой (ru/kk); в английском тексте — точка."""
    if lang != "en":
        return params
    return {k: _DECIMAL_COMMA.sub(".", v) if isinstance(v, str) else v for k, v in params.items()}


def _render(code: str, params_by_lang: dict[str, dict]) -> dict:
    tpl = templates()[code]
    return {"code": code, **{lang: tpl[lang].format(**_localize(lang, params_by_lang[lang])) for lang in LANGS}}


def years_phrase(n: int) -> dict[str, str]:
    """«4 года», «5 лет» / «4 жыл» — число лет с правильным окончанием."""
    if n % 10 == 1 and n % 100 != 11:
        word = "год"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "года"
    else:
        word = "лет"
    return {"ru": f"{n}{NBSP}{word}", "kk": f"{n}{NBSP}жыл", "en": f"{n}{NBSP}{'year' if n == 1 else 'years'}"}


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def explain_variant(rules: Rules, variant: dict, comparison: dict, baseline: dict | None) -> list[dict]:
    """Список предложений {code, ru, kk} для одного варианта."""
    out: list[dict] = []
    years = variant["years"]
    n = len(years)

    def names(crop_id: str) -> dict[str, str]:
        return {lang: rules.crop_name(crop_id, lang, short=True) for lang in LANGS}

    def both(**common) -> dict[str, dict]:
        """Параметры шаблона: значения-словари {ru, kk} раскладываются по языкам."""
        return {
            lang: {k: (v[lang] if isinstance(v, dict) else v) for k, v in common.items()} for lang in LANGS
        }

    # --- предшественники и монокультура (по одному предложению на правило) ---
    seen_rules: set[str] = set()
    mono_reported = False
    for i, y in enumerate(years):
        crop, prev = y["crop"], y["predecessor"]
        rule_id = y["predecessor_rule"]
        if rule_id and rule_id not in seen_rules and prev and y["predecessor_effect_pct"]:
            seen_rules.add(rule_id)
            pct = y["predecessor_effect_pct"]
            if pct > 0 and rules.group(prev) == "legume":
                code = "legume_then_cereal"
            elif pct > 0:
                code = "break_crop"
            else:
                code = "bad_predecessor"
            out.append(_render(code, both(prev=names(prev), crop=names(crop), year=y["year"], pct=fmt_num(abs(pct), 0))))
        if y["monoculture"] and not mono_reported:
            mono_reported = True
            nm = names(crop)
            out.append(
                _render(
                    "monoculture",
                    both(
                        crop_cap={lang: _cap(nm[lang]) for lang in LANGS},
                        run=y["monoculture_run"],
                        year=y["year"],
                        pct=fmt_num(abs(y["monoculture_penalty_pct"]), 0),
                    ),
                )
            )
        if y["group"] == "fallow":
            humus = fmt_num(abs(y["humus_t_ha"]), 1)
            if i + 1 < n and years[i + 1]["after_fallow"]:
                nxt = years[i + 1]
                gain_mm = nxt["stock_mm"] - comparison["conditions"]["stock_normal"]
                gain_pct = 100 * gain_mm / comparison["conditions"]["stock_normal"] if comparison["conditions"]["stock_normal"] else 0
                out.append(
                    _render(
                        "fallow_next",
                        both(year=y["year"], humus=humus, next=names(nxt["crop"]), gain=fmt_num(gain_pct, 0), mm=fmt_num(gain_mm, 0)),
                    )
                )
            else:
                out.append(_render("fallow_last", both(year=y["year"], humus=humus)))

    # --- засуха: кто теряет меньше, кто больше ---------------------------------
    loss_by_crop: dict[str, float] = {}
    for y in years:
        if y["group"] != "fallow" and y["yield_t_ha"] > 0:
            loss_by_crop[y["crop"]] = max(loss_by_crop.get(y["crop"], 0.0), y["yield_loss_dry_pct"])
    dry_year = comparison["conditions"]["dry_year"]
    if len(loss_by_crop) >= 2:
        best = min(loss_by_crop, key=loss_by_crop.get)  # type: ignore[arg-type]
        worst = max(loss_by_crop, key=loss_by_crop.get)  # type: ignore[arg-type]
        if loss_by_crop[worst] - loss_by_crop[best] >= 1:
            out.append(
                _render(
                    "drought_compare",
                    both(
                        dry_year=dry_year,
                        best=names(best),
                        best_pct=fmt_num(loss_by_crop[best], 0),
                        worst=names(worst),
                        worst_pct=fmt_num(loss_by_crop[worst], 0),
                    ),
                )
            )
    elif len(loss_by_crop) == 1:
        (crop, pct), = loss_by_crop.items()
        out.append(_render("drought_single", both(dry_year=dry_year, crop=names(crop), pct=fmt_num(pct, 0))))

    # --- влага --------------------------------------------------------------------
    cropped = [y for y in years if y["group"] != "fallow"]
    if cropped:
        thirsty = max(cropped, key=lambda y: y["water_deficit_mm"])
        if thirsty["water_deficit_mm"] > 0:
            out.append(
                _render(
                    "water_deficit",
                    both(
                        crop=names(thirsty["crop"]),
                        need=fmt_num(thirsty["water_need_mm"], 0),
                        water=fmt_num(thirsty["water_available_mm"], 0),
                    ),
                )
            )

    # --- почва --------------------------------------------------------------------
    totals = variant["totals"]
    if totals["nitrogen_kg_ha"] > 0:
        out.append(_render("nitrogen_positive", both(n_years=years_phrase(n), kg=fmt_num(totals["nitrogen_kg_ha"], 0))))
    elif totals["nitrogen_kg_ha"] < 0:
        out.append(_render("nitrogen_negative", both(n_years=years_phrase(n), kg=fmt_num(abs(totals["nitrogen_kg_ha"]), 0))))
    if totals["humus_t_ha"]:
        out.append(_render("humus", both(n_years=years_phrase(n), t=fmt_num(totals["humus_t_ha"], 1))))

    # --- доход --------------------------------------------------------------------
    income = totals["income_kzt_ha"]
    if baseline is None or baseline["id"] == variant["id"]:
        out.append(_render("income_base", both(n_years=years_phrase(n), income=fmt_int(income))))
    else:
        diff = income - baseline["totals"]["income_kzt_ha"]
        base_name = baseline.get("name") or {lang: baseline["id"] for lang in LANGS}
        code = "income_more" if diff >= 0 else "income_less"
        out.append(_render(code, both(n_years=years_phrase(n), income=fmt_int(income), diff=fmt_int(abs(diff)), base=base_name)))

    # --- приоритет и оговорка о допущениях ------------------------------------------
    if variant.get("fits_priority"):
        priority = rules.model["priorities"][comparison["priority"]]["name"]
        out.append(_render("fits_priority", both(priority=priority, score=fmt_num(variant["weighted_score"], 2))))
    if variant.get("assumptions_used"):
        out.append(
            _render("assumptions", both(n_assumptions=variant["assumptions_used"], n_params=variant["params_used"]))
        )
    return out


def attach_explanations(rules: Rules, comparison: dict) -> dict:
    variants = comparison["variants"]
    baseline = next((v for v in variants if tuple(v["crops"]) and set(v["crops"]) == {"wheat"}), variants[0])
    comparison["baseline_variant_id"] = baseline["id"]
    for v in variants:
        v["explanation"] = explain_variant(rules, v, comparison, baseline)
    return comparison
