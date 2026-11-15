#!/usr/bin/env python
"""Заранее скачивает ряд SMAP (апрель–май, с 2015 г.) для поля и кладёт его в кэш.

SMAP — самый медленный источник (~730 суточных файлов на поле). Скрипт удобно
запустить заранее, например для полей хозяйства перед демонстрацией.

    cd backend && .venv/bin/python ../scripts/prefetch_smap.py                # демо-поле
    cd backend && .venv/bin/python ../scripts/prefetch_smap.py field.geojson  # своё поле

Нужен EARTHDATA_TOKEN (или EARTHDATA_USERNAME/PASSWORD) в .env.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.data_sources.base import demo_field_record
from app.data_sources.registry import SOURCES
from app.geometry import parse_field
from app.services.analysis import SMAP_START


async def main() -> None:
    if len(sys.argv) > 1:
        geometry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    else:
        rec = demo_field_record()
        if rec is None:
            raise SystemExit("нет data/demo/field.json и не указан файл с контуром")
        geometry = rec["geometry"]
    if not get_settings().has_earthdata:
        raise SystemExit("не задан EARTHDATA_TOKEN (см. .env.example)")
    field = parse_field(geometry)
    src = SOURCES["smap"]

    def progress(done: int, total: int) -> None:
        if done == total or done % 25 == 0:
            print(f"  {done}/{total}", flush=True)

    # _fetch_live + запись в общий кэш, чтобы сайт взял данные оттуда
    from app import cache

    data = await src._fetch_live(field, SMAP_START, date.today(), progress)
    data.pop("partial", None)
    path = cache.write(src.id, src.cache_key(field, SMAP_START, date.today()), data)
    print(f"SMAP: {len(data['daily'])} дней с данными из {data['n_files']} файлов, ошибок {data['n_failed']} -> {path}")


if __name__ == "__main__":
    asyncio.run(main())
