"""ScreenProvider: where screenshots come from.

Coordinate model (important for HiDPI / Retina):

* ``Frame.image`` is in *physical pixels* (what the template matcher sees).
* "Screen coordinates" are the units the input layer clicks in: physical pixels on
  Windows/Linux (the process is made DPI aware) and points on macOS (Retina: 1 point
  = 2 pixels). ``Frame.scale_x/scale_y`` is pixels-per-screen-unit, so
  ``Frame.to_screen`` converts any image pixel to a clickable coordinate.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import platform_utils


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def center(self) -> tuple[float, float]:
        return (self.left + self.width / 2, self.top + self.height / 2)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (int(round(self.left)), int(round(self.top)), int(round(self.width)), int(round(self.height)))


@dataclass
class Frame:
    image: np.ndarray  # BGR uint8, physical pixels
    left: float = 0.0  # screen coordinate of the image's top-left pixel
    top: float = 0.0
    scale_x: float = 1.0  # image pixels per screen unit
    scale_y: float = 1.0

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        return (self.left + x / self.scale_x, self.top + y / self.scale_y)

    def to_image(self, sx: float, sy: float) -> tuple[float, float]:
        return ((sx - self.left) * self.scale_x, (sy - self.top) * self.scale_y)

    def rect_to_screen(self, x: float, y: float, w: float, h: float) -> Rect:
        l, t = self.to_screen(x, y)
        return Rect(l, t, w / self.scale_x, h / self.scale_y)

    def region_to_image(self, region: tuple[int, int, int, int]) -> Optional[tuple[int, int, int, int]]:
        """Convert a screen-coordinate region (l, t, w, h) into clamped image pixels (x0, y0, x1, y1).

        Returns None when the region does not intersect the frame.
        """
        l, t, w, h = region
        x0, y0 = self.to_image(l, t)
        x1, y1 = self.to_image(l + w, t + h)
        ih, iw = self.image.shape[:2]
        x0, y0 = max(0, int(np.floor(x0))), max(0, int(np.floor(y0)))
        x1, y1 = min(iw, int(np.ceil(x1))), min(ih, int(np.ceil(y1)))
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1, y1)

    @property
    def bounds(self) -> Rect:
        h, w = self.image.shape[:2]
        return Rect(self.left, self.top, w / self.scale_x, h / self.scale_y)


@dataclass(frozen=True)
class MonitorInfo:
    """One physical display, in screen units (the same units clicks use)."""

    index: int  # mss numbering: 1 = first monitor ... (0 is reserved for "all monitors combined")
    left: int
    top: int
    width: int
    height: int
    primary: bool = False

    @property
    def resolution(self) -> tuple[int, int]:
        return (self.width, self.height)

    @property
    def label(self) -> str:
        return f"Monitor {self.index}: {self.width}x{self.height}" + (" (primary)" if self.primary else "")


class ScreenProvider(ABC):
    @abstractmethod
    def grab(self) -> Frame:
        """Capture the current screen."""

    @abstractmethod
    def bounds(self) -> Rect:
        """Extent of the capturable area in screen coordinates (used for corner abort)."""

    def monitors(self) -> list[MonitorInfo]:
        """The individual displays. Default: one display covering ``bounds()``."""
        b = self.bounds()
        return [MonitorInfo(1, int(b.left), int(b.top), int(b.width), int(b.height), True)]

    def set_monitor(self, index: int) -> None:
        """Capture only monitor ``index`` from now on (0 = all combined). Default: single-display no-op."""


class MssScreen(ScreenProvider):
    """Real screen capture through ``mss``.

    ``monitor`` follows mss numbering: 0 = all monitors combined, 1 = primary, ...
    mss handles are thread bound on some platforms, so one is created per thread.
    """

    def __init__(self, monitor: int = 0) -> None:
        platform_utils.ensure_dpi_aware()
        self.monitor = monitor
        self._local = threading.local()

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss

            factory = getattr(mss, "MSS", None) or mss.mss
            sct = factory()
            self._local.sct = sct
        return sct

    def _monitor(self, sct) -> dict:
        monitors = sct.monitors
        idx = self.monitor if 0 <= self.monitor < len(monitors) else 0
        return monitors[idx]

    def grab(self) -> Frame:
        sct = self._sct()
        mon = self._monitor(sct)
        shot = sct.grab(mon)
        img = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        img = np.ascontiguousarray(img[:, :, :3])
        return Frame(
            image=img,
            left=float(mon["left"]),
            top=float(mon["top"]),
            scale_x=shot.width / mon["width"],
            scale_y=shot.height / mon["height"],
        )

    def bounds(self) -> Rect:
        mon = self._monitor(self._sct())
        return Rect(mon["left"], mon["top"], mon["width"], mon["height"])

    def monitors(self) -> list[MonitorInfo]:
        mons = self._sct().monitors[1:]
        out = []
        for i, m in enumerate(mons, start=1):
            primary = bool(m.get("is_primary", i == 1))
            out.append(MonitorInfo(i, int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"]), primary))
        if out and not any(m.primary for m in out):
            out[0] = MonitorInfo(*(out[0].index, out[0].left, out[0].top, out[0].width, out[0].height, True))
        return out

    def set_monitor(self, index: int) -> None:
        self.monitor = max(0, int(index))
