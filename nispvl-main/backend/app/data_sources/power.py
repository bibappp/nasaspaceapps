"""NASA POWER Daily API: осадки, температура, модельная влажность почвы, ветер и снег.

Документация: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
Точка запроса — центроид поля. POWER отдаёт значение ячейки исходной сетки
(метеопараметры MERRA-2: 0,5° x 0,625°), поэтому запрос кэшируется по координатам,
округлённым до 0,01° (документация просит не запрашивать одну и ту же ячейку повторно).
"""
from __future__ import annotations

import hashlib
from datetime import date

from ..geometry import Field
from .base import DataSource, DataWarning, ProgressCallback, SourceError, http_client

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = [
    "PRECTOTCORR", "T2M", "T2M_MAX", "T2M_MIN", "GWETROOT", "GWETTOP",
    # «Часы голой почвы»: ветер (среднее и максимум за сутки, 2 и 10 м) и снег (доля ячейки, высота)
    "WS2M", "WS10M", "WS2M_MAX", "WS10M_MAX", "FRSNO", "SNODP",
]
FILL = -999.0
FIRST_DAY = date(1981, 1, 1)


async def fetch_point(lat: float, lon: float, start: date, end: date) -> dict:
    params = {
        "parameters": ",".join(PARAMETERS),
        "community": "AG",
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    async with http_client() as client:
        resp = await client.get(URL, params=params)
    if resp.status_code != 200:
        raise SourceError(f"POWER HTTP {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    try:
        series = body["properties"]["parameter"]
        dates = sorted(series[PARAMETERS[0]].keys())
    except (KeyError, TypeError) as exc:
        raise SourceError("POWER: unexpected response structure") from exc
    if not dates:
        raise SourceError("POWER: empty series")
    daily: dict[str, list] = {"date": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dates]}
    for p in PARAMETERS:
        values = series.get(p, {})
        daily[p] = [None if values.get(d, FILL) == FILL else values[d] for d in dates]
    coords = body.get("geometry", {}).get("coordinates", [lon, lat, None])
    header = body.get("header", {})
    return {
        "lat": lat,
        "lon": lon,
        "elevation_m": coords[2] if len(coords) > 2 else None,
        "api_version": header.get("api", {}).get("version"),
        "models": header.get("sources"),
        "units": {k: v.get("units") for k, v in body.get("parameters", {}).items()},
        "daily": daily,
    }


def parameters_tag() -> str:
    """Короткий отпечаток списка параметров: при его изменении меняется ключ кэша."""
    return hashlib.sha1(",".join(PARAMETERS).encode()).hexdigest()[:8]


class PowerSource(DataSource):
    id = "power"
    #: v2 — добавлены ветер (WS2M, WS10M, WS2M_MAX, WS10M_MAX) и снег (FRSNO, SNODP).
    #: Старые файлы кэша без этих рядов получают другой ключ и скачиваются заново.
    schema_version = 2

    def cache_parts(self, field: Field, start: date, end: date) -> dict:
        return {
            "params": parameters_tag(),
            "lat": round(field.centroid_lat, 2),
            "lon": round(field.centroid_lon, 2),
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

    async def _fetch_live(
        self, field: Field, start: date, end: date, progress: ProgressCallback | None = None
    ) -> dict:
        return await fetch_point(round(field.centroid_lat, 2), round(field.centroid_lon, 2), max(start, FIRST_DAY), end)

    def _fallback(self, field: Field) -> tuple[dict, DataWarning] | None:
        # Без климата модель не считается. Если POWER недоступен и кэша нет,
        # берём климат демо-поля и громко предупреждаем об этом в интерфейсе.
        demo = self.read_demo()
        if demo is None:
            return None
        return demo, DataWarning("climate_fallback_demo", self.id)
