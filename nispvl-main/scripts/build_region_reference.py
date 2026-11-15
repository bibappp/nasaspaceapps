#!/usr/bin/env python
"""Опорные осадки областей из NASA POWER -> backend/app/rules/regions.yaml.

Для каждой области берутся точки ``reference_points`` из regions.yaml. В каждой точке
считается медиана суммы осадков за сезон (май–август) за последние N полных лет
(N = drought.window_years из model.yaml), затем значения точек усредняются.

Запуск (нужен интернет):
    cd backend && .venv/bin/python ../scripts/build_region_reference.py
"""
from __future__ import annotations

import asyncio
import re
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import cache
from app.analytics import climate
from app.data_sources import power
from app.model.rules import RULES_DIR, load_rules


async def point_series(lat: float, lon: float, end: date) -> dict:
    key = cache.make_key("power_points", lat=lat, lon=lon, end=end.strftime("%Y-%m"))
    hit = cache.read("power_points", key)
    if hit is None:
        hit = await power.fetch_point(lat, lon, power.FIRST_DAY, end)
        cache.write("power_points", key, hit)
    return hit


async def main() -> None:
    rules = load_rules()
    months = rules.model["season"]["months"]
    window = int(rules.model["drought"]["window_years"])
    today = date.today()
    path = RULES_DIR / "regions.yaml"
    text = path.read_text(encoding="utf-8")

    for rid, region in rules.regions.items():
        medians, period = [], None
        for pt in region["reference_points"]:
            data = await point_series(pt["lat"], pt["lon"], today)
            season = climate.season_precip_by_year(climate.daily_frame(data), months)
            years = sorted(season)[-window:]
            period = (years[0], years[-1])
            medians.append(statistics.median(season[y] for y in years))
            print(f"  {rid:18s} {pt['name']:16s} медиана {medians[-1]:6.1f} мм ({years[0]}–{years[-1]})")
        value = round(sum(medians) / len(medians), 1)
        names = ", ".join(p["name"] for p in region["reference_points"])
        note = (
            f"Среднее по {len(medians)} точкам ({names}) медианы осадков за май–август "
            f"{period[0]}–{period[1]} гг.; значения по точкам: "
            + ", ".join(f"{m:.0f}" for m in medians)
            + f" мм. Рассчитано {today.isoformat()}"
        )
        line = (
            "    reference_season_precip_mm:\n"
            f'      {{value: {value}, unit: "мм", source: nasa_power, status: verified, note: "{note}"}}\n'
        )
        # заменяем блок reference_season_precip_mm внутри секции нужной области
        pattern = re.compile(
            rf"(\n  {re.escape(rid)}:\n(?:(?!\n  \w+:\n).)*?)    reference_season_precip_mm:\n      \{{[^\n]*\}}\n",
            re.DOTALL,
        )
        text, count = pattern.subn(lambda m: m.group(1) + line, text, count=1)
        if count != 1:
            raise SystemExit(f"не удалось обновить regions.yaml для области {rid}")
        print(f"{rid}: опорные осадки сезона = {value} мм")
    path.write_text(text, encoding="utf-8")
    load_rules()  # проверка, что файл остался корректным
    print("regions.yaml обновлён")


if __name__ == "__main__":
    asyncio.run(main())
