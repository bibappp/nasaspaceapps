"""Настройки: .env, скопированный из .env.example без правок, должен работать."""
from __future__ import annotations

import re
import shutil

from app import db
from app.config import REPO_DIR, Settings

ENV_EXAMPLE = REPO_DIR / ".env.example"


def _example_keys() -> list[str]:
    return re.findall(r"^([A-Z_]+)=", ENV_EXAMPLE.read_text(encoding="utf-8"), flags=re.M)


def test_env_copied_from_example_works(tmp_path, monkeypatch):
    # Только копия .env.example: настоящие .env и переменные окружения не участвуют.
    for key in _example_keys():
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    shutil.copy(ENV_EXAMPLE, env)
    s = Settings(_env_file=env, data_dir=tmp_path)

    # Пустые значения в примере — «не задано», а не "" и не Path("") == Path(".").
    assert s.db_path is None
    assert s.ca_bundle is None
    assert s.earthdata_token is None and s.earthdata_username is None and s.earthdata_password is None
    assert not s.has_earthdata
    assert s.offline is False and s.session_days == 30 and s.demo_ttl_days == 3

    # База открывается в data_dir/app.db.
    monkeypatch.setattr(db, "get_settings", lambda: s)
    db.init_db()
    assert (tmp_path / "app.db").is_file()


def test_empty_values_fall_back_to_defaults(tmp_path, monkeypatch):
    for key in ("DB_PATH", "CA_BUNDLE", "SESSION_DAYS", "OFFLINE"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("DB_PATH=\nCA_BUNDLE=\nSESSION_DAYS=\nOFFLINE=\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.db_path is None and s.ca_bundle is None
    assert s.session_days == 30 and s.offline is False


def test_set_values_still_apply(tmp_path, monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    env = tmp_path / ".env"
    env.write_text(f"DB_PATH={tmp_path / 'x.db'}\n", encoding="utf-8")
    assert Settings(_env_file=env).db_path == tmp_path / "x.db"
