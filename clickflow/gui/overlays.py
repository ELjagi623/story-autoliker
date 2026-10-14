"""Full-screen overlays: the rectangle-capture overlay and the match highlighter."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import platform_utils
from .qtutils import bgr_to_pixmap


class CaptureOverlay(QWidget):
    """Shows a dimmed screenshot; the user drags a rectangle.

    Emits ``selected(x, y, w, h)`` in *screenshot pixels* (not Qt logical units), so the
    crop is exact on HiDPI screens. Esc or a right click cancels.
    """

    selected = Signal(int, int, int, int)
    cancelled = Signal()

    def __init__(self, image: np.ndarray, geometry: QRect, hint: str,
                 guides: Optional[list[tuple[int, int, int, int, str]]] = None) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(geometry)
        self._pix = bgr_to_pixmap(image)
        self._hint = hint
        # (x, y, w, h in screenshot pixels, label): existing boxes / the template, drawn for orientation
        self._guides = list(guides or [])
        self._start: Optional[QPoint] = None
        self._cur: Optional[QPoint] = None
        self._done = False

    def open(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _sel(self) -> Optional[QRect]:
        if self._start is None or self._cur is None:
            return None
        x0, x1 = sorted((self._start.x(), self._cur.x()))
        y0, y1 = sorted((self._start.y(), self._cur.y()))
        return QRect(x0, y0, x1 - x0, y1 - y0)  # not QRect(p1, p2): that one is inclusive (+1 px)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._pix)
        p.fillRect(self.rect(), QColor(0, 0, 0, 130))
        sel = self._sel()
        if sel and sel.width() > 0 and sel.height() > 0:
            sx, sy = self._pix.width() / self.width(), self._pix.height() / self.height()
            src = QRectF(sel.x() * sx, sel.y() * sy, sel.width() * sx, sel.height() * sy)
            p.drawPixmap(QRectF(sel), self._pix, src)  # un-dimmed hole
            p.setPen(QPen(QColor(0, 200, 255), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(sel)
            p.setFont(QFont("Arial", 10))
            p.setPen(QColor(255, 255, 255))
            p.drawText(sel.x(), max(14, sel.y() - 6), f"{round(src.width())} x {round(src.height())} px")
        self._paint_guides(p)
        p.setFont(QFont("Arial", 13))
        p.setPen(QColor(255, 255, 255))
        p.drawText(20, 36, self._hint)
        p.end()

    def _paint_guides(self, p: QPainter) -> None:
        if not self._guides:
            return
        sx, sy = self._pix.width() / self.width(), self._pix.height() / self.height()
        p.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        for x, y, w, h, label in self._guides:
            r = QRectF(x / sx, y / sy, w / sx, h / sy)
            col = QColor(0, 220, 255) if label == "template" else QColor(255, 170, 0)
            p.setPen(QPen(col, 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            p.setPen(col)
            p.drawText(QPoint(int(r.x()) + 2, max(12, int(r.y()) - 4)), label)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.RightButton:
            self._finish(None)
            return
        self._start = self._cur = e.position().toPoint()
        self.update()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._start is not None:
            self._cur = e.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._start is None or e.button() != Qt.MouseButton.LeftButton:
            return
        self._cur = e.position().toPoint()
        sel = self._sel()
        self._start = None
        if not sel or sel.width() < 4 or sel.height() < 4:
            self.update()
            return  # too small: let the user drag again
        sx, sy = self._pix.width() / self.width(), self._pix.height() / self.height()
        rect = (round(sel.x() * sx), round(sel.y() * sy), round(sel.width() * sx), round(sel.height() * sy))
        self._finish(rect)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def closeEvent(self, e) -> None:  # noqa: N802
        if not self._done:
            self._done = True
            self.cancelled.emit()
        super().closeEvent(e)

    def _finish(self, rect) -> None:
        if self._done:
            return
        self._done = True
        if rect is None:
            self.cancelled.emit()
        else:
            self.selected.emit(*rect)
        self.close()


class Highlighter(QWidget):
    """Click-through, always-on-top layer that draws boxes around matches for a moment."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._boxes: list[tuple[QRectF, str, QColor, float, bool]] = []  # rect, label, colour, expiry, dashed
        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._tick)

    def flash(self, rect: tuple[float, float, float, float], label: str, found: bool, ms: int = 700,
              kind: str = "match") -> None:
        """``rect`` is (left, top, width, height) in *input* (screen) coordinates.

        ``kind="region"`` draws a dashed blue search box instead of a green/orange match box.
        """
        screen = QGuiApplication.primaryScreen()
        geo = screen.virtualGeometry()
        f = platform_utils.input_to_qt_factor(screen.devicePixelRatio())
        l, t, w, h = rect
        box = QRectF(l * f - geo.x(), t * f - geo.y(), w * f, h * f)
        color = QColor(70, 150, 255) if kind == "region" else (QColor(40, 220, 80) if found else QColor(255, 170, 0))
        self._boxes.append((box, label, color, time.monotonic() + ms / 1000.0, kind == "region"))
        if not self.isVisible():
            self.setGeometry(geo)
            self.show()
        self._timer.start()
        self.update()

    def _tick(self) -> None:
        now = time.monotonic()
        self._boxes = [b for b in self._boxes if b[3] > now]
        if not self._boxes:
            self._timer.stop()
            self.hide()
        else:
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        for box, label, color, _, dashed in self._boxes:
            outer = box.adjusted(-4, -4, 4, 4)  # drawn outside the match so the icon pixels stay untouched
            p.setPen(QPen(color, 3, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(outer)
            p.setPen(color)
            p.drawText(QPoint(int(outer.x()), max(12, int(outer.y()) - 5)), label)
        p.end()


class StopBadge(QWidget):
    """Small always-on-top red "STOP" button shown while a run is active. Click it to stop.

    It never takes keyboard focus, so clicking it does not steal focus from the window being automated.
    """

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(190, 44)
        self._text = "STOP"

    def show_badge(self, hotkey: str) -> None:
        self._text = f"■ STOP  ({hotkey})" if hotkey else "■ STOP"
        geo = QGuiApplication.primaryScreen().geometry()
        self.move(geo.x() + (geo.width() - self.width()) // 2, geo.y() + 6)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(QColor(200, 30, 30))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
