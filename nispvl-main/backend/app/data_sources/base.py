"""Единый интерфейс источников данных.

Каждый источник реализует ``fetch(field, start, end)`` и возвращает ``SourceResult``:
данные (JSON-совместимый dict), их происхождение (``origin``) и предупреждения.

Порядок получения данных:
  1. демо-поле  -> заранее сохранённые данные из ``data/demo/`` (работает без сети);
  2. файловый кэш ``data/cache/<source>/<key>.json``;
  3. живой запрос к API (если не OFFLINE) с записью в кэш;
  4. запасной вариант источника (``_fallback``), если он определён;
  5. ``origin = "unavailable"`` и предупреждение для интерфейса.

Чтобы подключить новый источник (например, GPM или Landsat), достаточно
создать модуль с классом-наследником ``DataSource``, реализовать ``_fetch_live``
и зарегистрировать класс в ``registry.py``. Остальной код менять не нужно.
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import pandas as pd

from .. import cache
from ..config import get_settings
from ..geometry import Field

log = logging.getLogger(__name__)

Origin = Literal["live", "cache", "demo", "fallback", "unavailable"]
ProgressCallback = Callable[[int, int], None]


class SourceError(RuntimeError):
    """Источник не ответил или вернул некорректные данные."""


class SourceNotConfigured(SourceError):
    """Источник не настроен (нет учётных данных или модуль ещё не реализован)."""


@dataclass
class DataWarning:
    code: str
    source: str
    params: dict[str, Any] = dc_field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceResult:
    source: str
    origin: Origin
    data: dict | None
    fetched_at: str | None = None
    warnings: list[DataWarning] = dc_field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None

    def frame(self, key: str = "daily") -> pd.DataFrame:
        """Табличное представление ряда (если источник отдаёт ряд)."""
        if not self.data or key not in self.data:
            return pd.DataFrame()
        return pd.DataFrame(self.data[key])

    def meta(self) -> dict:
        return {"source": self.source, "origin": self.origin, "fetched_at": self.fetched_at}


def http_client(timeout: float | None = None) -> httpx.AsyncClient:
    settings = get_settings()
    verify: Any = settings.ca_bundle or True
    return httpx.AsyncClient(
        timeout=timeout or settings.http_timeout_s,
        verify=verify,
        follow_redirects=True,
        headers={"User-Agent": "agro-sevooborot/0.1 (hackathon MVP)"},
    )


def demo_dirs() -> list[Path]:
    """Каталоги демо-полей: основное поле в data/demo и дополнительные в data/demo/fields/<id>."""
    base = get_settings().demo_dir
    dirs = [base] if (base / "field.json").exists() else []
    extra = base / "fields"
    if extra.exists():
        dirs += sorted(d for d in extra.iterdir() if (d / "field.json").exists())
    return dirs


def _read_record(directory: Path) -> dict | None:
    try:
        return json.loads((directory / "field.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def demo_field_record() -> dict | None:
    """Основное демо-поле (совместимость с прежним API /api/demo)."""
    return _read_record(get_settings().demo_dir) if (get_settings().demo_dir / "field.json").exists() else None


def demo_field_records() -> list[dict]:
    out = []
    for d in demo_dirs():
        rec = _read_record(d)
        if rec:
            out.append({**rec, "_dir": str(d)})
    return out


def demo_dir_for(field: Field) -> Path | None:
    from ..geometry import parse_field

    for d in demo_dirs():
        rec = _read_record(d)
        if not rec:
            continue
        try:
            if parse_field(rec["geometry"]).canonical() == field.canonical():
                return d
        except Exception:  # noqa: BLE001
            continue
    return None


def is_demo_field(field: Field) -> bool:
    return demo_dir_for(field) is not None


#: источник -> (время последнего сбоя, текст ошибки). Пока не истекла пауза,
#: повторно не опрашиваем упавший сервис, чтобы пользователь не ждал тайм-аута каждый раз.
_failures: dict[str, tuple[float, str]] = {}
FAILURE_PAUSE_S = 600


class DataSource(ABC):
    id: str = ""
    enabled: bool = True
    #: увеличить при изменении формата данных, чтобы старый кэш не использовался
    schema_version: int = 1

    # ---- то, что реализует конкретный источник -------------------------
    @abstractmethod
    async def _fetch_live(
        self, field: Field, start: date, end: date, progress: ProgressCallback | None = None
    ) -> dict:
        ...

    def cache_parts(self, field: Field, start: date, end: date) -> dict:
        """Что входит в ключ кэша. По умолчанию — весь контур поля и период."""
        return {"geometry": field.canonical(), "start": start.isoformat(), "end": end.isoformat()}

    def _fallback(self, field: Field) -> tuple[dict, DataWarning] | None:
        """Запасные данные, если API недоступен (по умолчанию нет)."""
        return None

    # ---- общий алгоритм ---------------------------------------------------
    def cache_key(self, field: Field, start: date, end: date) -> str:
        return cache.make_key(self.id, v=self.schema_version, **self.cache_parts(field, start, end))

    def read_demo(self, directory: Path | None = None) -> dict | None:
        path = (directory or get_settings().demo_dir) / f"{self.id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def read_cached(self, field: Field, start: date, end: date) -> SourceResult | None:
        """Только демо/кэш, без сети."""
        demo_dir = demo_dir_for(field)
        if demo_dir is not None:
            demo = self.read_demo(demo_dir)
            if demo is not None:
                return SourceResult(self.id, "demo", demo, demo.get("cached_at"))
        cached = cache.read(self.id, self.cache_key(field, start, end))
        if cached is not None:
            return SourceResult(self.id, "cache", cached, cached.get("cached_at"))
        return None

    async def fetch(
        self,
        field: Field,
        start: date,
        end: date,
        *,
        progress: ProgressCallback | None = None,
    ) -> SourceResult:
        hit = self.read_cached(field, start, end)
        if hit is not None:
            return hit

        warnings: list[DataWarning] = []
        if not self.enabled:
            warnings.append(DataWarning("source_not_configured", self.id))
        elif get_settings().offline:
            warnings.append(DataWarning("offline_no_cache", self.id))
        elif self.id in _failures and time.monotonic() - _failures[self.id][0] < FAILURE_PAUSE_S:
            warnings.append(DataWarning("source_unavailable", self.id, {"detail": _failures[self.id][1]}))
        else:
            try:
                data = await self._fetch_live(field, start, end, progress)
                if not data.get("partial"):
                    # неполный результат (часть запросов не удалась) не закрепляем в кэше
                    cache.write(self.id, self.cache_key(field, start, end), data)
                _failures.pop(self.id, None)
                now = datetime.now(UTC).isoformat(timespec="seconds")
                return SourceResult(self.id, "live", data, now)
            except SourceNotConfigured as exc:
                warnings.append(DataWarning("source_not_configured", self.id, {"detail": str(exc)}))
            except (SourceError, httpx.HTTPError, ValueError, KeyError) as exc:
                log.warning("source %s failed: %r", self.id, exc)
                detail = (str(exc) or type(exc).__name__)[:200]
                _failures[self.id] = (time.monotonic(), detail)
                warnings.append(DataWarning("source_unavailable", self.id, {"detail": detail}))

        fb = self._fallback(field)
        if fb is not None:
            data, warn = fb
            return SourceResult(self.id, "fallback", data, data.get("cached_at"), [*warnings, warn])
        return SourceResult(self.id, "unavailable", None, None, warnings)
