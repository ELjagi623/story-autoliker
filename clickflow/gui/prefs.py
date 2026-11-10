"""Small UI preferences (theme, language, simple/advanced mode) kept in ``~/ClickFlow/ui.json``.

Everything here is best-effort: a missing or broken file simply means "defaults".
"""
from __future__ import annotations

import json
import os
from typing import Any

from .. import storage

DEFAULTS: dict[str, Any] = {"theme": "light", "lang": "", "mode": "simple"}
_cache: dict[str, Any] | None = None


def _path():
    return storage.default_home() / "ui.json"


def load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        data = dict(DEFAULTS)
        try:
            raw = json.loads(_path().read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update({k: raw[k] for k in DEFAULTS if k in raw})
        except (OSError, ValueError):
            pass
        _cache = data
    return _cache


def get(key: str) -> Any:
    return load().get(key, DEFAULTS[key])


def set(key: str, value: Any) -> None:  # noqa: A001 (mirrors dict-like naming)
    data = load()
    if data.get(key) == value:
        return
    data[key] = value
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def reset_cache() -> None:
    """For tests: forget what was read so the next call re-reads (CLICKFLOW_HOME may have changed)."""
    global _cache
    _cache = None


def env_lang() -> str:
    return os.environ.get("CLICKFLOW_LANG", "").strip().lower()
