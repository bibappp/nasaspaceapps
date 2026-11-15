"""Файлы переводов интерфейса: одинаковый набор ключей в ru, kk и en."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

LOCALES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales"
PLURAL = re.compile(r"_(zero|one|two|few|many|other)$")


def flat(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flat(v, key))
        else:
            out[key] = v
    return out


def load(lang: str) -> dict[str, str]:
    return flat(json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8")))


def test_all_languages_have_same_keys():
    norm = lambda keys: {PLURAL.sub("", k) for k in keys}  # noqa: E731 — формы множественного числа у языков разные
    ru = load("ru")
    for lang in ("kk", "en"):
        other = load(lang)
        assert norm(ru) == norm(other), {"only_ru": norm(ru) - norm(other), f"only_{lang}": norm(other) - norm(ru)}


def test_interpolation_placeholders_match():
    ru = load("ru")
    ph = lambda s: set(re.findall(r"{{\s*(\w+)\s*}}", s))  # noqa: E731
    for lang in ("kk", "en"):
        other = load(lang)
        for key, text in ru.items():
            if key in other:
                assert ph(text) == ph(other[key]), (lang, key)


def test_backend_error_codes_are_translated():
    """Коды ошибок API, которые видит пользователь, переведены на все языки."""
    app = Path(__file__).resolve().parents[1] / "app"
    codes = set()
    for path in app.rglob("*.py"):
        codes |= set(re.findall(r'HTTPException\(\s*\d+,\s*detail="(\w+)"', path.read_text(encoding="utf-8")))
    assert {"email_taken", "invalid_credentials", "weak_password"} <= codes
    for lang in ("ru", "kk", "en"):
        keys = load(lang)
        assert not {c for c in codes if f"errors.{c}" not in keys}, lang


def test_kazakh_texts_use_kazakh_letters():
    kk = load("kk")
    text = "".join(kk.values()).lower()
    assert set("әғқңөұүһі") <= set(text)


def test_backend_warning_codes_are_translated():
    """Каждый код предупреждения, который может отдать бэкенд, есть в переводах."""
    app = Path(__file__).resolve().parents[1] / "app"
    codes = set()
    for path in app.rglob("*.py"):
        codes |= set(re.findall(r'DataWarning\(\s*"(\w+)"', path.read_text(encoding="utf-8")))
    assert codes
    for lang in ("ru", "kk", "en"):
        keys = load(lang)
        missing = {c for c in codes if f"warnings.{c}" not in keys}
        assert not missing, (lang, missing)


def test_backend_text_templates_cover_both_languages():
    for name in ("explain.yaml", "report.yaml"):
        data = yaml.safe_load((Path(__file__).resolve().parents[1] / "app" / "locales" / name).read_text(encoding="utf-8"))
        for key, entry in data.items():
            assert set(entry) == {"ru", "kk", "en"}, (name, key)
