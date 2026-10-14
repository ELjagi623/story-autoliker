"""Input widgets that ignore the mouse wheel unless they have keyboard focus.

Qt's default: scrolling the wheel over a combo box or spin box *changes its value*. In a scrolling form that
silently flips settings (e.g. "Left click" -> "Right click") while the user is only scrolling the page.
These widgets only react to the wheel after being clicked/tabbed into; otherwise the wheel event is ignored so
the enclosing scroll area scrolls instead.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSlider, QSpinBox


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
