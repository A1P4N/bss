"""Clock abstraction — monotonic for RateLimiter/Retry (AGENTS §22)."""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FakeClock:
    """Deterministic clock for tests — monotonic, no real sleep."""

    def __init__(self, initial: float = 0.0):
        self._now = float(initial)
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self._now

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("sleep seconds must be >=0")
        self.sleeps.append(float(seconds))
        self._now += float(seconds)
