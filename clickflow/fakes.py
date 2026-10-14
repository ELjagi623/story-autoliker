"""Fake providers so the Runner can be exercised without a display."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

import numpy as np

from .clock import Clock
from .inputs import InputProvider
from .screen import Frame, MonitorInfo, Rect, ScreenProvider


class FakeScreen(ScreenProvider):
    """Serves a fixed image, or whatever ``source()`` returns at grab time."""

    def __init__(
        self,
        source: Union[np.ndarray, Callable[[], np.ndarray]],
        left: float = 0.0,
        top: float = 0.0,
        scale: float = 1.0,
    ) -> None:
        self._source = source
        self.left, self.top, self.scale = left, top, scale
        self.grab_count = 0

    def _image(self) -> np.ndarray:
        return self._source() if callable(self._source) else self._source

    def grab(self) -> Frame:
        self.grab_count += 1
        return Frame(self._image(), self.left, self.top, self.scale, self.scale)

    def bounds(self) -> Rect:
        return Frame(self._image(), self.left, self.top, self.scale, self.scale).bounds


@dataclass
class Action:
    t: float
    kind: str  # "click" | "key"
    x: float = 0.0
    y: float = 0.0
    button: str = ""
    clicks: int = 1
    key: str = ""


class FakeInput(InputProvider):
    """Records every action with a timestamp from ``clock``.

    ``on_click(action)`` lets a test world react to clicks (e.g. advance to the next story).
    """

    def __init__(
        self,
        clock: Optional[Clock] = None,
        on_click: Optional[Callable[[Action], None]] = None,
        on_key: Optional[Callable[[Action], None]] = None,
        position: tuple[float, float] = (500.0, 500.0),
    ) -> None:
        self.clock = clock or Clock()
        self.on_click = on_click
        self.on_key = on_key
        self.position = position
        self.actions: list[Action] = []

    def click(self, x: float, y: float, button: str = "left", clicks: int = 1) -> None:
        a = Action(self.clock.now(), "click", x, y, button, clicks)
        self.actions.append(a)
        self.position = (x, y)
        if self.on_click:
            self.on_click(a)

    def press_key(self, key: str) -> None:
        a = Action(self.clock.now(), "key", key=key)
        self.actions.append(a)
        if self.on_key:
            self.on_key(a)

    def mouse_position(self) -> tuple[float, float]:
        return self.position

    @property
    def clicks(self) -> list[Action]:
        return [a for a in self.actions if a.kind == "click"]

    @property
    def keys(self) -> list[Action]:
        return [a for a in self.actions if a.kind == "key"]


class FakeMultiScreen(ScreenProvider):
    """Several fake monitors. ``monitors`` maps index -> (image source, left, top); scale is 1.

    ``set_monitor(0)`` behaves like mss: all monitors combined is not simulated, the first monitor is used.
    """

    def __init__(self, monitors: dict[int, tuple[Union[np.ndarray, Callable[[], np.ndarray]], int, int]],
                 primary: int = 1) -> None:
        self._mons = dict(monitors)
        self.primary = primary
        self.current = primary
        self.grabs: list[int] = []  # which monitor each grab() hit, for assertions

    def _img(self, idx: int) -> np.ndarray:
        src = self._mons[idx][0]
        return src() if callable(src) else src

    def _cur(self) -> int:
        return self.current if self.current in self._mons else min(self._mons)

    def grab(self) -> Frame:
        idx = self._cur()
        self.grabs.append(idx)
        _, left, top = self._mons[idx]
        return Frame(self._img(idx), float(left), float(top), 1.0, 1.0)

    def bounds(self) -> Rect:
        idx = self._cur()
        _, left, top = self._mons[idx]
        h, w = self._img(idx).shape[:2]
        return Rect(left, top, w, h)

    def monitors(self) -> list[MonitorInfo]:
        out = []
        for idx in sorted(self._mons):
            _, left, top = self._mons[idx]
            h, w = self._img(idx).shape[:2]
            out.append(MonitorInfo(idx, left, top, w, h, idx == self.primary))
        return out

    def set_monitor(self, index: int) -> None:
        self.current = index
