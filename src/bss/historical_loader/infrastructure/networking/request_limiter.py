"""RequestLimiter — composition Rate + Concurrency, exception/cancellation-safe."""

from __future__ import annotations

from typing import Callable, TypeVar

from .concurrency_limiter import ConcurrencyLimiter
from .rate_limiter import RateLimiter

T = TypeVar("T")


class RequestLimiter:
    """Combines strict RPS and max_parallel with safe lifecycle:

    rate.acquire() → concurrency.acquire() → operation() → concurrency.release() (finally)
    rate token not released (consumed).
    If concurrency.acquire() raises, no release.
    """

    def __init__(self, rate_limiter: RateLimiter, concurrency_limiter: ConcurrencyLimiter):
        self._rate = rate_limiter
        self._concurrency = concurrency_limiter

    def execute(self, operation: Callable[[], T]) -> T:
        self._rate.acquire()
        acquired = False
        try:
            self._concurrency.acquire()
            acquired = True
            return operation()
        finally:
            if acquired:
                self._concurrency.release()
