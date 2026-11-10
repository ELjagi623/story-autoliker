"""Full-screen overlays: the rectangle-capture overlay and the match highlighter."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .. import platform_utils
from .qtutils import bgr_to_pixmap

# Native overlays use plain colours (no theme): they must stay readable over any desktop, light or dark.
_FONT = "Segoe UI"
ACCENT = QColor("#34C759")
ORANGE = QColor("#FF9F1C")
FOUND = QColor("#1FBF75")
REGION = QColor("#B08CFF")
NAVY = QColor("#101418")
STOP_RED = QColor("#D1344A")
SCRIM = QColor(0, 0, 0, 150)


def _pill(p: QPainter, text: str, x: float, y: float, bg: QColor, fg: QColor, above: bool = True) -> None:
    """Small solid label glued to the top-left edge of a box (flips inside when it would leave the screen)."""
    font = QFont(_FONT, 9)
    font.setWeight(QFont.Weight.DemiBold)
    p.save()
    p.setFont(font)
    w = QFontMetrics(font).horizontalAdvance(text) + 14
    top = y - 22 if above and y >= 24 else y + 2
    r = QRectF(x, top, w, 20)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(r, 5, 5)
    p.setPen(fg)
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
    p.restore()


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
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(self.rect(), self._pix)
        p.fillRect(self.rect(), SCRIM)
        sel = self._sel()
        if sel and sel.width() > 0 and sel.height() > 0:
            sx, sy = self._pix.width() / self.width(), self._pix.height() / self.height()
            src = QRectF(sel.x() * sx, sel.y() * sy, sel.width() * sx, sel.height() * sy)
            p.drawPixmap(QRectF(sel), self._pix, src)  # un-dimmed hole
            p.setPen(QPen(ACCENT, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(sel)
            # 8 x 8 handles on the corners and edge midpoints
            p.setBrush(QColor(255, 255, 255))
            p.setPen(QPen(ACCENT, 1.5))
            for hx, hy in ((sel.left(), sel.top()), (sel.center().x(), sel.top()), (sel.right(), sel.top()),
                           (sel.left(), sel.center().y()), (sel.right(), sel.center().y()),
                           (sel.left(), sel.bottom()), (sel.center().x(), sel.bottom()), (sel.right(), sel.bottom())):
                p.drawRect(QRectF(hx - 4, hy - 4, 8, 8))
            _pill(p, f"{round(src.width())} × {round(src.height())} px", sel.x(), sel.y(), ACCENT, NAVY, above=True)
        self._paint_guides(p)
        # hint bar (top-left)
        font = QFont(_FONT, 13)
        p.setFont(font)
        w = QFontMetrics(font).horizontalAdvance(self._hint) + 32
        bar = QRectF(20, 20, w, 36)
        p.setPen(QPen(QColor("#464950"), 1))
        p.setBrush(QColor(20, 21, 23, 235))
        p.drawRoundedRect(bar, 18, 18)
        p.setPen(QColor(255, 255, 255))
        p.drawText(bar, Qt.AlignmentFlag.AlignCenter, self._hint)
        p.end()

    def _paint_guides(self, p: QPainter) -> None:
        if not self._guides:
            return
        sx, sy = self._pix.width() / self.width(), self._pix.height() / self.height()
        for x, y, w, h, label in self._guides:
            r = QRectF(x / sx, y / sy, w / sx, h / sy)
            col = ACCENT if label == "template" else ORANGE
            p.setPen(QPen(col, 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            _pill(p, label, r.x(), r.y(), col, NAVY, above=True)

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
        color = REGION if kind == "region" else (FOUND if found else ORANGE)
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
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for box, label, color, _, dashed in self._boxes:
            outer = box.adjusted(-4, -4, 4, 4)  # drawn outside the match so the target pixels stay untouched
            pen = QPen(color, 2 if dashed else 3, Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(outer)
            _pill(p, label, outer.x(), outer.y(), color, NAVY, above=True)
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
        self._text = f"STOP · {hotkey}" if hotkey else "STOP"
        geo = QGuiApplication.primaryScreen().geometry()
        self.move(geo.x() + (geo.width() - self.width()) // 2, geo.y() + 6)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(STOP_RED)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 22, 22)
        font = QFont(_FONT, 11)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        fm = QFontMetrics(font)
        total = 14 + 12 + fm.horizontalAdvance(self._text)
        x0 = (self.width() - total) / 2
        p.setPen(QPen(QColor(255, 255, 255), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x0, self.height() / 2 - 7, 14, 14), 3, 3)  # the "stop" square glyph
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x0 + 26, 0, total, self.height()), Qt.AlignmentFlag.AlignVCenter, self._text)
        p.end()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
