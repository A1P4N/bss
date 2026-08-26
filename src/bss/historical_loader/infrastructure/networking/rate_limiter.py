"""RateLimiter strict pacing 5 RPS, interval=0.2s, capacity=1, monotonic."""

from __future__ import annotations

from .clock import Clock


class RateLimiter:
    """Strict pacing: each acquire not earlier than last + interval.

    No burst — capacity=1. Monotonic clock only (not UTC).
    """

    def __init__(self, rps: float, clock: Clock, capacity: int = 1):
        if rps <= 0:
            raise ValueError("rps must be >0")
        if capacity != 1:
            # per final plan, strict pacing capacity=1
            raise ValueError("capacity must be 1 for strict pacing")
        self._interval = 1.0 / float(rps)
        self._clock = clock
        self._capacity = int(capacity)
        # next allowed start time
        self._next_allowed: float = clock.monotonic()

    def acquire(self) -> None:
        now = self._clock.monotonic()
        if now < self._next_allowed:
            to_sleep = self._next_allowed - now
            self._clock.sleep(to_sleep)
            now = self._clock.monotonic()
        # consume token: next allowed is now + interval
        self._next_allowed = now + self._interval
