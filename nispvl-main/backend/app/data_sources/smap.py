"""SMAP SPL3SMP_E (влажность верхних ~5 см почвы, сетка 9 км, с 31.03.2015).

Суточный файл продукта — глобальный, ~650 МБ. Чтобы не скачивать его целиком,
берём только окно 3x3 ячейки вокруг поля через облачный OPeNDAP NASA
(``https://opendap.earthdata.nasa.gov``, ответ в CSV, ~3 с на файл).

Нужна авторизация NASA Earthdata (https://urs.earthdata.nasa.gov):
  * ``EARTHDATA_TOKEN`` — токен из профиля Earthdata (рекомендуется), или
  * ``EARTHDATA_USERNAME`` + ``EARTHDATA_PASSWORD`` — токен будет получен через ``earthaccess``.

Имена файлов (гранул) берём из открытого каталога CMR. Запрашиваются только
предпосевные месяцы (апрель–май). В расчёт идут измерения с признаком
«рекомендуемое качество» (бит 0 флага ``retrieval_qual_flag`` равен 0);
мёрзлая почва и снег этим флагом отсекаются.

``SmapSeasonSource`` (``smap_season``) — тот же источник за апрель–октябрь, для «Часов голой почвы»:
суточная влажность верхнего слоя в течение всего бесснежного периода. Ответы OPeNDAP кэшируются
по грануле, поэтому апрель–май, уже скачанные источником ``smap``, повторно не запрашиваются.
"""
from __future__ import annotations

import asyncio
import calendar
import math
from datetime import date

import httpx

from .. import cache
from ..config import get_settings
from ..geometry import Field
from .base import DataSource, ProgressCallback, SourceError, SourceNotConfigured, http_client

COLLECTION = "C2938664763-NSIDC_CPRD"  # SPL3SMP_E v006 (проверено в CMR)
PRODUCT = "SPL3SMP_E.006"
CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
OPENDAP = f"https://opendap.earthdata.nasa.gov/collections/{COLLECTION}/granules"
FIRST_DAY = date(2015, 3, 31)
PRESOWING_MONTHS = (4, 5)
#: бесснежный период для «Часов голой почвы»; мёрзлую почву отсекает флаг качества
SEASON_MONTHS = (4, 5, 6, 7, 8, 9, 10)
FILL = -9999.0
REQUEST_CACHE = "smap_requests"
WINDOW = 1  # ячеек в каждую сторону от центральной: окно 3x3

# EASE-Grid 2.0, глобальная цилиндрическая равновеликая проекция (EPSG:6933), сетка M09
_A = 6378137.0
_E = 0.0818191908426
_K0 = math.cos(math.radians(30)) / math.sqrt(1 - _E**2 * math.sin(math.radians(30)) ** 2)
CELL_M = 9008.055210146
NCOLS, NROWS = 3856, 1624


def _q(phi: float) -> float:
    s = math.sin(phi)
    return (1 - _E**2) * (s / (1 - _E**2 * s * s) - 1 / (2 * _E) * math.log((1 - _E * s) / (1 + _E * s)))


_QP = _q(math.pi / 2)


