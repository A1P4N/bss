"""ConcurrencyLimiter — max_parallel, real synchronization primitive."""

from __future__ import annotations

import threading


class ConcurrencyLimiter:
    """Semaphore-based, tracks in_flight for tests."""

    def __init__(self, max_parallel: int):
        if max_parallel <= 0:
            raise ValueError("max_parallel must be >0")
        self._max = int(max_parallel)
        self._sem = threading.Semaphore(self._max)
        self._lock = threading.Lock()
        self._in_flight = 0
        self._max_observed = 0

    def acquire(self) -> None:
        self._sem.acquire()
        with self._lock:
            self._in_flight += 1
            if self._in_flight > self._max_observed:
                self._max_observed = self._in_flight
            if self._in_flight > self._max:
                # should not happen due to semaphore, but guard
                raise RuntimeError("in_flight exceeds max_parallel")

    def release(self) -> None:
        with self._lock:
            self._in_flight -= 1
            if self._in_flight < 0:
                raise RuntimeError("release without acquire")
        self._sem.release()

    def in_flight(self) -> int:
        with self._lock:
            return self._in_flight

    @property
    def max_observed(self) -> int:
        with self._lock:
            return self._max_observed
