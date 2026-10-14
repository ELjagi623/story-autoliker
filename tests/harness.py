"""End-to-end backends.

* ``RealBackend``  - real mss screenshots + real pyautogui mouse (needs an unlocked display).
* ``QtBackend``    - the same Runner/Matcher/mock window, but screenshots are taken from the Qt
  widget and clicks are delivered as Qt mouse events. Works offscreen / headless, so the whole
  application flow stays testable when no display is available. Only the thin OS layer
  (mss + pyautogui) is not exercised by it.

Both run the Runner in a worker thread while the main thread pumps Qt events, exactly like the app.
"""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QMetaObject, QObject, QPoint, QThread, Qt, Slot
from PySide6.QtTest import QTest

from clickflow.gui.qtutils import qimage_to_bgr
from clickflow.inputs import InputProvider, PyAutoGuiInput
from clickflow.screen import Frame, MssScreen, Rect, ScreenProvider


class _Marshal(QObject):
    """Runs a callable on the thread this object lives in (the GUI thread) and waits for the result."""

    def __init__(self) -> None:
        super().__init__()
        self._fn = None
        self.result = None
        self.error = None

    @Slot()
    def _run(self) -> None:
        try:
            self.result = self._fn()
            self.error = None
        except Exception as exc:  # re-raised in the calling thread
            self.error = exc

    def call(self, fn):
        if QThread.currentThread() is self.thread():
            return fn()
        self._fn = fn
        QMetaObject.invokeMethod(self, "_run", Qt.ConnectionType.BlockingQueuedConnection)
        if self.error:
            raise self.error
        return self.result


class WidgetScreen(ScreenProvider):
    def __init__(self, widget, marshal: _Marshal) -> None:
        self.widget, self.marshal = widget, marshal

    def grab(self) -> Frame:
        img, dpr = self.marshal.call(lambda: (qimage_to_bgr(self.widget.grab().toImage()),
                                              self.widget.devicePixelRatioF()))
        return Frame(img, 0.0, 0.0, dpr, dpr)

    def bounds(self) -> Rect:
        return Rect(0, 0, self.widget.width(), self.widget.height())


class WidgetInput(InputProvider):
    def __init__(self, widget, marshal: _Marshal) -> None:
        self.widget, self.marshal = widget, marshal
        self.pos = (widget.width() / 2.0, widget.height() / 2.0)  # not in a corner
        self.keys: list[str] = []

    def click(self, x: float, y: float, button: str = "left", clicks: int = 1) -> None:
        btn = Qt.MouseButton.RightButton if button == "right" else Qt.MouseButton.LeftButton
        self.pos = (x, y)

        def do():
            for _ in range(clicks):
                QTest.mouseClick(self.widget, btn, Qt.KeyboardModifier.NoModifier, QPoint(round(x), round(y)))

        self.marshal.call(do)

    def press_key(self, key: str) -> None:
        self.keys.append(key)

    def mouse_position(self) -> tuple[float, float]:
        return self.pos


class QtBackend:
    name = "qt"

    def __init__(self, qapp) -> None:
        self.qapp = qapp
        self.marshal = _Marshal()  # created in the GUI thread
        self.inputs: WidgetInput | None = None

    def providers(self, win):
        self.inputs = WidgetInput(win, self.marshal)
        return WidgetScreen(win, self.marshal), self.inputs

    def move_mouse_to_corner(self) -> None:
        self.inputs.pos = (0.0, 0.0)

    def patch_gui(self, monkeypatch, win) -> None:
        import clickflow.gui.main_window as mw

        monkeypatch.setattr(mw, "MssScreen", lambda *a, **k: self.providers(win)[0])
        monkeypatch.setattr(mw, "PyAutoGuiInput", lambda *a, **k: self.providers(win)[1])


class RealBackend:
    name = "real"

    def __init__(self, qapp) -> None:
        import pyautogui

        pyautogui.FAILSAFE = False
        self.qapp = qapp
        self._start = pyautogui.position()

    def providers(self, win):
        return MssScreen(0), PyAutoGuiInput()

    def move_mouse_to_corner(self) -> None:
        import pyautogui

        pyautogui.moveTo(0, 0)

    def patch_gui(self, monkeypatch, win) -> None:
        pass  # the GUI uses the real providers already

    def restore(self) -> None:
        import pyautogui

        pyautogui.moveTo(self._start.x, self._start.y)


def pump(app, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def run_in_thread(app, runner, *, on_tick=None, timeout: float = 90):
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("r", runner.run()), daemon=True)
    th.start()
    end = time.monotonic() + timeout
    while th.is_alive() and time.monotonic() < end:
        app.processEvents()
        if on_tick:
            on_tick()
        time.sleep(0.005)
    if th.is_alive():
        runner.request_stop()
        th.join(5)
        raise AssertionError("run did not finish in time")
    return out["r"]


# ---------------------------------------------------------------- two fake monitors made of two Qt windows

from clickflow.screen import MonitorInfo  # noqa: E402


class WidgetMultiScreen(ScreenProvider):
    """Monitors = Qt widgets placed at different desktop origins (so they can differ in resolution)."""

    def __init__(self, monitors: dict, marshal: _Marshal, primary: int = 1) -> None:
        self.mons = monitors  # index -> (widget, left, top)
        self.marshal, self.primary, self.current = marshal, primary, primary
        self.grabs: list[int] = []

    def _cur(self) -> int:
        return self.current if self.current in self.mons else min(self.mons)

    def grab(self) -> Frame:
        idx = self._cur()
        self.grabs.append(idx)
        w, left, top = self.mons[idx]
        img, dpr = self.marshal.call(lambda: (qimage_to_bgr(w.grab().toImage()), w.devicePixelRatioF()))
        return Frame(img, float(left), float(top), dpr, dpr)

    def bounds(self) -> Rect:
        w, left, top = self.mons[self._cur()]
        return Rect(left, top, w.width(), w.height())

    def monitors(self) -> list[MonitorInfo]:
        return [MonitorInfo(i, l, t, w.width(), w.height(), i == self.primary)
                for i, (w, l, t) in sorted(self.mons.items())]

    def set_monitor(self, index: int) -> None:
        self.current = index


class WidgetMultiInput(InputProvider):
    def __init__(self, screen: WidgetMultiScreen) -> None:
        self.screen = screen
        self.pos = (300.0, 200.0)  # inside monitor 1, far from any corner

    def click(self, x: float, y: float, button: str = "left", clicks: int = 1) -> None:
        for _idx, (w, left, top) in self.screen.mons.items():
            if left <= x < left + w.width() and top <= y < top + w.height():
                btn = Qt.MouseButton.RightButton if button == "right" else Qt.MouseButton.LeftButton

                def do(w=w, lx=round(x - left), ly=round(y - top)):
                    for _ in range(clicks):
                        QTest.mouseClick(w, btn, Qt.KeyboardModifier.NoModifier, QPoint(lx, ly))

                self.pos = (x, y)
                self.screen.marshal.call(do)
                return

    def press_key(self, key: str) -> None:
        pass

    def mouse_position(self) -> tuple[float, float]:
        return self.pos


class QtMultiBackend:
    name = "qt-multi"

    def __init__(self, qapp) -> None:
        self.marshal = _Marshal()
        self.qapp = qapp

    def providers(self, wins: dict):
        screen = WidgetMultiScreen(wins, self.marshal)
        return screen, WidgetMultiInput(screen)
