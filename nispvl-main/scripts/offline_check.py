#!/usr/bin/env python
"""Проверка: демо проходит путь «анализ -> сравнение -> слои -> мониторинг и риски -> часы голой почвы -> PDF/XLSX»
без сети.

    cd backend && OFFLINE=1 .venv/bin/python ../scripts/offline_check.py

В режиме OFFLINE=1 бэкенд не делает ни одного внешнего запроса; дополнительно
сетевые вызовы httpx в этом скрипте запрещены, чтобы случайный запрос упал с ошибкой.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["OFFLINE"] = "1"

import httpx

from app.data_sources.base import demo_field_record, demo_field_records
from app.report.pdf import build_report
from app.report.xlsx import build_workbook
from app.schemas import CompareRequest
from app.services import layers
from app.services import monitoring as mon
from app.services.bare_soil import bare_soil
from app.services.comparison import run_compare
from app.services.report_data import gather


async def _no_network(*args, **kwargs):
    raise RuntimeError("network access attempted in offline check")


httpx.AsyncClient.send = _no_network  # type: ignore[method-assign]


async def main() -> None:
    demo = demo_field_record()
    if demo is None:
        raise SystemExit("data/demo/field.json не найден: сначала запустите scripts/build_demo.py")
    req = CompareRequest(
        geometry=demo["geometry"], region=demo["region"], history=demo["history"],
        priority=demo["priority"], horizon_years=demo["horizon_years"],
    )
    comparison, analysis = await run_compare(req)
    a = analysis.response
    origins = {s["source"]: s["origin"] for s in a["sources"]}
    print("Источники:", origins)
    bad = {k: v for k, v in origins.items() if v != "demo"}
    if bad:
        raise SystemExit(f"не все источники взяты из демо-данных: {bad}")
    d = a["drought"]
    print(f"Засушливые годы {d['window']['from']}–{d['window']['to']}: {d['dry_years']} "
          f"(доля {d['share']:.0%}, примерно каждый {d['every_nth']}-й год)")
    t = a["ndvi"]["trend"]
    print(f"Тренд NDVI {t['from_year']}–{t['to_year']}: {t['label']}, наклон {t['slope_per_year']}/год, p = {t['p_value']}")
    print(f"Влага: основа {a['soil_moisture']['basis']}, обычный запас {a['soil_moisture']['stock']['normal_stock_mm']} мм")
    base = next(v for v in comparison["variants"] if v["id"] == comparison["baseline_variant_id"])
    for v in comparison["variants"]:
        diff = (v["totals"]["income_kzt_ha"] / base["totals"]["income_kzt_ha"] - 1) * 100 if base["totals"]["income_kzt_ha"] > 0 else float("nan")
        print(f"  {'★' if v['fits_priority'] else ' '} {v['id']:22s} доход {v['totals']['income_kzt_ha']:>8} тг/га "
              f"({diff:+.0f} % к монокультуре), балл {v['weighted_score']}, без покрова {v['bare_days_per_year']} дн./год, "
              f"exposure {v['exposure_index']}")
    season = comparison["bare_soil_season"]
    print(f"Планировщик: бесснежный сезон {season['start']}–{season['end']} ({season['days']} дн., {season['n_years']} лет), "
          f"статус {season['status']}")
    if season["status"] != "ok" or any(v["bare_days_per_year"] is None or v["exposure_index"] is None
                                       for v in comparison["variants"]):
        raise SystemExit("планировщик: нет дней без покрова или exposure на демо-данных")
    if any(v["bare_soil"]["in_score"] for v in comparison["variants"]):
        raise SystemExit("планировщик: дни без покрова не должны входить в балл (MODEL_AUDIT.md § 7)")
    for kind in layers.KINDS:
        layer = await layers.build_layer(kind, tuple(a["field"]["bbox"]), None)
        print(f"Слой {kind}: {len(layer['features'])} ячеек, источник {layer['meta']['source']}, дата {layer['meta']['date']}")
    m = await mon.monitoring(demo["geometry"], demo["region"], None, None)
    print(f"Мониторинг {m['range']['start']}…{m['range']['end']}: {len(m['climate']['months'])} мес., "
          f"{len(m['ndvi']['composites'])} композитов NDVI, {len(m['soil_moisture']['days'])} дней SMAP")
    r = await mon.risk(demo["geometry"], demo["region"])
    print(f"Риски сезона {r['latest_season']}: итог {r['overall']}; " + ", ".join(f"{i['id']}={i['level']}" for i in r["items"]))
    s = await mon.suitability(demo["geometry"], demo["region"], demo["history"])
    print("Пригодность: " + ", ".join(f"{c['crop']}={c['category']}" for c in s["crops"]))
    for rec in demo_field_records():
        b = await bare_soil(0, rec["geometry"], None, None, region=rec["region"])
        months = [m for y in b["years"] for m in y["months"]]
        count = {st: sum(m["state"] == st for m in months) for st in ("ok", "snow", "missing")}
        pending = sum(m["missing_reason"] == "ndvi_pending_fetch" for m in months)
        print(f"Часы голой почвы, {rec['id']} {b['period']['start_year']}–{b['period']['end_year']}: status {b['status']}, "
              f"месяцев ok {count['ok']}, снег {count['snow']}, нет данных {count['missing']} "
              f"(ждут MODIS межсезонья {pending}); самые опасные месяцы {b['headline']['top_months']}")
        he = b["effective_thresholds"]["harvest_end"]
        wins = [(w["start"], w["end"]) for w in b["cover_crop_windows"]]
        print(f"  окна покровных культур (после уборки {he}): {wins or 'нет — ' + b['cover_crop_note']['reason']}")
        if any(w[0] < he for w in wins) or (not wins and not b["cover_crop_note"]):
            raise SystemExit(f"Окно покровной культуры до уборки или без объяснения: {rec['id']}")
        if b["status"] in ("missing", "loading") or not count["ok"]:
            raise SystemExit(f"«Часы голой почвы» не посчитаны для {rec['id']}: {[w['code'] for w in b['warnings']]}")
        if any(m["state"] == "missing" and m["exposure"] is not None for m in months):
            raise SystemExit("месяц без данных получил число exposure")
    data = await gather(req, {"name": "offline-check"})
    for lang in ("ru", "kk", "en"):
        pdf = build_report(data, lang=lang)
        xlsx = build_workbook(data, lang=lang)
        print(f"PDF {lang}: {len(pdf) // 1024} КБ, XLSX {lang}: {len(xlsx) // 1024} КБ")
    print("OK: демо работает без сети")


if __name__ == "__main__":
    asyncio.run(main())
