"""Global stop hotkey (pynput) and hotkey string parsing."""
from __future__ import annotations

from typing import Callable, Optional

_MODIFIERS = {"ctrl": "<ctrl>", "control": "<ctrl>", "alt": "<alt>", "shift": "<shift>",
              "cmd": "<cmd>", "win": "<cmd>", "super": "<cmd>", "meta": "<cmd>"}
_SPECIAL = {"esc", "escape", "space", "enter", "return", "tab", "backspace", "delete", "home", "end",
            "pageup", "pagedown", "up", "down", "left", "right", "insert", "pause"}


def parse_hotkey(text: str) -> str:
    """Convert e.g. 'F8' or 'Ctrl+Shift+S' into pynput's '<f8>' / '<ctrl>+<shift>+s'.

    Raises ValueError for an empty or unparsable string.
    """
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if not parts:
        raise ValueError("Hotkey is empty.")
    out: list[str] = []
    for p in parts:
        if p in _MODIFIERS:
            out.append(_MODIFIERS[p])
        elif p == "escape":
            out.append("<esc>")
        elif p in _SPECIAL:
            out.append({"pageup": "<page_up>", "pagedown": "<page_down>", "return": "<enter>"}.get(p, f"<{p}>"))
        elif p.startswith("f") and p[1:].isdigit() and 1 <= int(p[1:]) <= 24:
            out.append(f"<{p}>")
        elif len(p) == 1:
            out.append(p)
        else:
            raise ValueError(f"Unknown key '{p}' in hotkey '{text}'.")
    if all(p in _MODIFIERS for p in parts):
        raise ValueError(f"Hotkey '{text}' needs a non-modifier key.")
    return "+".join(out)


class HotkeyListener:
    """Calls ``callback`` (from a pynput thread) whenever the hotkey is pressed."""

    def __init__(self, hotkey: str, callback: Callable[[], None]) -> None:
        self.hotkey = hotkey
        self.callback = callback
        self._listener = None
        self.error: Optional[str] = None

    def start(self) -> bool:
        self.stop()
        try:
            from pynput import keyboard

            self._listener = keyboard.GlobalHotKeys({parse_hotkey(self.hotkey): self.callback})
            self._listener.start()
            self.error = None
            return True
        except Exception as exc:  # bad hotkey, missing permission, no display ...
            self.error = str(exc)
            self._listener = None
            return False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
