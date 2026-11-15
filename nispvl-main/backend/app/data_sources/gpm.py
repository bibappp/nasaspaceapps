"""GPM IMERG (осадки, 0,1°) — ТОЧКА РАСШИРЕНИЯ, в MVP не реализовано.

Что нужно, чтобы включить источник (остальной код менять не придётся):
  1. Реализовать ``_fetch_live``: суточный продукт ``GPM_3IMERGDF`` v07
     (CMR: C2723754864-GES_DISC) через OPeNDAP GES DISC с вырезкой одной ячейки,
     авторизация Earthdata — так же, как в ``smap.py``.
  2. Вернуть dict того же вида, что ``power.py``:
     ``{"lat", "lon", "daily": {"date": [...], "PRECTOTCORR": [...]}}``.
  3. Поставить ``enabled = True``. В ``analytics/climate.py`` источник осадков
     выбирается параметром ``precip_source`` в ``rules/model.yaml``.

Ограничения продукта описаны в ``sources.yaml`` (запись ``gpm``).
"""
from __future__ import annotations

from datetime import date

from ..geometry import Field
from .base import DataSource, ProgressCallback, SourceNotConfigured


class GpmSource(DataSource):
    id = "gpm"
    enabled = False

    async def _fetch_live(
        self, field: Field, start: date, end: date, progress: ProgressCallback | None = None
    ) -> dict:
        raise SourceNotConfigured("GPM IMERG is not implemented in the MVP; NASA POWER is used for precipitation")
