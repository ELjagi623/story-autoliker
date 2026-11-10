"""Input widgets and the small custom controls of the ClickFlow design system.

Wheel safety: combo boxes, spin boxes and sliders ignore the mouse wheel unless they have keyboard focus.
Qt's default (scrolling over a combo box *changes its value*) silently flips settings (e.g. "Left click" ->
"Right click") while the user is only scrolling the page.

Custom controls (Switch, Segmented, Pill, Alert, Group, ThresholdSlider, HotkeyEdit, ...) read their colours from
``theme.tok`` at paint time, so a theme switch only needs a repaint.
"""
from __future__ import annotations

import weakref
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QSizePolicy, QSlider, QSpinBox, QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout, QWidget,
)

from . import icons, theme
from .i18n import tr

# ============================================================================ wheel-safe inputs


class _WheelGuard:
    def _guard_init(self) -> None:
        # Click or Tab gives focus; the wheel alone never does.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()  # lets the parent (the scroll area) handle it


class SafeComboBox(_WheelGuard, QComboBox):
    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self._guard_init()


class SafeSpinBox(_WheelGuard, QSpinBox):
    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self._guard_init()


class SafeDoubleSpinBox(_WheelGuard, QDoubleSpinBox):
    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self._guard_init()


class SafeSlider(_WheelGuard, QSlider):
    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self._guard_init()


# ============================================================================ theme-aware icons

_themed: "weakref.WeakSet" = weakref.WeakSet()


def _refresh_themed() -> None:
    for w in list(_themed):
        try:
            w.refresh_theme()
        except RuntimeError:  # the C++ object is already gone
            pass


theme.on_change(_refresh_themed)


class _IconSlot:
    """A button's icon that is re-rendered when the theme changes."""

    def __init__(self, btn: QAbstractButton, name: str, token: str, size: int, stroke: float) -> None:
        self.btn, self.name, self.token, self.size, self.stroke = btn, name, token, size, stroke

    def apply(self) -> None:
        self.btn.setIcon(icons.icon(self.name, theme.tok(self.token), self.size, self.stroke))
        self.btn.setIconSize(QSize(self.size, self.size))


class _Refresher:
    def __init__(self) -> None:
        self.slots: "weakref.WeakKeyDictionary[QAbstractButton, _IconSlot]" = weakref.WeakKeyDictionary()

    def refresh_theme(self) -> None:
        for s in list(self.slots.values()):
            try:
                s.apply()
            except RuntimeError:
                pass


_icon_refresher = _Refresher()
_themed.add(_icon_refresher)


def set_icon(btn: QAbstractButton, name: str, token: str = "tx", size: int = 16, stroke: float = 1.75) -> None:
    slot = _IconSlot(btn, name, token, size, stroke)
    _icon_refresher.slots[btn] = slot
    slot.apply()


_VARIANT_ICON_TOKEN = {"primary": "on_ac", "danger": "on_dg", "ghost": "tx2", "": "tx"}


def button(text: str = "", icon: str = "", variant: str = "", size: str = "", tip: str = "",
           on_click: Optional[Callable] = None) -> QPushButton:
    """A design-system push button. ``variant``: "" | primary | danger | ghost | link; ``size``: "" | sm | lg."""
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if size:
        b.setProperty("size", size)
    if icon:
        set_icon(b, icon, _VARIANT_ICON_TOKEN.get(variant, "tx"), 18 if size == "lg" else 16)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if on_click:
        b.clicked.connect(on_click)
    return b


def icon_button(icon: str, tip: str = "", variant: str = "ghost", size: str = "", on_click: Optional[Callable] = None,
                token: str = "") -> QToolButton:
    b = QToolButton()
    b.setProperty("btn", True)
    b.setProperty("icononly", True)
    if variant:
        b.setProperty("variant", variant)
    if size:
        b.setProperty("size", size)
    set_icon(b, icon, token or _VARIANT_ICON_TOKEN.get(variant, "tx"), 16)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    if on_click:
        b.clicked.connect(on_click)
    return b


