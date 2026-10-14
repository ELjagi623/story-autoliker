"""Synthetic imagery and a tiny fake 'world' shared by the tests."""
from __future__ import annotations

import cv2
import numpy as np

from clickflow.clock import FakeClock
from clickflow.fakes import FakeInput, FakeScreen


def make_background(w: int = 800, h: int = 600, seed: int = 1) -> np.ndarray:
    """Smooth-ish random clutter so matching is not trivially easy."""
    rng = np.random.default_rng(seed)
    small = rng.integers(40, 200, size=(h // 8 + 1, w // 8 + 1, 3), dtype=np.uint8)
    bg = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    noise = rng.integers(-10, 10, size=bg.shape, dtype=np.int16)
    return np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def make_heart(size: int = 48, filled: bool = True) -> np.ndarray:
    """A heart-ish icon: dark disc, red/white heart. Non-symmetric details avoid false matches."""
    img = np.full((size, size, 3), (30, 30, 30), np.uint8)
    cv2.circle(img, (size // 2, size // 2), size // 2 - 1, (60, 40, 20), -1)
    s = size / 48.0
    pts = np.array([[24, 40], [8, 22], [10, 12], [18, 10], [24, 17], [31, 9], [39, 13], [40, 23]], np.float32) * s
    color = (40, 40, 230) if filled else (240, 240, 240)
    if filled:
        cv2.fillPoly(img, [pts.astype(np.int32)], color)
    else:
        cv2.polylines(img, [pts.astype(np.int32)], True, color, max(1, int(2 * s)))
    cv2.circle(img, (int(14 * s), int(34 * s)), max(1, int(3 * s)), (0, 200, 255), -1)  # asymmetry marker
    return img


def make_arrow(size: int = 40) -> np.ndarray:
    img = np.full((size, size, 3), (230, 230, 230), np.uint8)
    s = size / 40.0
    cv2.rectangle(img, (int(6 * s), int(16 * s)), (int(22 * s), int(24 * s)), (20, 20, 20), -1)
    tri = np.array([[22, 8], [34, 20], [22, 32]], np.float32) * s
    cv2.fillPoly(img, [tri.astype(np.int32)], (20, 120, 20))
    cv2.line(img, (2, 2), (int(10 * s), int(4 * s)), (200, 0, 0), 2)
    return img


def make_end_marker(size: int = 56) -> np.ndarray:
    img = np.full((size, size, 3), (20, 140, 220), np.uint8)
    cv2.line(img, (6, 6), (size - 6, size - 6), (255, 255, 255), 5)
    cv2.line(img, (size - 6, 6), (6, size - 6), (255, 255, 255), 5)
    cv2.circle(img, (size // 2, size // 2), size // 4, (0, 0, 0), 3)
    return img


def paste(bg: np.ndarray, icon: np.ndarray, x: int, y: int) -> np.ndarray:
    out = bg.copy()
    h, w = icon.shape[:2]
    out[y:y + h, x:x + w] = icon
    return out


HEART_POS = (150, 200)   # top-left, in screenshot pixels
ARROW_POS = (600, 250)
END_POS = (350, 400)


class World:
    """A fake screen + input that reacts to clicks: heart/arrow visibility can be scripted."""

    def __init__(self, heart=True, arrow=True, end=False, scale: float = 1.0, left: float = 0.0, top: float = 0.0):
        self.clock = FakeClock()
        self.bg = make_background()
        self.heart_img, self.arrow_img, self.end_img = make_heart(), make_arrow(), make_end_marker()
        self.heart, self.arrow, self.end = heart, arrow, end
        self.click_log: list[str] = []
        self.on_grab = None  # optional callback(grab_index)
        self.screen = FakeScreen(self.render, left=left, top=top, scale=scale)
        self.input = FakeInput(self.clock, on_click=self._clicked)
        self.templates = {"heart.png": self.heart_img, "arrow.png": self.arrow_img, "end.png": self.end_img}

    def render(self) -> np.ndarray:
        if self.on_grab:
            self.on_grab(self.screen.grab_count)
        img = self.bg
        if self.heart:
            img = paste(img, self.heart_img, *HEART_POS)
        if self.arrow:
            img = paste(img, self.arrow_img, *ARROW_POS)
        if self.end:
            img = paste(img, self.end_img, *END_POS)
        return img

    def _clicked(self, a) -> None:
        s = self.screen.scale
        px, py = (a.x - self.screen.left) * s, (a.y - self.screen.top) * s
        for name, (x, y), icon in (("H", HEART_POS, self.heart_img), ("A", ARROW_POS, self.arrow_img)):
            h, w = icon.shape[:2]
            if x <= px < x + w and y <= py < y + h:
                self.click_log.append(name)
                return
        self.click_log.append("?")

    def center(self, pos, icon) -> tuple[float, float]:
        h, w = icon.shape[:2]
        s = self.screen.scale
        return (self.screen.left + (pos[0] + w / 2) / s, self.screen.top + (pos[1] + h / 2) / s)
