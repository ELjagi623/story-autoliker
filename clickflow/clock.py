"""Clock abstraction so the Runner's waits can be tested without real sleeping."""
from __future__ import annotations

import time


class Clock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class FakeClock(Clock):
    """Virtual time: sleep() advances the clock instantly and records the request."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.t += seconds
            self.sleeps.append(seconds)
