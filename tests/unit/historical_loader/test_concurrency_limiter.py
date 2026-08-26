"""Tests for ConcurrencyLimiter and RequestLimiter."""

import threading

import pytest

from bss.historical_loader.infrastructure.networking.concurrency_limiter import ConcurrencyLimiter
from bss.historical_loader.infrastructure.networking.clock import FakeClock
from bss.historical_loader.infrastructure.networking.rate_limiter import RateLimiter
from bss.historical_loader.infrastructure.networking.request_limiter import RequestLimiter


def test_max_parallel_4():
    limiter = ConcurrencyLimiter(max_parallel=4)
    # acquire 4 should succeed
    for _ in range(4):
        limiter.acquire()
    assert limiter.in_flight() == 4
    # 5th should block until release — test with thread
    acquired = []
    def try_acquire():
        limiter.acquire()
        acquired.append(True)
        # hold a bit
        import time
        time.sleep(0.05)
        limiter.release()

    t = threading.Thread(target=try_acquire)
    t.start()
    # give thread time to attempt
    import time
    time.sleep(0.02)
    # should not have acquired yet (blocked)
    assert acquired == []
    # release one
    limiter.release()
    t.join(timeout=1.0)
    assert acquired == [True]
    assert limiter.in_flight() == 3
    # cleanup remaining
    for _ in range(3):
        limiter.release()
    assert limiter.in_flight() == 0


def test_release_after_success():
    limiter = ConcurrencyLimiter(max_parallel=4)
    limiter.acquire()
    assert limiter.in_flight() == 1
    limiter.release()
    assert limiter.in_flight() == 0


def test_release_after_exception():
    from bss.historical_loader.infrastructure.networking.clock import FakeClock

    clock = FakeClock(0.0)
    rate = RateLimiter(rps=5, clock=clock, capacity=1)
    conc = ConcurrencyLimiter(max_parallel=4)
    limiter = RequestLimiter(rate, conc)

    def failing():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        limiter.execute(failing)
    assert conc.in_flight() == 0
    assert conc.max_observed == 1


def test_release_after_cancellation():
    clock = FakeClock(0.0)
    rate = RateLimiter(rps=5, clock=clock, capacity=1)
    conc = ConcurrencyLimiter(max_parallel=4)
    limiter = RequestLimiter(rate, conc)

    class CancelledError(Exception):
        pass

    def cancelled():
        raise CancelledError("cancel")

    with pytest.raises(CancelledError):
        limiter.execute(cancelled)
    assert conc.in_flight() == 0


def test_request_limiter_exception_safe_concurrency_not_acquired():
    # If rate.acquire succeeds but concurrency.acquire raises, no release should happen
    clock = FakeClock(0.0)
    rate = RateLimiter(rps=5, clock=clock, capacity=1)
    conc = ConcurrencyLimiter(max_parallel=1)
    # fill concurrency
    conc.acquire()
    assert conc.in_flight() == 1
    limiter = RequestLimiter(rate, conc)
    # This will block on conc.acquire in another thread; test that rate not leaked
    # For exception during conc.acquire, simulate by interrupting
    # Instead test that if conc.acquire fails, no double release
    # We use a failing concurrency mock
    class FailingConcurrency:
        def acquire(self):
            raise RuntimeError("acquire fail")
        def release(self):
            assert False, "release should not be called if acquire failed"
        def in_flight(self):
            return 0
        @property
        def max_observed(self):
            return 0

    limiter2 = RequestLimiter(rate, FailingConcurrency())  # type: ignore
    with pytest.raises(RuntimeError):
        limiter2.execute(lambda: 42)
    # release should not have been called (assert inside)
    conc.release()
