"""Постоянное хранилище: SQLite (файл data/app.db, том Docker ./data).

Таблицы: пользователи, сессии, поля (с историей культур) и сохранённые анализы.
Каждое обращение открывает своё соединение — это безопасно для потоков FastAPI
и достаточно для нагрузки одного хозяйства или демонстрации.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL DEFAULT '',
    farm_name     TEXT NOT NULL DEFAULT '',
    lang          TEXT NOT NULL DEFAULT 'ru',
    password_hash TEXT NOT NULL,
    is_demo       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fields (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    region     TEXT NOT NULL,
    geometry   TEXT NOT NULL,
    area_ha    REAL NOT NULL,
    centroid_lat REAL NOT NULL,
    centroid_lon REAL NOT NULL,
    soil       TEXT NOT NULL DEFAULT '{}',
    notes      TEXT NOT NULL DEFAULT '',
    history    TEXT NOT NULL DEFAULT '[]',
    history_is_scenario INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS fields_user ON fields(user_id);
CREATE TABLE IF NOT EXISTS analyses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    field_id   INTEGER NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
    title      TEXT NOT NULL DEFAULT '',
    request    TEXT NOT NULL,
    summary    TEXT NOT NULL,
    result     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS analyses_field ON analyses(field_id);
CREATE INDEX IF NOT EXISTS analyses_user ON analyses(user_id);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _path():
    s = get_settings()
    return s.db_path or (s.data_dir / "app.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)


def row_to_dict(row: sqlite3.Row | None, json_fields: tuple[str, ...] = ()) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    for f in json_fields:
        if f in d and isinstance(d[f], str):
            d[f] = json.loads(d[f])
    return d