def label(text: str = "", role: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    if wrap:
        lb.setWordWrap(True)
    return lb


def tag(text: str, tone: str = "") -> QLabel:
    lb = QLabel(text)
    lb.setProperty("tag", tone)
    return lb


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def hline() -> QFrame:
    f = QFrame()
    f.setProperty("sep", True)
    f.setFixedHeight(1)
    return f


# ============================================================================ switch

def paint_switch(p: QPainter, r: QRect, on: bool, enabled: bool = True) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if not enabled:
        p.setOpacity(0.42)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.qcolor("sw_on" if on else "sw_off"))  # iOS-style green when on
    p.drawRoundedRect(QRectF(r), r.height() / 2, r.height() / 2)
    d = r.height() - 4
    x = r.right() - d - 1 if on else r.left() + 2
    p.setBrush(QColor("#FFFFFF") if on else theme.qcolor("sw_th"))
    p.drawEllipse(QRectF(x, r.top() + 2, d, d))
    p.restore()


class Switch(QAbstractButton):
    """36x20 toggle. Same API as a QCheckBox (isChecked / setChecked / toggled)."""

    def __init__(self, checked: bool = False) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(36, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(36, 20)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        paint_switch(p, self.rect(), self.isChecked(), self.isEnabled())
        if self.hasFocus():
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(theme.qcolor("fc"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(-1, -1, 1, 1), 11, 11)
        p.end()


class SwitchRow(QWidget):
    """Switch + bold title (+ small grey subtitle). ``.switch`` is the underlying toggle."""

    def __init__(self, title: str, sub: str = "") -> None:
        super().__init__()
        self.switch = Switch()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignTop if sub else Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight: 600;")
        col.addWidget(self.title)
        self.sub = label(sub, "hint")
        self.sub.setVisible(bool(sub))
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.title.mousePressEvent = lambda e: self.switch.toggle() if self.switch.isEnabled() else None


# ============================================================================ segmented control

class Segmented(QFrame):
    """Pill-shaped single-choice control. Mirrors the part of QComboBox the editors use
    (addItem / currentData / setCurrentIndex / findData / currentIndexChanged)."""

    currentIndexChanged = Signal(int)

    def __init__(self, fill: bool = True) -> None:
        super().__init__()
        self.setProperty("seg", True)
        self._fill = fill
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns: list[QToolButton] = []
        self._data: list[object] = []
        self._current = -1
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(0)
        self._lay = lay

    def addItem(self, text: str, data: object = None) -> None:  # noqa: N802
        b = QToolButton()
        b.setProperty("seg", True)
        b.setText(text)
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        if self._fill:
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        i = len(self._btns)
        self._btns.append(b)
        self._data.append(data)
        self._group.addButton(b, i)
        b.clicked.connect(lambda _=False, idx=i: self.setCurrentIndex(idx))
        self._lay.addWidget(b, 1 if self._fill else 0)
        if self._current < 0:
            self.setCurrentIndex(0)

    def setItemText(self, i: int, text: str) -> None:  # noqa: N802
        self._btns[i].setText(text)

    def count(self) -> int:
        return len(self._btns)

    def currentIndex(self) -> int:  # noqa: N802
        return self._current

    def currentData(self) -> object:  # noqa: N802
        return self._data[self._current] if 0 <= self._current < len(self._data) else None

    def findData(self, data: object) -> int:  # noqa: N802
        return self._data.index(data) if data in self._data else -1

    def setCurrentIndex(self, i: int) -> None:  # noqa: N802
        if not (0 <= i < len(self._btns)):
            return
        changed = i != self._current
        self._current = i
        for k, b in enumerate(self._btns):
            b.setChecked(k == i)
        if changed:
            self.currentIndexChanged.emit(i)

    def setCurrentData(self, data: object) -> None:  # noqa: N802
        self.setCurrentIndex(max(0, self.findData(data)))

    def clearSelection(self) -> None:  # noqa: N802
        """No segment selected (e.g. the speed slider sits between the presets)."""
        if self._current < 0:
            return
        self._current = -1
        self._group.setExclusive(False)
        for b in self._btns:
            b.setChecked(False)
        self._group.setExclusive(True)


class TabStrip(QFrame):
    """Underlined tabs (Step settings | Global settings)."""

    currentChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("bare", True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._lay = lay
        self._group = QButtonGroup(self)
        self._btns: list[QToolButton] = []
        self._cur = -1

    def add(self, text: str, extra: QWidget | None = None) -> QToolButton:
        b = QToolButton()
        b.setProperty("tab", True)
        b.setText(text)
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        i = len(self._btns)
        self._btns.append(b)
        self._group.addButton(b, i)
        b.clicked.connect(lambda _=False, idx=i: self.setCurrentIndex(idx))
        self._lay.addWidget(b)
        if extra is not None:
            self._lay.addWidget(extra)
        if self._cur < 0:
            self.setCurrentIndex(0)
        return b

    def finish(self) -> None:
        self._lay.addStretch(1)

    def currentIndex(self) -> int:  # noqa: N802
        return self._cur

    def setCurrentIndex(self, i: int) -> None:  # noqa: N802
        if not (0 <= i < len(self._btns)):
            return
        self._cur = i
        for k, b in enumerate(self._btns):
            b.setChecked(k == i)
        self.currentChanged.emit(i)

    def setTabText(self, i: int, text: str) -> None:  # noqa: N802
        self._btns[i].setText(text)


# ============================================================================ status pill, alert, tile, meter

_PILL = {  # kind -> (background token, text/dot token)
    "idle": ("inp", "tx2"), "run": ("ok_bg", "ok"), "cdn": ("ac_soft", "ac_tx"), "dry": ("inf_bg", "inf"),
    "sto": ("wn_bg", "wn"), "err": ("er_bg", "er"),
}


class Pill(QWidget):
    """Status capsule with a coloured dot: idle / run / cdn (countdown) / dry / sto (stopped) / err."""

    def __init__(self, kind: str = "idle", text: str = "", big: bool = False) -> None:
        super().__init__()
        self._kind, self._text, self._big = kind, text, big
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_state(self, kind: str, text: str) -> None:
        self._kind, self._text = kind, text
        self.updateGeometry()
        self.update()

    def kind(self) -> str:
        return self._kind

    def text(self) -> str:
        return self._text

    def _font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(14 if self._big else 12)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    def sizeHint(self) -> QSize:  # noqa: N802
        w = QFontMetrics(self._font()).horizontalAdvance(self._text)
        return QSize(w + (46 if self._big else 40), 36 if self._big else 28)

    def paintEvent(self, _e) -> None:  # noqa: N802
        bg, fg = _PILL.get(self._kind, _PILL["idle"])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(theme.qcolor(bg))
        p.setPen(QPen(theme.qcolor("bd"), 1) if self._kind == "idle" else Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor("tx3" if self._kind == "idle" else fg))
        cx = 15 if self._big else 14
        p.drawEllipse(QPointF(cx, r.height() / 2 + 0.5), 4, 4)
        p.setPen(theme.qcolor(fg))
        p.setFont(self._font())
        p.drawText(QRectF(cx + 10, 0, self.width() - cx - 10, self.height()), Qt.AlignmentFlag.AlignVCenter, self._text)
        p.end()


_ALERT_ICON = {"info": ("info", "inf"), "ok": ("ok", "ok"), "wn": ("warn", "wn"), "er": ("err", "er")}


class Alert(QFrame):
    """Coloured note bar: tone is info | ok | wn | er. Optional link-style action on the right."""

    def __init__(self, text: str = "", tone: str = "info", action: str = "") -> None:
        super().__init__()
        self._tone = tone
        self.setProperty("alert", tone)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFixedSize(16, 16)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size: 12.5px;")
        lay.addWidget(self.label, 1)
        self.action = button(action, variant="link")
        self.action.setStyleSheet("font-size: 12.5px;")
        self.action.setVisible(bool(action))
        lay.addWidget(self.action, 0, Qt.AlignmentFlag.AlignTop)
        _themed.add(self)
        self.refresh_theme()

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        self.setProperty("alert", tone)
        repolish(self)
        self.refresh_theme()

    def set_text(self, text: str) -> None:
        self.label.setText(text)

    def text(self) -> str:
        return self.label.text()

    def tone(self) -> str:
        return self._tone

    def refresh_theme(self) -> None:
        name, token = _ALERT_ICON.get(self._tone, _ALERT_ICON["info"])
        self.icon.setPixmap(icons.pixmap(name, theme.tok(token), 16, 2.0))


class Tile(QFrame):
    """Dashboard number tile: caption, big value, small footnote."""

    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setProperty("tile", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(0)
        self.k = label(caption, "field")
        self.n = label("0", "num")
        self.s = label("", "hint")
        lay.addWidget(self.k)
        lay.addWidget(self.n)
        lay.addWidget(self.s)

    def set(self, value: str, note: str = "") -> None:
        self.n.setText(value)
        self.s.setText(note)


class MatchMeter(QWidget):
    """Confidence bar 0.50..1.00 with a tick at the threshold."""

    def __init__(self) -> None:
        super().__init__()
        self._v, self._thr = 0.0, 0.85
        self.setFixedHeight(18)

    def set(self, value: float, threshold: float) -> None:
        self._v, self._thr = value, threshold
        self.update()

    @staticmethod
    def _pos(v: float) -> float:
        return max(0.0, min(1.0, (v - 0.5) / 0.5))

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 4.5, self.width() - 1, 9)
        p.setBrush(theme.qcolor("inp"))
        p.setPen(QPen(theme.qcolor("bd"), 1))
        p.drawRoundedRect(r, 4.5, 4.5)
        w = r.width() * self._pos(self._v)
        if w > 1:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor("ok" if self._v >= self._thr else "wn"))
            p.drawRoundedRect(QRectF(r.left(), r.top(), w, r.height()), 4.5, 4.5)
        x = r.left() + r.width() * self._pos(self._thr)
        p.setPen(QPen(theme.qcolor("tx"), 2))
        p.drawLine(QPointF(x, 1), QPointF(x, 17))
        p.end()


# ============================================================================ collapsible group

class Group(QFrame):
    """Card with a clickable header (chevron, title, optional tag, optional right-hand widget) and a collapsible body."""

    toggled_open = Signal(bool)

    def __init__(self, title: str, open_: bool = True, right: QWidget | None = None) -> None:
        super().__init__()
        self.setProperty("card", True)
        self._open = open_
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 2, 10, 0)
        root.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self.head_btn = QToolButton()
        self.head_btn.setProperty("grouphead", True)
        self.head_btn.setText("  " + title.replace("&", "&&"))
        self.head_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.head_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.head_btn.setIconSize(QSize(16, 16))
        self.head_btn.clicked.connect(lambda: self.set_open(not self._open))
        head.addWidget(self.head_btn)
        self.tag = tag("", "ok")
        self.tag.setVisible(False)
        head.addWidget(self.tag)
        head.addStretch(1)
        self.right = right
        if right is not None:
            head.addWidget(right)
        root.addLayout(head)
        self.body = QWidget()
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(10, 2, 6, 16)
        self.body_lay.setSpacing(14)
        root.addWidget(self.body)
        self.body.setVisible(open_)
        _themed.add(self)
        self.refresh_theme()

    def set_title(self, title: str) -> None:
        self.head_btn.setText("  " + title.replace("&", "&&"))

    def set_tag(self, text: str = "", tone: str = "ok") -> None:
        self.tag.setVisible(bool(text))
        self.tag.setText(text)
        self.tag.setProperty("tag", tone)
        repolish(self.tag)

    def is_open(self) -> bool:
        return self._open

    def set_open(self, on: bool) -> None:
        self._open = on
        self.body.setVisible(on)
        self.refresh_theme()
        self.toggled_open.emit(on)

    def refresh_theme(self) -> None:
        self.head_btn.setIcon(icons.icon("chevd" if self._open else "chevr", theme.tok("tx3"), 16, 1.75))

    def add(self, w: QWidget | QHBoxLayout | QVBoxLayout) -> None:
        if isinstance(w, QWidget):
            self.body_lay.addWidget(w)
        else:
            self.body_lay.addLayout(w)


def field(caption: str, widget: QWidget, hint: str = "") -> QWidget:
    """Caption above a control (the design's ``.fld``)."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    cap = label(caption, "field")
    lay.addWidget(cap)
    lay.addWidget(widget)
    if hint:
        lay.addWidget(label(hint, "hint", True))
    w.caption = cap  # type: ignore[attr-defined]
    return w


# ============================================================================ threshold slider (0.50 .. 1.00)

class ThresholdSlider(QWidget):
    """Match-strictness slider with a float API: ``value()`` / ``setValue(0.93)`` / ``valueChanged(float)``."""

    valueChanged = Signal(float)

    def __init__(self, title: str = "", lo: float = 0.5, hi: float = 1.0) -> None:
        super().__init__()
        self._lo, self._hi = lo, hi
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.title = label(title, "field")
        self.readout = label("0.85", "mono")
        self.readout.setStyleSheet("font-weight: 600;")
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.readout)
        lay.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.low = label(tr("Loose"), "hint")
        self.high = label(tr("Strict"), "hint")
        self.slider = SafeSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(round(lo * 100)), int(round(hi * 100)))
        self.slider.setSingleStep(1)
        self.slider.setPageStep(5)
        self.slider.valueChanged.connect(self._changed)
        row.addWidget(self.low)
        row.addWidget(self.slider, 1)
        row.addWidget(self.high)
        lay.addLayout(row)
        self.setValue(0.85)

    def _changed(self, v: int) -> None:
        self.readout.setText(f"{v / 100:.2f}")
        self.valueChanged.emit(v / 100)

    def value(self) -> float:
        return self.slider.value() / 100

    def setValue(self, v: float) -> None:  # noqa: N802
        self.slider.setValue(int(round(max(self._lo, min(self._hi, v)) * 100)))
        self.readout.setText(f"{self.value():.2f}")

    def setToolTip(self, text: str) -> None:  # noqa: N802
        super().setToolTip(text)
        self.slider.setToolTip(text)


# ============================================================================ hotkey capture field

_QT_NAMES = {
    Qt.Key.Key_Space: "space", Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter", Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Backspace: "backspace", Qt.Key.Key_Delete: "delete", Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "pageup", Qt.Key.Key_PageDown: "pagedown", Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down",
    Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right", Qt.Key.Key_Insert: "insert", Qt.Key.Key_Pause: "pause",
}
_MOD_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr,
             Qt.Key.Key_CapsLock, Qt.Key.Key_NumLock}


def hotkey_from_event(ev) -> Optional[str]:
    """Qt key event -> text understood by ``hotkey.parse_hotkey`` ("F8", "ctrl+shift+s"); None for modifier-only."""
    k = Qt.Key(ev.key()) if ev.key() in {m.value for m in Qt.Key} else None
    if k is None or k in _MOD_KEYS:
        return None
    if Qt.Key.Key_F1 <= k <= Qt.Key.Key_F24:
        name = f"F{k.value - Qt.Key.Key_F1.value + 1}"
    elif k in _QT_NAMES:
        name = _QT_NAMES[k]
    elif Qt.Key.Key_A <= k <= Qt.Key.Key_Z or Qt.Key.Key_0 <= k <= Qt.Key.Key_9:
        name = chr(k.value).lower()
    else:
        return None
    mods = ev.modifiers()
    parts = [n for m, n in ((Qt.KeyboardModifier.ControlModifier, "ctrl"), (Qt.KeyboardModifier.AltModifier, "alt"),
                            (Qt.KeyboardModifier.ShiftModifier, "shift"), (Qt.KeyboardModifier.MetaModifier, "win"))
             if mods & m]
    return "+".join(parts + [name])


class HotkeyEdit(QLineEdit):
    """Click, then press the key (combination) you want. Esc cancels. ``editingFinished`` fires when a key is taken."""

    def __init__(self) -> None:
        super().__init__()
        self.setProperty("hotkey", True)
        self.setPlaceholderText(tr("Press the key you want..."))
        self.setReadOnly(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._before = ""

    def focusInEvent(self, e) -> None:  # noqa: N802
        self._before = self.text()
        super().focusInEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.setText(self._before)
            self.clearFocus()
            return
        name = hotkey_from_event(e)
        if name is None:
            return  # modifier alone / unsupported key: keep waiting
        self.setText(name)
        self.editingFinished.emit()

    def inputMethodEvent(self, e) -> None:  # noqa: N802
        e.ignore()


# ============================================================================ thumbnail

class Thumbnail(QLabel):
    """Dark tile showing a template image (or a placeholder icon). Hidden while a run is active (safety)."""

    def __init__(self, width: int = 120, height: int = 80) -> None:
        super().__init__()
        self.setProperty("thumbbox", True)
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._w, self._h = width, height
        self._pix: Optional[QPixmap] = None
        self._missing = ""
        _themed.add(self)

    def show_pixmap(self, pix: Optional[QPixmap], missing: str = "") -> None:
        self._pix, self._missing = pix, missing
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._pix is not None:
            p.setBrush(theme.qcolor("thumb"))
            p.setPen(QPen(theme.qcolor("bd2"), 1))
            p.drawRoundedRect(r, 10, 10)
            s = self._pix.scaled(int((self._w - 12) * 2), int((self._h - 12) * 2), Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            s.setDevicePixelRatio(2.0)
            p.drawPixmap(int((self._w - s.width() / 2) / 2), int((self._h - s.height() / 2) / 2), s)
        else:
            p.setBrush(theme.qcolor("inp"))
            pen = QPen(theme.qcolor("tx3"), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRoundedRect(r, 10, 10)
            ic = icons.pixmap("image", theme.tok("tx3"), 28, 2.0, 1.5)
            p.drawPixmap(int((self._w - 28) / 2), int((self._h - 28) / 2) - (6 if self._missing else 0), ic)
            if self._missing:
                p.setPen(theme.qcolor("tx3"))
                f = QFont(self.font())
                f.setPixelSize(11)
                p.setFont(f)
                p.drawText(QRectF(4, self._h - 22, self._w - 8, 18), Qt.AlignmentFlag.AlignCenter, self._missing)
        p.end()

    def refresh_theme(self) -> None:
        self.update()


class HatchedThumb(QLabel):
    """What replaces a hidden thumbnail while a run is active: diagonal hatching + a crossed-out eye."""

    def __init__(self, width: int = 120, height: int = 80) -> None:
        super().__init__()
        self.setFixedSize(width, height)

    def paintEvent(self, _e) -> None:  # noqa: N802
        paint_hatch(QPainter(self), QRectF(self.rect()), 10, icon_px=24)


def paint_hatch(p: QPainter, r: QRectF, radius: float, icon_px: int = 18) -> None:
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.save()
    rr = r.adjusted(0.5, 0.5, -0.5, -0.5)
    p.setBrush(theme.qcolor("inp"))
    p.setPen(QPen(theme.qcolor("bd2"), 1))
    p.drawRoundedRect(rr, radius, radius)
    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.addRoundedRect(rr, radius, radius)
    p.setClipPath(path)
    p.setPen(QPen(theme.qcolor("bd"), 1))
    x = rr.left() - rr.height()
    while x < rr.right():
        p.drawLine(QPointF(x, rr.bottom()), QPointF(x + rr.height(), rr.top()))
        x += 6
    p.restore()
    ic = icons.pixmap("eyeoff", theme.tok("tx3"), icon_px, 2.0, 1.5)
    p.drawPixmap(int(r.center().x() - icon_px / 2), int(r.center().y() - icon_px / 2), ic)
    p.end()


# ============================================================================ step list (card rows)

ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_VIEW = Qt.ItemDataRole.UserRole + 1

ROW_H = 72
CARD_H = 64


class StepDelegate(QStyledItemDelegate):
    """Paints one step as a card: grip, 44 px thumbnail, "N. name", tag chips and an on/off switch."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_key: Optional[str] = None  # id of the step the runner is on (green card)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), ROW_H)

    @staticmethod
    def switch_rect(card: QRect) -> QRect:
        return QRect(card.right() - 12 - 36, card.center().y() - 10, 36, 20)

    def paint(self, p: QPainter, option, index) -> None:
        view = index.data(ROLE_VIEW) or {}
        card = QRect(option.rect.x() + 1, option.rect.y() + 1, option.rect.width() - 2, CARD_H)
        enabled_row = bool(option.state & QStyle.StateFlag.State_Enabled)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        running_here = index.data(ROLE_ID) == self.current_key and self.current_key is not None
        on = bool(view.get("enabled", True))
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not enabled_row and not running_here:
            p.setOpacity(0.7)
        if running_here:
            bg, border = theme.qcolor("ok_bg"), theme.qcolor("ok")
        elif selected:
            bg, border = theme.qcolor("ac_soft"), theme.qcolor("fc")
        elif hover and enabled_row:
            bg, border = theme.qcolor("hv"), theme.qcolor("bd")
        else:
            bg, border = theme.qcolor("cd"), theme.qcolor("bd")
        p.setBrush(bg)
        p.setPen(QPen(border, 1.5 if (selected or running_here) else 1))
        p.drawRoundedRect(QRectF(card).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        # grip
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor("tx3"))
        gx, gy = card.x() + 12, card.center().y() - 6
        for dx in (0, 5):
            for dy in (0, 5, 10):
                p.drawEllipse(QPointF(gx + dx, gy + dy), 1.1, 1.1)
        # thumbnail
        tr_ = QRectF(card.x() + 28, card.y() + 10, 44, 44)
        if not on:
            p.setOpacity(p.opacity() * 0.5)
        pix = view.get("thumb")
        if view.get("hidden"):
            paint_hatch_inline(p, tr_)
        elif pix is not None:
            p.setBrush(theme.qcolor("thumb"))
            p.setPen(QPen(theme.qcolor("bd2"), 1))
            p.drawRoundedRect(tr_.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            s = pix.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            s.setDevicePixelRatio(2.0)
            p.drawPixmap(int(tr_.center().x() - s.width() / 4), int(tr_.center().y() - s.height() / 4), s)
        else:
            p.setBrush(theme.qcolor("inp"))
            p.setPen(QPen(theme.qcolor("tx3"), 1, Qt.PenStyle.DashLine))
            p.drawRoundedRect(tr_.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            p.drawPixmap(int(tr_.center().x() - 11), int(tr_.center().y() - 11),
                         icons.pixmap("image", theme.tok("tx3"), 22, 2.0, 1.5))
        # name
        font = QFont(option.font)
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        left = card.x() + 84
        right = self.switch_rect(card).left() - 10
        idx_txt = f"{view.get('index', index.row() + 1)}  "
        fm = QFontMetrics(font)
        p.setPen(theme.qcolor("tx3"))
        p.drawText(QRect(left, card.y() + 10, 40, 20), Qt.AlignmentFlag.AlignVCenter, idx_txt.strip())
        nx = left + fm.horizontalAdvance(idx_txt) - 2
        p.setPen(theme.qcolor("tx"))
        name = fm.elidedText(str(view.get("name", "")), Qt.TextElideMode.ElideRight, max(20, right - nx))
        p.drawText(QRect(nx, card.y() + 10, right - nx, 20), Qt.AlignmentFlag.AlignVCenter, name)
        # tag chips
        small = QFont(option.font)
        small.setPixelSize(10)
        small.setWeight(QFont.Weight.DemiBold)
        p.setFont(small)
        sfm = QFontMetrics(small)
        x = left
        for text, tone in view.get("tags", []):
            w = sfm.horizontalAdvance(text) + 14
            if x + w > right:
                break
            r = QRectF(x, card.y() + 36, w, 18)
            bgk, fgk = _TAG.get(tone, _TAG[""])
            p.setPen(QPen(theme.qcolor("bd"), 1) if tone == "" else Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(bgk))
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
            p.setPen(theme.qcolor(fgk))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
            x += w + 4
        p.restore()
        # switch (drawn at full opacity so it stays readable; dimmed when the list is locked)
        p.save()
        paint_switch(p, self.switch_rect(card), on, enabled_row)
        p.restore()

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            card = QRect(option.rect.x() + 1, option.rect.y() + 1, option.rect.width() - 2, CARD_H)
            if self.switch_rect(card).adjusted(-4, -4, 4, 4).contains(event.position().toPoint()):
                cur = index.data(Qt.ItemDataRole.CheckStateRole)
                checked = int(getattr(cur, "value", cur) or 0) == Qt.CheckState.Checked.value  # int or enum, by binding
                new = Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
                model.setData(index, new, Qt.ItemDataRole.CheckStateRole)
                return True
        return super().editorEvent(event, model, option, index)


_TAG = {"": ("inp", "tx2"), "ok": ("ok_bg", "ok"), "wn": ("wn_bg", "wn"), "er": ("er_bg", "er"), "if": ("inf_bg", "inf"),
        "ac": ("ac_soft", "ac_tx")}


def paint_hatch_inline(p: QPainter, r: QRectF) -> None:
    """Hatched placeholder drawn inside another paint pass (does not end the painter)."""
    from PySide6.QtGui import QPainterPath

    p.save()
    rr = r.adjusted(0.5, 0.5, -0.5, -0.5)
    p.setBrush(theme.qcolor("inp"))
    p.setPen(QPen(theme.qcolor("bd2"), 1))
    p.drawRoundedRect(rr, 8, 8)
    path = QPainterPath()
    path.addRoundedRect(rr, 8, 8)
    p.setClipPath(path)
    p.setPen(QPen(theme.qcolor("bd"), 1))
    x = rr.left() - rr.height()
    while x < rr.right():
        p.drawLine(QPointF(x, rr.bottom()), QPointF(x + rr.height(), rr.top()))
        x += 6
    p.restore()
    p.drawPixmap(int(r.center().x() - 10), int(r.center().y() - 10), icons.pixmap("eyeoff", theme.tok("tx3"), 20, 2.0, 1.5))


class StepList(QListWidget):
    """The steps as cards. Drag to reorder; the switch on each card enables / disables the step."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("steps")
        self.delegate = StepDelegate(self)
        self.setItemDelegate(self.delegate)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSpacing(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)

    def set_current_step(self, step_id: Optional[str]) -> None:
        self.delegate.current_key = step_id
        self.viewport().update()
