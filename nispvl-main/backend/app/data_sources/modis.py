"""MODIS MOD13Q1 (NDVI, 250 м, 16 дней) через ORNL DAAC TESViS/MODIS Web Service.

Документация: https://modis.ornl.gov/data/modis_webservice.html
Ограничения сервиса, проверенные на практике:
  * не более 10 композитных дат на один запрос ``/subset``;
  * окно не больше 100 км вверх/вниз и влево/вправо от центра;
  * ответ на один запрос занимает 30–50 секунд.
Поэтому запрашиваем только вегетационный сезон (10 композитов, DOY 129–273,
то есть с ~9 мая по ~30 сентября) — один запрос на год и на слой, параллельно.
Каждый запрос кэшируется отдельно: прошедшие годы скачиваются один раз.

Маска качества: слой ``250m_16_days_pixel_reliability`` (0 — хорошие данные,
1 — пригодные с оговорками, 2 — снег/лёд, 3 — облака). В расчёт идут пиксели 0 и 1.
Для каждого композита дополнительно сохраняются счётчики кодов качества по пикселям поля
(``reliability_counts``), доли снега (код 2) и облаков (код 3) по отдельности и квантили NDVI
по годным пикселям поля (``ndvi_q``) — их использует «Часы голой почвы».

``ModisShoulderSource`` (``modis_shoulder``) догружает композиты вне сезона: весну до появления
всходов и осень после уборки (DOY 81–305 без 129–273). Композиты MOD13Q1 идут с шагом 16 дней
от DOY 1, поэтому это DOY 81, 97, 113 и 289, 305 — два запроса на год и слой (каждый ≤ 10 дат).
"""
from __future__ import annotations

import asyncio
import math
from datetime import date

import httpx
import numpy as np
from shapely.geometry import Point

from .. import cache
from ..config import get_settings
from ..geometry import Field
from .base import DataSource, ProgressCallback, SourceError, http_client

BASE = "https://modis.ornl.gov/rst/api/v1"
PRODUCT = "MOD13Q1"
BAND_NDVI = "250m_16_days_NDVI"
BAND_REL = "250m_16_days_pixel_reliability"
SEASON_DOY = (129, 273)
#: весна до всходов и осень после уборки: DOY 81–305 за вычетом сезона SEASON_DOY
SHOULDER_DOY = (81, 305)
#: композиты MOD13Q1 начинаются в DOY 1, 17, 33, … (шаг 16 дней), каждый покрывает 16 дней
COMPOSITE_STEP = 16
COMPOSITE_DOYS = tuple(range(1, 366, COMPOSITE_STEP))
#: ограничение сервиса ORNL: не больше 10 композитных дат в одном запросе /subset
MAX_DATES_PER_REQUEST = 10
#: уровни квантилей NDVI по годным пикселям поля, которые сохраняются для каждого композита
QUANTILE_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
RELIABILITY_CODES = (-1, 0, 1, 2, 3)  # -1 — нет данных (fill), 0–3 — см. выше
SNOW_CODE, CLOUD_CODE = 2, 3
FIRST_YEAR = 2000
SIN_RADIUS = 6371007.181  # радиус сферы синусоидальной проекции MODIS, м
GOOD_RELIABILITY = (0, 1)
RASTER_YEARS = 6  # за сколько последних сезонов хранить пиксельные растры для карты
REQUEST_CACHE = "modis_requests"


def sin_to_lonlat(x: float, y: float) -> tuple[float, float]:
    lat = y / SIN_RADIUS
    lon = x / (SIN_RADIUS * math.cos(lat))
    return math.degrees(lon), math.degrees(lat)


def pixel_center(grid: dict, row: int, col: int) -> tuple[float, float]:
    x = grid["xllcorner"] + (col + 0.5) * grid["cellsize"]
    y = grid["yllcorner"] + (grid["nrows"] - row - 0.5) * grid["cellsize"]
    return sin_to_lonlat(x, y)


def pixel_polygon(grid: dict, row: int, col: int) -> list[list[float]]:
    """Углы пикселя в lon/lat (замкнутое кольцо GeoJSON)."""
    cs = grid["cellsize"]
    x0 = grid["xllcorner"] + col * cs
    y1 = grid["yllcorner"] + (grid["nrows"] - row) * cs
    corners = [(x0, y1), (x0 + cs, y1), (x0 + cs, y1 - cs), (x0, y1 - cs), (x0, y1)]
    return [[round(v, 6) for v in sin_to_lonlat(x, y)] for x, y in corners]


def field_mask(field: Field, grid: dict) -> list[int]:
    """1 — центр пикселя внутри контура поля. Если таких нет, берём ближайший к центроиду."""
    mask: list[int] = []
    best, best_d = 0, float("inf")
    for r in range(grid["nrows"]):
        for c in range(grid["ncols"]):
            lon, lat = pixel_center(grid, r, c)
            inside = field.polygon.contains(Point(lon, lat))
            mask.append(1 if inside else 0)
            d = (lon - field.centroid_lon) ** 2 + (lat - field.centroid_lat) ** 2
            if d < best_d:
                best, best_d = len(mask) - 1, d
    if not any(mask):
        mask[best] = 1
    return mask


