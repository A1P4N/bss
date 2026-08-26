"""Typed errors for Loader domain (08_RULES §7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class LoaderError(Exception):
    """Base class for loader domain errors."""

    code: str
    message: str
    context: Dict[str, Any]

    def __str__(self) -> str:
        return f"[{self.code}] {self.message} context={self.context}"


class NormalizationError(LoaderError):
    """Raised when raw candle cannot be normalized to Candle."""



class ValidationError(LoaderError):
    """Raised for validation-specific failures (optional, ValidationResult preferred)."""



class DuplicateError(ValidationError):
    """Duplicate candle detected."""


class GapError(ValidationError):
    """Gap detected (missing candles)."""


class StorageError(LoaderError):
    """Storage layer error (atomicity, checksum, immutability)."""


class ImmutableViolation(StorageError):
    """Attempt to mutate published READY version."""


class CorruptChunkError(StorageError):
    """Chunk is partially written or checksum mismatch."""


# ── Retry / RateLimit taxonomy (not HTTP-specific) ─────────────────


class RetryableError(LoaderError):
    """Transient, retryable. Adapter maps 429/5xx/timeout/network → this."""

    retry_after: float | None = None  # seconds, if from Retry-After header

    def __init__(self, code: str, message: str, context: dict, retry_after: float | None = None):
        super().__init__(code=code, message=message, context=context)
        # set per-instance to avoid dataclass frozen issues
        object.__setattr__(self, "retry_after", retry_after)  # type: ignore


class RateLimitedError(RetryableError):
    """429 Too Many Requests — retryable with optional Retry-After."""

    def __init__(self, message: str = "rate limited (429)", context: dict | None = None, retry_after: float | None = None):
        super().__init__(code="RATE_LIMITED", message=message, context=context or {}, retry_after=retry_after)


class TemporaryServerError(RetryableError):
    """5xx — retryable."""

    def __init__(self, message: str = "temporary server error (5xx)", context: dict | None = None, retry_after: float | None = None):
        super().__init__(code="TEMPORARY_SERVER_ERROR", message=message, context=context or {}, retry_after=retry_after)


class TimeoutError(RetryableError):  # noqa: A001
    """Timeout — retryable."""

    def __init__(self, message: str = "timeout", context: dict | None = None):
        super().__init__(code="TIMEOUT", message=message, context=context or {})


class NetworkError(RetryableError):
    """Network failure — retryable."""

    def __init__(self, message: str = "network error", context: dict | None = None):
        super().__init__(code="NETWORK_ERROR", message=message, context=context or {})


class PermanentError(LoaderError):
    """Non-retryable (400/401/403/404, validation, etc)."""


class BadRequestError(PermanentError):
    def __init__(self, message: str = "bad request (400)", context: dict | None = None):
        super().__init__(code="BAD_REQUEST", message=message, context=context or {})


class UnauthorizedError(PermanentError):
    def __init__(self, message: str = "unauthorized (401)", context: dict | None = None):
        super().__init__(code="UNAUTHORIZED", message=message, context=context or {})


class ForbiddenError(PermanentError):
    def __init__(self, message: str = "forbidden (403)", context: dict | None = None):
        super().__init__(code="FORBIDDEN", message=message, context=context or {})


class NotFoundError(PermanentError):
    def __init__(self, message: str = "not found (404)", context: dict | None = None):
        super().__init__(code="NOT_FOUND", message=message, context=context or {})


class RetryExhaustedError(LoaderError):
    """Raised after max_attempts exhausted (RetryPolicy only, no JobStatus change)."""

    def __init__(self, message: str = "retry exhausted", context: dict | None = None):
        super().__init__(code="RETRY_EXHAUSTED", message=message, context=context or {})
