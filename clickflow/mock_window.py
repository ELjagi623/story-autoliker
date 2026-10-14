"""A fake "story viewer" used as the end-to-end test target (and as a practice target).

It shows a fake heart button and a fake next-story arrow and counts clicks on each.
Clicking the heart likes the current story (the heart turns into a filled red one, so
the unliked-heart template no longer matches); clicking the arrow advances to the next
story, whose background changes. After the last story an "end" marker is shown and the
buttons disappear. It contains no real-service logic - it is just two clickable shapes.

Run it by hand:  python -m clickflow.mock_window
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .gui.qtutils import qimage_to_bgr

HEART_RECT = QRect(40, 330, 64, 64)
ARROW_RECT = QRect(470, 190, 60, 60)
END_RECT = QRect(220, 150, 120, 120)


@dataclass
class ClickRecord:
    kind: str  # "heart" | "arrow" | "other"
    story: int
    global_x: float
    global_y: float
    local_x: float
    local_y: float
    t: float = 0.0  # time.monotonic() when the click arrived (for speed measurements)


class MockStoryWindow(QWidget):
    def __init__(self, num_stories: int = 6, preliked: Iterable[int] = (), position=(500, 250)) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setFixedSize(560, 430)
        self.move(*position)
        self.num_stories = num_stories
        self.liked: set[int] = set(preliked)
        self.story = 0
        self.clicks: list[ClickRecord] = []

    # ------------------------------------------------------------------ state

    @property
    def finished(self) -> bool:
        return self.story >= self.num_stories

    @property
    def heart_clicks(self) -> int:
        return sum(1 for c in self.clicks if c.kind == "heart")

    @property
    def arrow_clicks(self) -> int:
        return sum(1 for c in self.clicks if c.kind == "arrow")

    @property
    def sequence(self) -> list[str]:
        """Click kinds in order, e.g. ['heart', 'arrow', 'arrow', ...]."""
        return [c.kind for c in self.clicks]

    def set_story(self, index: int) -> None:
        self.story = index
        self.update()
        self.repaint()

    # ------------------------------------------------------------------ input

    def mousePressEvent(self, e) -> None:  # noqa: N802 (Qt API)
        p = e.position().toPoint()
        g = e.globalPosition()
        kind = "other"
        if not self.finished:
            if HEART_RECT.contains(p):
                kind = "heart"
                self.liked.add(self.story)
            elif ARROW_RECT.contains(p):
                kind = "arrow"
                self.story += 1
        self.clicks.append(ClickRecord(kind, self.story, g.x(), g.y(), p.x(), p.y(), time.monotonic()))
        self.update()

    # ------------------------------------------------------------------ painting

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hue = (self.story * 53) % 360
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor.fromHsv(hue, 120, 90))
        grad.setColorAt(1, QColor.fromHsv((hue + 70) % 360, 160, 160))
        p.fillRect(self.rect(), grad)
        p.setPen(QPen(QColor(255, 255, 255, 60), 2))
        for i in range(6):  # story "photo" clutter that changes per story
            p.drawEllipse(QPointF(80 + i * 85 + self.story * 13 % 40, 90 + (i * 37 + self.story * 29) % 120), 28, 28)

        if self.finished:
            self._draw_end(p)
        else:
            self._draw_heart(p, HEART_RECT, filled=self.story in self.liked)
            self._draw_arrow(p, ARROW_RECT)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 11))
        label = "end of stories" if self.finished else f"story {self.story + 1}/{self.num_stories}"
        p.drawText(14, 24, f"MOCK VIEWER - {label}   hearts={self.heart_clicks} arrows={self.arrow_clicks}")
        p.end()

    @staticmethod
    def _heart_path(r: QRectF) -> QPainterPath:
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        path = QPainterPath()
        path.moveTo(x + w * 0.5, y + h * 0.92)
        path.cubicTo(x - w * 0.15, y + h * 0.55, x + w * 0.1, y + h * 0.05, x + w * 0.5, y + h * 0.32)
        path.cubicTo(x + w * 0.9, y + h * 0.05, x + w * 1.15, y + h * 0.55, x + w * 0.5, y + h * 0.92)
        return path

    def _draw_heart(self, p: QPainter, r: QRect, filled: bool) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(25, 25, 40))
        p.drawEllipse(r)
        inner = QRectF(r).adjusted(14, 14, -14, -14)
        path = self._heart_path(inner)
        if filled:
            p.setBrush(QColor(235, 30, 60))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(245, 245, 245), 3))
        p.drawPath(path)
        p.setBrush(QColor(255, 200, 0))  # asymmetry marker so the icon is unambiguous to match
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(r.x() + 12, r.y() + r.height() - 12), 4, 4)

    def _draw_arrow(self, p: QPainter, r: QRect) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(240, 240, 240))
        p.drawEllipse(r)
        pen = QPen(QColor(20, 20, 20), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        c = QPointF(r.center())
        p.drawLine(QPointF(c.x() - 8, c.y() - 16), QPointF(c.x() + 10, c.y()))
        p.drawLine(QPointF(c.x() + 10, c.y()), QPointF(c.x() - 8, c.y() + 16))

    def _draw_end(self, p: QPainter) -> None:
        r = END_RECT
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 140, 220))
        p.drawRoundedRect(r, 14, 14)
        p.setPen(QPen(QColor(255, 255, 255), 8))
        p.drawLine(r.left() + 20, r.top() + 20, r.right() - 20, r.bottom() - 20)
        p.drawLine(r.right() - 20, r.top() + 20, r.left() + 20, r.bottom() - 20)
        p.setPen(QPen(QColor(0, 0, 0), 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(r.center(), 26, 26)

    # ------------------------------------------------------------------ test helpers

    def grab_region(self, rect: QRect, story: Optional[int] = None) -> np.ndarray:
        """Render the given widget-local rect (in physical pixels) as a BGR array.

        Optionally shows another story first, so tests can capture each state as a template.
        """
        old = self.story
        if story is not None:
            self.set_story(story)
        QApplication.processEvents()
        img = qimage_to_bgr(self.grab(rect).toImage())
        if story is not None:
            self.set_story(old)
        return img

    def global_center(self, rect: QRect) -> tuple[float, float]:
        c = self.mapToGlobal(rect.center())
        return (c.x(), c.y())


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    win = MockStoryWindow(num_stories=8, preliked={1, 4})
    win.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
    win.setWindowTitle("ClickFlow mock viewer")
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
