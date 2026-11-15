from __future__ import annotations

import pytest

from app.config import get_settings
from app.model.rotation import FieldConditions
from app.model.rules import get_rules


@pytest.fixture(scope="session")
def rules():
    return get_rules()


@pytest.fixture
def cond() -> FieldConditions:
    """Синтетические условия поля в Акмолинской области (не реальные данные)."""
    return FieldConditions(
        region="akmola",
        area_ha=400.0,
        p_season_normal=165.0,
        stock_normal=120.0,
        p_season_dry=95.0,
        stock_dry=110.0,
        dry_year=2023,
        p_season_ref=154.1,
        stock_ref=120.0,
        awc_mm=140.0,
    )


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Пустые каталоги кэша и демо: тесты не трогают настоящие data/."""
    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    (tmp_path / "cache").mkdir()
    (tmp_path / "demo").mkdir()
    return tmp_path
