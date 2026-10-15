"""Minimal translation layer.

All UI strings go through ``_()``. English is the source language; adding Urdu
means filling ``TRANSLATIONS['ur']`` (or loading a JSON file next to this
module) - the UI switches to right-to-left layout automatically.
"""
from __future__ import annotations

import json
from pathlib import Path

LANGUAGES = {"en": "English", "ur": "اردو (Urdu) - preview"}
RTL = {"ur"}
TRANSLATIONS: dict[str, dict[str, str]] = {
    "ur": {
        "Dashboard": "ڈیش بورڈ", "Live Bays": "لائیو بے", "Sessions": "سیشنز", "History": "ہسٹری",
        "Reports": "رپورٹس", "Products": "مصنوعات", "Cameras": "کیمرے", "Training": "ٹریننگ",
        "Users": "صارفین", "Settings": "ترتیبات", "Log in": "لاگ ان", "Log out": "لاگ آؤٹ",
        "Username": "صارف نام", "Password": "پاس ورڈ", "Start loading": "لوڈنگ شروع کریں",
        "Close & verify": "بند کریں اور تصدیق کریں", "CLEARED": "کلیئر", "MISMATCH": "فرق",
    }
}
_lang = "en"


def set_language(code: str):
    global _lang
    _lang = code if code in LANGUAGES else "en"
    extra = Path(__file__).parent / "translations" / f"{_lang}.json"
    if extra.exists():
        TRANSLATIONS.setdefault(_lang, {}).update(json.loads(extra.read_text(encoding="utf-8")))


def language() -> str:
    return _lang


def is_rtl() -> bool:
    return _lang in RTL


def _(text: str) -> str:
    if _lang == "en":
        return text
    return TRANSLATIONS.get(_lang, {}).get(text, text)