def composite_chunks(doys: list[int] | tuple[int, ...], max_dates: int = MAX_DATES_PER_REQUEST) -> list[tuple[int, int]]:
    """Окна запросов ``(первый DOY, последний DOY)``: подряд идущие композиты, не больше ``max_dates`` в окне."""
    runs: list[list[int]] = []
    for d in sorted(set(doys)):
        if runs and d - runs[-1][-1] == COMPOSITE_STEP and len(runs[-1]) < max_dates:
            runs[-1].append(d)
        else:
            runs.append([d])
    return [(r[0], r[-1]) for r in runs]


def shoulder_windows() -> tuple[tuple[int, int], ...]:
    doys = [d for d in COMPOSITE_DOYS
            if SHOULDER_DOY[0] <= d <= SHOULDER_DOY[1] and not SEASON_DOY[0] <= d <= SEASON_DOY[1]]
    return tuple(composite_chunks(doys))


def n_composites(window: tuple[int, int]) -> int:
    return sum(window[0] <= d <= window[1] for d in COMPOSITE_DOYS)


def composite_stats(ndvi: list[int], rel: list[int], mask: list[int], scale: float) -> tuple[dict, list[int | None]]:
    """Сводка композита по пикселям поля и маскированный растр (None — пиксель не годен)."""
    masked = [v if (q in GOOD_RELIABILITY and -2000 <= v <= 10000) else None for v, q in zip(ndvi, rel)]
    in_field = [i for i, m in enumerate(mask) if m]
    n_field = len(in_field)
    vals = [masked[i] * scale for i in in_field if masked[i] is not None]
    counts = {str(c): 0 for c in RELIABILITY_CODES}
    for i in in_field:
        code = int(rel[i])
        counts[str(code if code in RELIABILITY_CODES else -1)] += 1
    stats = {
        "ndvi": round(sum(vals) / len(vals), 4) if vals else None,
        "valid_fraction": round(len(vals) / n_field, 3),
        "snow_fraction": round(counts[str(SNOW_CODE)] / n_field, 3),
        "cloud_fraction": round(counts[str(CLOUD_CODE)] / n_field, 3),
        "reliability_counts": counts,
        "ndvi_q": [round(float(q), 4) for q in np.quantile(vals, QUANTILE_LEVELS)] if vals else None,
    }
    return stats, masked


async def _request_subset(
    client: httpx.AsyncClient, lat: float, lon: float, km_ab: int, km_lr: int, year: int, band: str,
    window: tuple[int, int] = SEASON_DOY,
) -> dict:
    if n_composites(window) > MAX_DATES_PER_REQUEST:
        raise ValueError(f"MODIS window {window} has more than {MAX_DATES_PER_REQUEST} composite dates")
    today = date.today()
    key_parts: dict = {"lat": lat, "lon": lon, "km_ab": km_ab, "km_lr": km_lr, "year": year, "band": band}
    if tuple(window) != SEASON_DOY:
        # окно сезона — прежний ключ без DOY, чтобы уже скачанные ответы оставались в силе
        key_parts["doy"] = f"{window[0]:03d}-{window[1]:03d}"
    if year >= today.year - 1:
        # свежие композиты ещё появляются и переобрабатываются: обновляем раз в месяц
        key_parts["stamp"] = today.strftime("%Y-%m")
    key = cache.make_key(REQUEST_CACHE, **key_parts)
    hit = cache.read(REQUEST_CACHE, key)
    if hit is not None:
        return hit
    params = {
        "latitude": lat,
        "longitude": lon,
        "band": band,
        "startDate": f"A{year}{window[0]:03d}",
        "endDate": f"A{year}{window[1]:03d}",
        "kmAboveBelow": km_ab,
        "kmLeftRight": km_lr,
    }
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.get(f"{BASE}/{PRODUCT}/subset", params=params, headers={"Accept": "application/json"})
            if resp.status_code == 200:
                body = resp.json()
                data = {
                    "grid": {
                        "xllcorner": float(body["xllcorner"]),
                        "yllcorner": float(body["yllcorner"]),
                        "cellsize": float(body["cellsize"]),
                        "nrows": int(body["nrows"]),
                        "ncols": int(body["ncols"]),
                    },
                    "scale": float(body.get("scale") or 1) if band == BAND_NDVI else 1.0,
                    "subset": [{"date": s["calendar_date"], "data": s["data"]} for s in body.get("subset", [])],
                }
                cache.write(REQUEST_CACHE, key, data)
                return data
            if resp.status_code in (400, 404) and year >= today.year:
                # сезон текущего года ещё не начался — данных нет, это не ошибка
                return {"grid": None, "scale": 1.0, "subset": []}
            last_exc = SourceError(f"MODIS HTTP {resp.status_code}: {resp.text[:160]}")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            last_exc = exc
        await asyncio.sleep(2 * (attempt + 1))
    raise SourceError(f"MODIS request failed for {year}/{band}/{window}: {last_exc!r}")


