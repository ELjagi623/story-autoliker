"""Tiny gettext-style translation layer: ``tr("English text")`` -> text in the active language.

English is the source language (the string itself is the key); ``i18n_zh.ZH`` maps it to Chinese. A string with no
translation falls back to the English text, so a missing entry is never an error. ``{name}`` placeholders are filled
from keyword arguments *after* translation, so word order may differ between languages.
"""
from __future__ import annotations

import locale
from typing import Callable

from . import prefs

_lang = "en"
_listeners: list[Callable[[], None]] = []


def default_language() -> str:
    forced = prefs.env_lang()
    if forced in ("en", "zh"):
        return forced
    saved = str(prefs.get("lang") or "")
    if saved in ("en", "zh"):
        return saved
    try:
        loc = (locale.getlocale()[0] or "").lower()
    except Exception:
        loc = ""
    return "zh" if loc.startswith("zh") or "chinese" in loc else "en"


def init() -> str:
    global _lang
    _lang = default_language()
    return _lang


def language() -> str:
    return _lang


def set_language(lang: str, *, save: bool = True) -> None:
    global _lang
    lang = "zh" if lang == "zh" else "en"
    if save:
        prefs.set("lang", lang)
    if lang != _lang:
        _lang = lang
        for fn in list(_listeners):
            fn()


def on_change(fn: Callable[[], None]) -> None:
    _listeners.append(fn)


def tr(text: str, **kw) -> str:
    if _lang == "zh":
        from .i18n_zh import ZH

        text = ZH.get(text, text)
    return text.format(**kw) if kw else text


def format_event(ev) -> str:
    """Runner event -> display text in the active language (the core keeps English messages)."""
    if _lang != "zh":
        return ev.message
    from .i18n_zh import format_event as _fmt

    return _fmt(ev)
