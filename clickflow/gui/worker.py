"""Background threads so the GUI never blocks."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from .. import runner as R
from ..runner import Event, RunResult, Runner


class RunThread(QThread):
    """Runs a Runner off the GUI thread; events are delivered as queued signals."""

    event = Signal(object)
    done = Signal(object)

    def __init__(self, runner: Runner) -> None:
        super().__init__()
        self.runner = runner
        runner.on_event = self._forward

    def _forward(self, ev: Event) -> None:
        self.event.emit(ev)

    def request_stop(self) -> None:
        self.runner.request_stop()

    def run(self) -> None:
        try:
            result = self.runner.run()
        except Exception as exc:  # Runner.run should never raise; belt and braces
            result = RunResult(R.ERROR, f"Unexpected error: {exc}")
        self.done.emit(result)


class CallThread(QThread):
    """Runs ``fn()`` in a thread and emits its return value (or the exception) when finished."""

    result = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.result.emit(self._fn())
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
