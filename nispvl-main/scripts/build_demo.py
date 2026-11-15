#!/usr/bin/env python
"""Собирает данные демо-поля в data/demo/ — после этого демо работает без интернета.

Что сохраняется:
    field.json      контур, область, история (демо-сценарий), приоритет
    power.json           NASA POWER, суточный ряд с 1981 г. (осадки, температура, GWETTOP, ветер, снег)
    modis.json           MODIS MOD13Q1, сезон (DOY 129–273): ряд NDVI по полю и пиксельные растры
    modis_shoulder.json  MODIS MOD13Q1, весна и осень (DOY 81–113, 289–305) для «Часов голой почвы»
    soilgrids.json       ISRIC SoilGrids: почва по слоям до 1 м
    smap.json            SMAP SPL3SMP_E: влажность почвы в апреле–мае (нужен EARTHDATA_TOKEN)
    smap_season.json     SMAP SPL3SMP_E: апрель–октябрь для «Часов голой почвы» (нужен EARTHDATA_TOKEN)

Запуск (нужен интернет):
    cd backend && .venv/bin/python ../scripts/build_demo.py [--only power,modis,...] [--field kostanay] [--refresh]
    make demo ARGS="--only modis,modis_shoulder,smap_season --refresh"

Если какой-то источник недоступен, уже сохранённый файл не трогается.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.data_sources.registry import SOURCES
from app.geometry import parse_field
from app.services.analysis import MODIS_START, POWER_START, SMAP_START

# Демо-поле: два смежных участка пашни в Шортандинском районе Акмолинской области,
# между полевой дорогой (север) и ручьём (юг), ~9 км западнее п. Шортанды.
# Контур снят вручную по спутниковому снимку Esri World Imagery (следы уборки, границы полей),
# с отступом ~30 м внутрь от видимых границ. Это НЕ кадастровая граница.
DEMO_FIELD = {
    "id": "demo-akmola-shortandy",
    "name": {"ru": "Демо-поле, Шортандинский район", "kk": "Демо-егістік, Шортанды ауданы", "en": "Demo field, Shortandy district"},
    "region": "akmola",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [70.9186, 51.6916],
                [70.9465, 51.6935],
                [70.9475, 51.6808],
                [70.9300, 51.6781],
                [70.9138, 51.6802],
                [70.9186, 51.6916],
            ]
        ],
    },
    # Демо-СЦЕНАРИЙ из постановки задачи: «пшеница 10 лет подряд».
    # Фактическая история культур на этом поле нам неизвестна и не подтверждена.
    "history": [{"year": y, "crop": "wheat"} for y in range(2022, 2027)],
    "history_is_scenario": True,
    "history_note": {
        "ru": "История культур — учебный сценарий «пшеница много лет подряд». Что на самом деле сеяли на этом поле, не проверялось.",
        "kk": "Дақылдар тарихы — «қатарынан көп жыл бидай» оқу сценарийі. Бұл егістікке іс жүзінде не себілгені тексерілмеген.",
        "en": "Crop history is a training scenario (wheat for many years in a row). What was actually sown on this field has not been verified.",
    },
    "priority": "max_income",
    "horizon_years": 4,
    "contour_source": "Esri World Imagery, ручная оцифровка 12.11.2026",
}

# Второе демо-поле: пашня в Костанайском районе (~12 км восточнее Костаная, полосы обработки видны на снимке).
# Контур снят вручную по Esri World Imagery 13.11.2026 с отступом ~30 м; озеро у южной границы исключено.
KOSTANAY_FIELD = {
    "id": "demo-kostanay",
    "name": {"ru": "Демо-поле, Костанайский район", "kk": "Демо-егістік, Қостанай ауданы", "en": "Demo field, Kostanay district"},
    "region": "kostanay",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[63.9555, 53.0845], [63.9790, 53.0845], [63.9790, 53.0700], [63.9486, 53.0700], [63.9555, 53.0845]]],
    },
    "history": [{"year": 2022, "crop": "wheat"}, {"year": 2023, "crop": "wheat"}, {"year": 2024, "crop": "pea"},
                {"year": 2025, "crop": "wheat"}, {"year": 2026, "crop": "wheat"}],
    "history_is_scenario": True,
    "history_note": {
        "ru": "История культур — учебный сценарий (пшеница с одним годом гороха). Фактические посевы на этом поле не проверялись.",
        "kk": "Дақылдар тарихы — оқу сценарийі (бір жыл асбұршақпен бидай). Бұл егістіктегі нақты егістер тексерілмеген.",
        "en": "Crop history is a training scenario (wheat with one year of peas). Actual crops on this field have not been verified.",
    },
    "priority": "balanced",
    "horizon_years": 4,
    "contour_source": "Esri World Imagery, ручная оцифровка 13.11.2026",
}

FIELDS = {"shortandy": (DEMO_FIELD, None), "kostanay": (KOSTANAY_FIELD, "kostanay")}

PERIODS = {"power": POWER_START, "soilgrids": POWER_START, "modis": MODIS_START, "modis_shoulder": MODIS_START,
           "smap": SMAP_START, "smap_season": SMAP_START}


def progress_printer(name: str):
    def cb(done: int, total: int) -> None:
        if done == total or done % 10 == 0:
            print(f"  {name}: {done}/{total}", flush=True)

    return cb


async def build(key: str, wanted: list[str], refresh: bool) -> list[str]:
    spec, subdir = FIELDS[key]
    settings = get_settings()
    demo_dir = settings.demo_dir if subdir is None else settings.demo_dir / "fields" / subdir
    demo_dir.mkdir(parents=True, exist_ok=True)
    field = parse_field(spec["geometry"])
    record = {
        **spec,
        "area_ha": round(field.area_ha, 1),
        "centroid": {"lat": round(field.centroid_lat, 5), "lon": round(field.centroid_lon, 5)},
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (demo_dir / "field.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{key}] {record['area_ha']} га, центр {record['centroid']}")
    today = date.today()
    failed = []
    for sid in wanted:
        src = SOURCES[sid]
        if not src.enabled:
            print(f"[{key}] {sid}: пропущен — источник не настроен (для SMAP нужен EARTHDATA_TOKEN)")
            failed.append(sid)
            continue
        print(f"[{key}] {sid}: загрузка…", flush=True)
        try:
            if refresh:
                data = await src._fetch_live(field, PERIODS[sid], today, progress_printer(sid))
            else:
                # без --refresh берём кэш, если он есть (результат fetch: demo/cache/live)
                res = await src.fetch(field, PERIODS[sid], today, progress=progress_printer(sid))
                if res.origin not in ("live", "cache", "demo") or res.data is None:
                    raise RuntimeError(f"origin={res.origin}: {[w.code for w in res.warnings]}")
                data = dict(res.data)
        except Exception as exc:  # noqa: BLE001
            print(f"[{key}] {sid}: НЕ УДАЛОСЬ ({type(exc).__name__}: {str(exc)[:160]}); прежний файл оставлен как есть")
            failed.append(sid)
            continue
        data.pop("partial", None)
        data.pop("cached_at", None)
        out = {"cached_at": datetime.now(UTC).isoformat(timespec="seconds"), "demo": True, **data}
        path = demo_dir / f"{sid}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"[{key}] {sid}: сохранено {path.relative_to(settings.data_dir)}, {path.stat().st_size / 1024:.0f} КБ")
    return failed


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=",".join(PERIODS))
    parser.add_argument("--field", default="all", help="shortandy | kostanay | all")
    parser.add_argument("--refresh", action="store_true", help="скачать заново, не используя кэш")
    args = parser.parse_args()
    wanted = [s.strip() for s in args.only.split(",") if s.strip()]
    keys = list(FIELDS) if args.field == "all" else [args.field]
    failed = []
    for key in keys:
        failed += [f"{key}:{s}" for s in await build(key, wanted, args.refresh)]
    if failed:
        print("Не обновлены:", ", ".join(failed))
        sys.exit(1)
    print("Готово: демо-данные собраны.")


if __name__ == "__main__":
    asyncio.run(main())
