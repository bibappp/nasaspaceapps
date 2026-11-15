"""Файловый JSON-кэш. Ключ — sha256 от (источник + геометрия + период + параметры)."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import get_settings


def make_key(source: str, **parts: Any) -> str:
    payload = json.dumps({"source": source, **parts}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _path(directory: Path, source: str, key: str) -> Path:
    return directory / source / f"{key}.json"


def read(source: str, key: str, directory: Path | None = None) -> dict | None:
    path = _path(directory or get_settings().cache_dir, source, key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write(source: str, key: str, data: dict, directory: Path | None = None) -> Path:
    path = _path(directory or get_settings().cache_dir, source, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"cached_at": datetime.now(UTC).isoformat(timespec="seconds"), **data}
    # атомарная запись: фоновые задачи могут писать параллельно
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return path
