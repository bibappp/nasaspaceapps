"""Реестр источников данных. Новый источник добавляется одной строкой в ``SOURCES``."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..config import get_settings
from .base import DataSource
from .gpm import GpmSource
from .landsat import LandsatSource
from .modis import ModisShoulderSource, ModisSource
from .power import PowerSource
from .smap import SmapSeasonSource, SmapSource
from .soilgrids import SoilGridsSource

SOURCES: dict[str, DataSource] = {
    s.id: s
    for s in (PowerSource(), ModisSource(), ModisShoulderSource(), SoilGridsSource(), SmapSource(),
              SmapSeasonSource(), GpmSource(), LandsatSource())
}


def get_source(source_id: str) -> DataSource:
    return SOURCES[source_id]


@lru_cache
def source_catalog() -> dict[str, dict]:
    path = Path(__file__).with_name("sources.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def describe_sources() -> list[dict]:
    """Каталог источников с текущим состоянием для страницы «Методика»."""
    settings = get_settings()
    out = []
    for sid, meta in source_catalog().items():
        src = SOURCES.get(sid)
        if meta.get("status") == "planned":
            state = "planned"
        elif src is not None and not src.enabled:
            state = "needs_credentials"
        elif settings.offline:
            state = "offline"
        else:
            state = "active"
        out.append({"id": sid, **meta, "state": state})
    return out
