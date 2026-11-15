"""Настройки приложения. Секреты читаются только из окружения / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
APP_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # env_ignore_empty: пустое значение (`DB_PATH=` в .env, скопированном из .env.example) значит «не задано»
    # и даёт значение по умолчанию. Иначе DB_PATH= превращается в Path("") == Path(".") — истинное значение,
    # и SQLite пытается открыть каталог (sqlite3.OperationalError: unable to open database file).
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    data_dir: Path = REPO_DIR / "data"
    content_dir: Path = REPO_DIR / "content"

    # OFFLINE=1 полностью запрещает сетевые запросы: только кэш и демо-данные.
    offline: bool = False

    # NASA Earthdata (SMAP, GPM). Достаточно токена; логин/пароль нужны только для earthaccess.
    earthdata_token: str | None = None
    earthdata_username: str | None = None
    earthdata_password: str | None = None

    # Необязательный путь к набору корневых сертификатов (корпоративный прокси).
    ca_bundle: str | None = None

    # Учётные записи и хранилище
    db_path: Path | None = None  # по умолчанию data/app.db
    session_days: int = 30
    cookie_secure: bool = False  # True за HTTPS
    allow_registration: bool = True
    demo_ttl_days: int = 3

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"

    http_timeout_s: float = 60.0
    modis_timeout_s: float = 180.0
    modis_concurrency: int = 8
    smap_concurrency: int = 6

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def demo_dir(self) -> Path:
        return self.data_dir / "demo"

    @property
    def has_earthdata(self) -> bool:
        return bool(self.earthdata_token or (self.earthdata_username and self.earthdata_password))


@lru_cache
def get_settings() -> Settings:
    return Settings()
