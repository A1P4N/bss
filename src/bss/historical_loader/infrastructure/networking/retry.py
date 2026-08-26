"""RetryPolicy — deterministic, no HTTP, no DownloadJob knowledge."""

from __future__ import annotations

from typing import Callable, TypeVar

from ...domain.errors import PermanentError, RetryableError, RetryExhaustedError
from .clock import Clock

T = TypeVar("T")


class RetryPolicy:
    """Retries only RetryableError, capped attempts, deterministic backoff, Retry-After support."""

    def __init__(
        self,
        max_attempts: int = 5,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        factor: float = 2.0,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >=1")
        if initial_delay <= 0 or max_delay <= 0 or factor < 1:
            raise ValueError("invalid backoff params")
        self.max_attempts = int(max_attempts)
        self.initial_delay = float(initial_delay)
        self.max_delay = float(max_delay)
        self.factor = float(factor)

    def backoff(self, attempt: int) -> float:
        """Attempt is 1-indexed next attempt number. For attempt=2 → initial, 3→ initial*factor, etc."""
        if attempt <= 1:
            return 0.0
        # attempt=2 => exponent 0 => initial, attempt=3 => initial*factor
        exp = attempt - 2
        delay = self.initial_delay * (self.factor ** exp)
        if delay > self.max_delay:
            delay = self.max_delay
        return float(delay)

    def _choose_delay(self, err: RetryableError, next_attempt: int) -> float:
        ra = getattr(err, "retry_after", None)
        if isinstance(ra, (int, float)) and 0 < float(ra) <= self.max_delay:
            return float(ra)
        return self.backoff(next_attempt)

    def execute(self, operation: Callable[[], T], clock: Clock) -> T:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return operation()
            except RetryableError as e:
                last_exc = e
                if attempt == self.max_attempts:
                    break
                delay = self._choose_delay(e, attempt + 1)
                clock.sleep(delay)
                continue
            except PermanentError:
                raise
            except Exception:
                # non-typed exceptions are treated as permanent (no retry) to avoid hiding
                raise
        # exhausted
        raise RetryExhaustedError(
            message=f"retry exhausted after {self.max_attempts} attempts: {last_exc}",
            context={"max_attempts": self.max_attempts, "last_error": str(last_exc) if last_exc else ""},
        )
