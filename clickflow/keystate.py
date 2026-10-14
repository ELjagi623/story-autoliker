"""Hook-free stop key: polls the OS key state (Windows GetAsyncKeyState).

pynput's global hotkey depends on a keyboard hook, which some setups miss. Polling the key
state every ~10 ms is independent of that and also catches very short taps (it checks the
"pressed since last call" bit as well). On other OSes this is a no-op and only the pynput
hotkey, the Stop button and the corner abort are available.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from . import platform_utils

_NAMED = {
    "esc": 0x1B, "escape": 0x1B, "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "backspace": 0x08,
    "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "insert": 0x2D, "pause": 0x13,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "cmd": 0x5B, "win": 0x5B, "super": 0x5B, "meta": 0x5B,
}
_MODIFIER_VKS = {0x11, 0x12, 0x10, 0x5B}


def vk_codes(hotkey: str) -> list[int]:
    """'ctrl+shift+F8' -> list of Windows virtual-key codes. Raises ValueError if unknown."""
    codes: list[int] = []
    for p in (x.strip().lower() for x in hotkey.split("+")):
        if not p:
            continue
        if p in _NAMED:
            codes.append(_NAMED[p])
        elif p.startswith("f") and p[1:].isdigit() and 1 <= int(p[1:]) <= 24:
            codes.append(0x70 + int(p[1:]) - 1)
        elif len(p) == 1 and p.isalnum():
            codes.append(ord(p.upper()))
        else:
            raise ValueError(f"Unknown key '{p}' in hotkey '{hotkey}'.")
    if not codes or all(c in _MODIFIER_VKS for c in codes):
        raise ValueError(f"Hotkey '{hotkey}' needs a non-modifier key.")
    return codes


class StopKeyWatcher:
    """Calls ``callback`` (from a background thread) when the hotkey is pressed. Windows only."""

    def __init__(self, hotkey: str, callback: Callable[[], None], poll: float = 0.01,
                 get_state: Optional[Callable[[int], int]] = None) -> None:
        self.hotkey = hotkey
        self.callback = callback
        self.poll = poll
        self._get_state = get_state
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.error: Optional[str] = None

    @staticmethod
    def supported() -> bool:
        return platform_utils.os_name() == "windows"

    def start(self) -> bool:
        self.stop()
        if self._get_state is None:
            if not self.supported():
                self.error = "key-state polling is only available on Windows"
                return False
            import ctypes

            self._get_state = ctypes.windll.user32.GetAsyncKeyState
        try:
            codes = vk_codes(self.hotkey)
        except ValueError as exc:
            self.error = str(exc)
            return False
        self.error = None
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(codes,), name="stop-key-watcher", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        t, self._thread = self._thread, None
        if t is not None and t is not threading.current_thread():
            t.join(1.0)

    def _loop(self, codes: list[int]) -> None:
        main = codes[-1]
        mods = codes[:-1]
        get = self._get_state
        was_down = False
        while not self._stop.is_set():
            try:
                s = get(main)
                mods_down = all(get(m) & 0x8000 for m in mods)
                down = bool(s & 0x8000)
                tapped = bool(s & 0x0001)  # pressed (and maybe released) since the last poll
                combo_down = mods_down and down
                if (combo_down and not was_down) or (mods_down and tapped):
                    self.callback()
                was_down = combo_down
            except Exception:
                pass
            time.sleep(self.poll)
