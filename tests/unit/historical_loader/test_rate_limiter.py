"""Tests for RateLimiter strict pacing."""

import pytest

from bss.historical_loader.infrastructure.networking.clock import FakeClock
from bss.historical_loader.infrastructure.networking.rate_limiter import RateLimiter


def test_strict_5_rps():
    clock = FakeClock(0.0)
    limiter = RateLimiter(rps=5, clock=clock, capacity=1)
    times = []
    for _ in range(5):
        limiter.acquire()
        times.append(clock.monotonic())
    # strict pacing: 0.0, 0.2, 0.4, 0.6, 0.8
    assert times == pytest.approx([0.0, 0.2, 0.4, 0.6, 0.8])
    for i in range(1, len(times)):
        assert abs(times[i] - times[i-1] - 0.2) < 1e-9


def test_rate_limiter_monotonic():
    clock = FakeClock(10.0)
    limiter = RateLimiter(rps=5, clock=clock)
    limiter.acquire()
    # next acquire should sleep 0.2 → 10.2
    limiter.acquire()
    assert clock.monotonic() == pytest.approx(10.2)
