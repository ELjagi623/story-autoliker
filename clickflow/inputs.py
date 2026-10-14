"""InputProvider: how clicks and key presses reach the OS."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from . import platform_utils


class InputProvider(ABC):
    @abstractmethod
    def click(self, x: float, y: float, button: str = "left", clicks: int = 1) -> None:
        """Click at screen coordinates. ``button`` is left/right; ``clicks`` 1 or 2."""

    @abstractmethod
    def press_key(self, key: str) -> None:
        """Press a key or a combination written like ``ctrl+w``."""

    @abstractmethod
    def mouse_position(self) -> tuple[float, float]:
        """Current cursor position in screen coordinates."""


class PyAutoGuiInput(InputProvider):
    def __init__(self) -> None:
        platform_utils.ensure_dpi_aware()
        import pyautogui

        pyautogui.FAILSAFE = False  # ClickFlow implements its own corner abort in the Runner
        pyautogui.PAUSE = 0
        self._pg = pyautogui

    def click(self, x: float, y: float, button: str = "left", clicks: int = 1) -> None:
        pg = self._pg
        pg.moveTo(int(round(x)), int(round(y)))
        time.sleep(0.04)  # let hover state / the target window settle before pressing
        pg.click(button=button, clicks=clicks, interval=0.06)

    def press_key(self, key: str) -> None:
        parts = [k.strip() for k in key.split("+") if k.strip()]
        if not parts:
            return
        if len(parts) == 1:
            self._pg.press(parts[0])
        else:
            self._pg.hotkey(*parts)

    def mouse_position(self) -> tuple[float, float]:
        p = self._pg.position()
        return (float(p.x), float(p.y))


class NullInput(InputProvider):
    """Does nothing. Used for 'Test this step', which only looks and never touches the mouse."""

    def click(self, x: float, y: float, button: str = "left", clicks: int = 1) -> None:
        pass

    def press_key(self, key: str) -> None:
        pass

    def mouse_position(self) -> tuple[float, float]:
        return (-1.0, -1.0)
