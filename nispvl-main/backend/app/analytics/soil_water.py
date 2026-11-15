"""Водно-физические свойства почвы по данным SoilGrids.

Педотрансферные функции Saxton & Rawls (2006, SSSAJ 70:1569–1578, табл. 1):
по долям песка и глины и содержанию органического вещества оцениваются
влажность завядания (1500 кПа), наименьшая влагоёмкость (33 кПа) и полная влагоёмкость.
Диапазон доступной влаги (ДДВ, AWC) = НВ − ВЗ; суммируется по слоям до 1 м.
"""
from __future__ import annotations

VAN_BEMMELEN = 1.724  # органическое вещество = органический углерод x 1,724


def saxton_rawls(sand: float, clay: float, om_pct: float) -> dict[str, float]:
    """sand, clay — доли по массе (0–1); om_pct — органическое вещество, % по массе.

    Возвращает объёмные влажности (м³/м³): wp — завядание, fc — НВ, sat — насыщение.
    """
    s, c = min(max(sand, 0.0), 1.0), min(max(clay, 0.0), 0.6)
    om = min(max(om_pct, 0.0), 8.0)  # область применимости уравнений

    t1500 = -0.024 * s + 0.487 * c + 0.006 * om + 0.005 * s * om - 0.013 * c * om + 0.068 * s * c + 0.031
    wp = t1500 + (0.14 * t1500 - 0.02)

    t33 = -0.251 * s + 0.195 * c + 0.011 * om + 0.006 * s * om - 0.027 * c * om + 0.452 * s * c + 0.299
    fc = t33 + (1.283 * t33 * t33 - 0.374 * t33 - 0.015)

    ts33 = 0.278 * s + 0.034 * c + 0.022 * om - 0.018 * s * om - 0.027 * c * om - 0.584 * s * c + 0.078
    s33 = ts33 + (0.636 * ts33 - 0.107)
    sat = fc + s33 - 0.097 * s + 0.043
    return {"wp": round(wp, 4), "fc": round(fc, 4), "sat": round(sat, 4)}


def soil_summary(soil_data: dict, root_zone_cm: int = 100) -> dict | None:
    """Сводка по почве: слои, влагоёмкость метрового слоя, гумус пахотного слоя."""
    props = (soil_data or {}).get("properties") or {}
    need = ("sand", "clay", "soc")
    if not all(p in props for p in need):
        return None
    layers = []
    awc_mm = 0.0
    covered_cm = 0
    for label, d in props["sand"]["depths"].items():
        top, bottom = d["top_cm"], d["bottom_cm"]
        sand = d["mean"]
        clay = props["clay"]["depths"].get(label, {}).get("mean")
        soc = props["soc"]["depths"].get(label, {}).get("mean")
        if sand is None or clay is None or soc is None or top >= root_zone_cm:
            continue
        ph = (props.get("phh2o", {}).get("depths", {}).get(label) or {}).get("mean")
        om_pct = soc / 10 * VAN_BEMMELEN  # soc в г/кг -> % -> органическое вещество
        w = saxton_rawls(sand / 100, clay / 100, om_pct)
        thickness = min(bottom, root_zone_cm) - top
        layer_awc = max(0.0, w["fc"] - w["wp"]) * thickness * 10  # см -> мм
        awc_mm += layer_awc
        covered_cm += thickness
        layers.append(
            {
                "depth": label,
                "top_cm": top,
                "bottom_cm": bottom,
                "sand_pct": round(sand, 1),
                "clay_pct": round(clay, 1),
                "soc_g_kg": round(soc, 1),
                "humus_pct": round(om_pct, 2),
                "ph": None if ph is None else round(ph, 1),
                "wilting_point": w["wp"],
                "field_capacity": w["fc"],
                "saturation": w["sat"],
                "awc_mm": round(layer_awc, 1),
            }
        )
    if not layers or covered_cm == 0:
        return None
    if covered_cm < root_zone_cm:  # нижние слои недоступны — достраиваем по последнему
        awc_mm *= root_zone_cm / covered_cm
    top_layers = [layer for layer in layers if layer["bottom_cm"] <= 30]
    thickness = sum(layer["bottom_cm"] - layer["top_cm"] for layer in top_layers) or 1

    def wavg(key: str) -> float | None:
        vals = [(layer[key], layer["bottom_cm"] - layer["top_cm"]) for layer in top_layers if layer[key] is not None]
        return round(sum(v * t for v, t in vals) / sum(t for _, t in vals), 2) if vals else None

    return {
        "layers": layers,
        "awc_mm": round(awc_mm, 0),
        "root_zone_cm": root_zone_cm,
        "topsoil": {
            "depth_cm": thickness,
            "humus_pct": wavg("humus_pct"),
            "soc_g_kg": wavg("soc_g_kg"),
            "clay_pct": wavg("clay_pct"),
            "sand_pct": wavg("sand_pct"),
            "ph": wavg("ph"),
        },
        "texture_class": texture_class(wavg("sand_pct") or 0, wavg("clay_pct") or 0),
    }


def texture_class(sand_pct: float, clay_pct: float) -> str:
    """Упрощённый класс гранулометрического состава (ключ для перевода в интерфейсе)."""
    if clay_pct >= 40:
        return "clay"
    if clay_pct >= 27:
        return "clay_loam"
    if sand_pct >= 70 and clay_pct < 15:
        return "sandy"
    if sand_pct >= 50 and clay_pct < 20:
        return "sandy_loam"
    return "loam"
