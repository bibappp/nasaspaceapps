"""Landsat Collection 2 Level-2 (NDVI, 30 м) — ТОЧКА РАСШИРЕНИЯ, в MVP не реализовано.

Что нужно, чтобы включить источник (остальной код менять не придётся):
  1. Реализовать ``_fetch_live``: поиск сцен в STAC Microsoft Planetary Computer
     (``https://planetarycomputer.microsoft.com/api/stac/v1``, коллекция ``landsat-c2-l2``),
     подпись ссылок, чтение окон ``red`` и ``nir08`` (COG) и маски ``qa_pixel``.
     Потребуются зависимости ``pystac-client``, ``planetary-computer``, ``rasterio``.
  2. Вернуть dict того же вида, что ``modis.py``:
     ``{"series": [{"date", "ndvi", "valid_fraction"}], "grid", "rasters"}``.
     Тогда тренд NDVI, слой карты и страница «Ретро-проверка» заработают без изменений.
  3. Поставить ``enabled = True``.

Ограничения продукта описаны в ``sources.yaml`` (запись ``landsat``).
"""
from __future__ import annotations

from datetime import date

from ..geometry import Field
from .base import DataSource, ProgressCallback, SourceNotConfigured


class LandsatSource(DataSource):
    id = "landsat"
    enabled = False

    async def _fetch_live(
        self, field: Field, start: date, end: date, progress: ProgressCallback | None = None
    ) -> dict:
        raise SourceNotConfigured("Landsat is not implemented in the MVP; MODIS MOD13Q1 is used for NDVI")