class ModisSource(DataSource):
    """Сезон вегетации: 10 композитов DOY 129–273, один запрос на год и слой."""

    id = "modis"
    #: v2 — у композитов появились reliability_counts, snow_fraction, cloud_fraction и ndvi_q
    schema_version = 2
    windows: tuple[tuple[int, int], ...] = (SEASON_DOY,)
    #: за сколько последних лет хранить пиксельные растры для карты (0 — не хранить)
    raster_years = RASTER_YEARS

    def cache_parts(self, field: Field, start: date, end: date) -> dict:
        return {"geometry": field.canonical(), "start_year": start.year, "end": end.strftime("%Y-%m")}

    def describe_windows(self) -> list[int] | list[list[int]]:
        return list(self.windows[0]) if len(self.windows) == 1 else [list(w) for w in self.windows]

    async def _fetch_live(
        self, field: Field, start: date, end: date, progress: ProgressCallback | None = None
    ) -> dict:
        settings = get_settings()
        # центр окна — центр bbox (а не центроид): запрос слоя карты по тому же bbox
        # попадает в уже сохранённые ответы
        minx, miny, maxx, maxy = field.bbox
        lat, lon = round((miny + maxy) / 2, 4), round((minx + maxx) / 2, 4)
        half_ns, half_ew = field.half_extent_km()
        km_ab, km_lr = max(1, math.ceil(half_ns)), max(1, math.ceil(half_ew))
        if km_ab > 100 or km_lr > 100:
            raise SourceError("field is larger than the 100 km window supported by the MODIS web service")
        years = list(range(max(start.year, FIRST_YEAR), end.year + 1))
        jobs = [(y, w, b) for y in years for w in self.windows for b in (BAND_NDVI, BAND_REL)]
        total, done = len(jobs), 0
        sem = asyncio.Semaphore(settings.modis_concurrency)
        results: dict[tuple[int, tuple[int, int], str], dict] = {}
        failed: set[int] = set()

        async with http_client(timeout=settings.modis_timeout_s) as client:

            async def run(year: int, window: tuple[int, int], band: str) -> None:
                nonlocal done
                async with sem:
                    try:
                        results[(year, window, band)] = await _request_subset(
                            client, lat, lon, km_ab, km_lr, year, band, window)
                    except SourceError:
                        failed.add(year)
                    done += 1
                    if progress:
                        progress(done, total)

            await asyncio.gather(*(run(y, w, b) for y, w, b in jobs))

        ok_years = [y for y in years if y not in failed]
        if len(ok_years) < max(3, len(years) // 2):
            raise SourceError(f"MODIS: only {len(ok_years)} of {len(years)} years could be downloaded")

        grid = next((r["grid"] for r in results.values() if r.get("grid")), None)
        if grid is None:
            raise SourceError("MODIS: empty response")
        mask = field_mask(field, grid)
        n_field = sum(mask)
        raster_from = end.year - self.raster_years + 1 if self.raster_years else end.year + 1

        series: list[dict] = []
        rasters: dict[str, list[int | None]] = {}
        for year in ok_years:
            for window in self.windows:
                ndvi_req, rel_req = results[(year, window, BAND_NDVI)], results[(year, window, BAND_REL)]
                rel_by_date = {s["date"]: s["data"] for s in rel_req["subset"]}
                scale = ndvi_req["scale"]
                for s in ndvi_req["subset"]:
                    rel = rel_by_date.get(s["date"])
                    if rel is None or len(rel) != len(s["data"]) or len(mask) != len(s["data"]):
                        continue
                    stats, masked = composite_stats(s["data"], rel, mask, scale)
                    series.append({"date": s["date"], **stats})
                    if year >= raster_from:
                        rasters[s["date"]] = masked
        series.sort(key=lambda r: r["date"])
        return {
            "product": f"{PRODUCT}.061",
            "lat": lat,
            "lon": lon,
            "season_doy": self.describe_windows(),
            "grid": grid,
            "field_mask": mask,
            "n_field_pixels": n_field,
            "ndvi_scale": 0.0001,
            "quantile_levels": list(QUANTILE_LEVELS),
            "series": series,
            "rasters": rasters,
            "missing_years": sorted(failed),
            "partial": bool(failed),
        }


class ModisShoulderSource(ModisSource):
    """Весна до всходов и осень после уборки (DOY 81–113 и 289–305) — для «Часов голой почвы».

    Тот же сервис, кэш запросов и фоновая задача, что у ``ModisSource``; растры для карты не хранятся.
    """

    id = "modis_shoulder"
    schema_version = 1
    windows = shoulder_windows()
    raster_years = 0
