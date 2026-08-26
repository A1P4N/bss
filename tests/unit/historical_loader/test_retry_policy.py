"""Tests for RetryPolicy — 429, 5xx, permanent, exhausted, deterministic, no Job/HTTP."""

import pytest

from bss.historical_loader.domain.errors import (
    BadRequestError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    PermanentError,
    RateLimitedError,
    RetryExhaustedError,
    TemporaryServerError,
    TimeoutError,
    UnauthorizedError,
)
from bss.historical_loader.infrastructure.networking.clock import FakeClock
from bss.historical_loader.infrastructure.networking.retry import RetryPolicy


def test_429_retry():
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=3, initial_delay=1.0, max_delay=60.0, factor=2.0)
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RateLimitedError(retry_after=0.5)
        return "ok"

    result = policy.execute(op, clock)
    assert result == "ok"
    assert calls["n"] == 3
    # first retry delay 0.5 (Retry-After), second 0.5
    assert clock.sleeps == [0.5, 0.5]


def test_503_retry():
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=3, initial_delay=1.0, max_delay=60.0, factor=2.0)
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TemporaryServerError()
        return "ok"

    result = policy.execute(op, clock)
    assert result == "ok"
    assert calls["n"] == 2
    assert clock.sleeps == [1.0]  # backoff for attempt 2


def test_400_no_retry():
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=3)
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise BadRequestError()

    with pytest.raises(BadRequestError):
        policy.execute(op, clock)
    assert calls["n"] == 1
    assert clock.sleeps == []


def test_401_no_retry():
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=3)
    with pytest.raises(UnauthorizedError):
        policy.execute(lambda: (_ for _ in ()).throw(UnauthorizedError()), clock)
    assert clock.sleeps == []


def test_403_no_retry():
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=3)
    with pytest.raises(ForbiddenError):
        policy.execute(lambda: (_ for _ in ()).throw(ForbiddenError()), clock)
    assert clock.sleeps == []


def test_404_no_retry():
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=3)
    with pytest.raises(NotFoundError):
        policy.execute(lambda: (_ for _ in ()).throw(NotFoundError()), clock)
    assert clock.sleeps == []


def test_exhausted_no_checkpoint_change():
    # Invariant: exhausted does not imply checkpoint change — policy just raises
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=3, initial_delay=1.0, max_delay=60.0, factor=2.0)
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise TemporaryServerError()

    with pytest.raises(RetryExhaustedError) as exc:
        policy.execute(op, clock)
    assert calls["n"] == 3
    assert exc.value.code == "RETRY_EXHAUSTED"
    # sleeps for attempts 2 and 3
    assert clock.sleeps == [1.0, 2.0]


def test_retry_policy_no_download_job_import():
    import pathlib

    text = pathlib.Path("src/bss/historical_loader/infrastructure/networking/retry.py").read_text()
    lower = text.lower()
    # must not import job types; docstring may mention but import is forbidden
    assert "from bss.historical_loader.domain.download_job" not in lower
    assert "import download_job" not in lower
    assert "from .download_job" not in lower


def test_retry_policy_no_http_import():
    import pathlib

    text = pathlib.Path("src/bss/historical_loader/infrastructure/networking/retry.py").read_text()
    assert "httpx" not in text.lower()
    assert "requests" not in text.lower()
    assert "aiohttp" not in text.lower()


def test_deterministic_backoff():
    policy = RetryPolicy(max_attempts=5, initial_delay=1.0, max_delay=60.0, factor=2.0)
    # attempt 2 ->1.0, 3->2.0, 4->4.0, 5->8.0
    assert policy.backoff(1) == 0.0
    assert policy.backoff(2) == 1.0
    assert policy.backoff(3) == 2.0
    assert policy.backoff(4) == 4.0
    assert policy.backoff(5) == 8.0
    # capped
    policy2 = RetryPolicy(max_attempts=10, initial_delay=10.0, max_delay=60.0, factor=2.0)
    assert policy2.backoff(5) == 60.0  # 10*8=80 capped 60
    # deterministic: two policies same params give same
    assert policy.backoff(3) == RetryPolicy(5, 1.0, 60.0, 2.0).backoff(3)


def test_retry_after_valid_vs_invalid():
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=3, initial_delay=1.0, max_delay=5.0, factor=2.0)
    # valid Retry-After <= max_delay -> used
    def op_valid():
        raise RateLimitedError(retry_after=3.0)

    calls = {"n": 0}

    def op():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RateLimitedError(retry_after=3.0)
        if calls["n"] == 2:
            raise RateLimitedError(retry_after=100.0)  # invalid > max_delay -> backoff
        return "ok"

    # first retry uses 3.0, second uses backoff 2.0 (attempt 3)
    result = policy.execute(op, clock)
    assert result == "ok"
    assert clock.sleeps[0] == 3.0
    assert clock.sleeps[1] == 2.0


def test_timeout_network_retry():
    clock = FakeClock(0.0)
    policy = RetryPolicy(max_attempts=2)
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError()
        return "ok"

    assert policy.execute(op, clock) == "ok"
    calls = {"n": 0}

    def op2():
        calls["n"] += 1
        if calls["n"] == 1:
            raise NetworkError()
        return "ok"

    assert policy.execute(op2, clock) == "ok"