def lonlat_to_rowcol(lon: float, lat: float) -> tuple[int, int]:
    x = _A * _K0 * math.radians(lon)
    y = _A * _q(math.radians(lat)) / (2 * _K0)
    col = int((x + NCOLS * CELL_M / 2) // CELL_M)
    row = int((NROWS * CELL_M / 2 - y) // CELL_M)
    return min(max(row, 0), NROWS - 1), min(max(col, 0), NCOLS - 1)


def _xy_to_lonlat(x: float, y: float) -> tuple[float, float]:
    lon = math.degrees(x / (_A * _K0))
    beta = math.asin(max(-1.0, min(1.0, 2 * y * _K0 / (_A * _QP))))
    e2, e4, e6 = _E**2, _E**4, _E**6
    lat = (
        beta
        + (e2 / 3 + 31 * e4 / 180 + 517 * e6 / 5040) * math.sin(2 * beta)
        + (23 * e4 / 360 + 251 * e6 / 3780) * math.sin(4 * beta)
        + (761 * e6 / 45360) * math.sin(6 * beta)
    )
    return lon, math.degrees(lat)


def cell_polygon(row: int, col: int) -> list[list[float]]:
    """Углы ячейки 9 км в lon/lat (замкнутое кольцо GeoJSON)."""
    x0 = col * CELL_M - NCOLS * CELL_M / 2
    y1 = NROWS * CELL_M / 2 - row * CELL_M
    corners = [(x0, y1), (x0 + CELL_M, y1), (x0 + CELL_M, y1 - CELL_M), (x0, y1 - CELL_M), (x0, y1)]
    return [[round(v, 6) for v in _xy_to_lonlat(x, y)] for x, y in corners]


def cell_center(row: int, col: int) -> tuple[float, float]:
    x = (col + 0.5) * CELL_M - NCOLS * CELL_M / 2
    y = NROWS * CELL_M / 2 - (row + 0.5) * CELL_M
    return _xy_to_lonlat(x, y)


async def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    if settings.earthdata_token:
        return {"Authorization": f"Bearer {settings.earthdata_token}"}
    if settings.earthdata_username and settings.earthdata_password:
        try:
            import earthaccess  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SourceNotConfigured(
                "install the 'earthdata' extra (earthaccess) or set EARTHDATA_TOKEN"
            ) from exc

        def _login() -> str:
            auth = earthaccess.login(strategy="environment")
            token = getattr(auth, "token", None) or {}
            return token.get("access_token", "")

        token = await asyncio.to_thread(_login)
        if not token:
            raise SourceNotConfigured("Earthdata login failed: check EARTHDATA_USERNAME / EARTHDATA_PASSWORD")
        return {"Authorization": f"Bearer {token}"}
    raise SourceNotConfigured("EARTHDATA_TOKEN is not set")


async def _list_granules(
    client: httpx.AsyncClient, year: int, months: tuple[int, ...] = PRESOWING_MONTHS
) -> dict[str, str]:
    """{дата: OPeNDAP-ссылка гранулы} за месяцы ``months`` указанного года (каталог CMR, без авторизации).

    Ссылку берём из записи CMR, а не собираем из имени файла: у свежих гранул
    идентификатор в каталоге (GranuleUR) отличается от имени файла.
    """
    parts: dict = {"kind": "granule_links", "year": year, "stamp": date.today().strftime("%Y-%m")}
    if tuple(months) != PRESOWING_MONTHS:
        # прежний ключ для апреля–мая не меняется, чтобы сохранённые списки оставались в силе
        parts["months"] = ",".join(str(m) for m in months)
    key = cache.make_key(REQUEST_CACHE, **parts)
    hit = cache.read(REQUEST_CACHE, key)
    if hit is not None:
        return hit["granules"]
    m0, m1 = min(months), max(months)
    last_day = calendar.monthrange(year, m1)[1]
    params = {
        "collection_concept_id": COLLECTION,
        "temporal": f"{year}-{m0:02d}-01T00:00:00Z,{year}-{m1:02d}-{last_day}T23:59:59Z",
        "page_size": 2000,
        "sort_key": "start_date",
    }
    resp = await client.get(CMR_GRANULES, params=params)
    if resp.status_code != 200:
        raise SourceError(f"CMR HTTP {resp.status_code}")
    out: dict[str, str] = {}
    for entry in resp.json().get("feed", {}).get("entry", []):
        day = entry.get("time_start", "")[:10]
        link = next((l["href"] for l in entry.get("links", []) if "opendap.earthdata.nasa.gov" in l.get("href", "")), None)
        if link is None and entry.get("title"):
            link = f"{OPENDAP}/{entry['title']}"
        if day and link and int(day[5:7]) in months:
            out[day] = link  # при нескольких версиях остаётся последняя по сортировке
    cache.write(REQUEST_CACHE, key, {"granules": out})
    return out


def _parse_csv(text: str) -> dict[str, list[list[float]]]:
    """Ответ OPeNDAP ``.dap.csv``: строки вида ``/Group/var[i], v0, v1, v2``."""
    out: dict[str, list[list[float]]] = {}
    for line in text.splitlines():
        if not line.startswith("/"):
            continue
        head, *vals = [p.strip() for p in line.split(",")]
        name = head.rsplit("/", 1)[-1].split("[", 1)[0]
        out.setdefault(name, []).append([float(v) for v in vals])
    return out


async def _request_day(
    client: httpx.AsyncClient, headers: dict[str, str], granule: str, row: int, col: int
) -> dict:
    key = cache.make_key(REQUEST_CACHE, granule=granule, row=row, col=col, window=WINDOW)
    hit = cache.read(REQUEST_CACHE, key)
    if hit is not None:
        return hit
    r0, r1 = row - WINDOW, row + WINDOW
    c0, c1 = col - WINDOW, col + WINDOW
    slab = f"[{r0}:{r1}][{c0}:{c1}]"
    am, pm = "/Soil_Moisture_Retrieval_Data_AM", "/Soil_Moisture_Retrieval_Data_PM"
    ce = ";".join(
        [
            f"{am}/soil_moisture{slab}",
            f"{am}/retrieval_qual_flag{slab}",
            f"{pm}/soil_moisture_pm{slab}",
            f"{pm}/retrieval_qual_flag_pm{slab}",
        ]
    )
    last: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.get(f"{granule}.dap.csv", params={"dap4.ce": ce}, headers=headers)
            if resp.status_code in (401, 403):
                denied = SourceNotConfigured(f"Earthdata rejected the credentials (HTTP {resp.status_code})")
                if attempt == 2:
                    raise denied
                last = denied
                await asyncio.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 200 and resp.text.startswith("Dataset"):
                v = _parse_csv(resp.text)
                n = (2 * WINDOW + 1) ** 2
                acc, cnt = [0.0] * n, [0] * n
                for sm_name, fl_name in (
                    ("soil_moisture", "retrieval_qual_flag"),
                    ("soil_moisture_pm", "retrieval_qual_flag_pm"),
                ):
                    sm = [x for r in v.get(sm_name, []) for x in r]
                    fl = [x for r in v.get(fl_name, []) for x in r]
                    if len(sm) != n or len(fl) != n:
                        continue
                    for i in range(n):
                        if sm[i] != FILL and 0 < sm[i] < 1 and (int(fl[i]) & 1) == 0:
                            acc[i] += sm[i]
                            cnt[i] += 1
                data = {"window": [round(a / c, 4) if c else None for a, c in zip(acc, cnt)]}
                cache.write(REQUEST_CACHE, key, data)
                return data
            last = SourceError(f"OPeNDAP HTTP {resp.status_code}: {resp.text[:120]}")
        except httpx.HTTPError as exc:
            last = exc
        await asyncio.sleep(2 * (attempt + 1))
    raise SourceError(f"SMAP request failed for {granule}: {last!r}")


class SmapSource(DataSource):
    id = "smap"
    months: tuple[int, ...] = PRESOWING_MONTHS

    @property
    def enabled(self) -> bool:  # type: ignore[override]
        return get_settings().has_earthdata

    def cache_parts(self, field: Field, start: date, end: date) -> dict:
        row, col = lonlat_to_rowcol(field.centroid_lon, field.centroid_lat)
        return {"row": row, "col": col, "start_year": max(start.year, FIRST_DAY.year), "end": end.strftime("%Y-%m")}

    async def _fetch_live(
        self, field: Field, start: date, end: date, progress: ProgressCallback | None = None
    ) -> dict:
        settings = get_settings()
        headers = await _auth_headers()
        row, col = lonlat_to_rowcol(field.centroid_lon, field.centroid_lat)
        years = list(range(max(start.year, FIRST_DAY.year), end.year + 1))
        sem = asyncio.Semaphore(settings.smap_concurrency)
        daily: dict[str, list[float | None]] = {}
        failed = 0
        done = 0

        async with http_client(timeout=120.0) as client:
            granules: dict[str, str] = {}
            for year in years:
                listed = await _list_granules(client, year, self.months)
                granules.update({d: g for d, g in listed.items() if FIRST_DAY.isoformat() <= d <= end.isoformat()})
            total = len(granules)
            if total == 0:
                raise SourceError("SMAP: no granules found for the requested period")

            async def run(day: str, granule: str) -> None:
                nonlocal failed, done
                async with sem:
                    try:
                        daily[day] = (await _request_day(client, headers, granule, row, col))["window"]
                    except SourceNotConfigured:
                        raise
                    except SourceError:
                        failed += 1
                    done += 1
                    if progress:
                        progress(done, total)

            await asyncio.gather(*(run(d, g) for d, g in sorted(granules.items())))

        if failed > total * 0.3:
            raise SourceError(f"SMAP: {failed} of {total} daily files could not be read")
        center = (2 * WINDOW + 1) ** 2 // 2
        lon_c, lat_c = cell_center(row, col)
        return {
            "product": PRODUCT,
            "months": list(self.months),
            "cell": {"row": row, "col": col, "lon": round(lon_c, 5), "lat": round(lat_c, 5)},
            "window_cells": 2 * WINDOW + 1,
            "unit": "m3/m3",
            "daily": [
                {"date": d, "sm": w[center], "window": w} for d, w in sorted(daily.items()) if any(x is not None for x in w)
            ],
            "n_files": total,
            "n_failed": failed,
            "partial": failed > 0,
        }


class SmapSeasonSource(SmapSource):
    """SMAP за апрель–октябрь — суточная влажность верхнего слоя для «Часов голой почвы»."""

    id = "smap_season"
    months = SEASON_MONTHS
