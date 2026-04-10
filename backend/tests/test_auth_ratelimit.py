"""Unit tests for the in-memory login rate limiter."""

from __future__ import annotations

import time

from app.auth.ratelimit import LoginRateLimiter


def test_allows_attempts_below_limit():
    rl = LoginRateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        assert rl.check("ip1") is True
        rl.record_attempt("ip1")
    assert rl.check("ip1") is False


def test_separate_keys_have_separate_quotas():
    rl = LoginRateLimiter(max_attempts=2, window_seconds=60)
    rl.record_attempt("ip1")
    rl.record_attempt("ip1")
    assert rl.check("ip1") is False
    assert rl.check("ip2") is True


def test_remaining_decrements():
    rl = LoginRateLimiter(max_attempts=5, window_seconds=60)
    assert rl.remaining("ip1") == 5
    rl.record_attempt("ip1")
    assert rl.remaining("ip1") == 4
    rl.record_attempt("ip1")
    assert rl.remaining("ip1") == 3


def test_window_expires_attempts(monkeypatch):
    """Old attempts fall out of the window and the key is allowed again."""
    rl = LoginRateLimiter(max_attempts=2, window_seconds=60)

    # Fake time so we don't have to actually wait 60 seconds.
    fake_time = [1000.0]
    monkeypatch.setattr(
        "app.auth.ratelimit.time.monotonic", lambda: fake_time[0]
    )

    rl.record_attempt("ip1")
    rl.record_attempt("ip1")
    assert rl.check("ip1") is False

    fake_time[0] += 61  # advance past the window
    assert rl.check("ip1") is True
    assert rl.remaining("ip1") == 2


def test_retry_after_seconds_when_blocked():
    rl = LoginRateLimiter(max_attempts=1, window_seconds=300)
    rl.record_attempt("ip1")
    retry = rl.retry_after_seconds("ip1")
    assert 0 < retry <= 300


def test_reset_specific_key():
    rl = LoginRateLimiter(max_attempts=2, window_seconds=60)
    rl.record_attempt("ip1")
    rl.record_attempt("ip1")
    assert rl.check("ip1") is False
    rl.reset("ip1")
    assert rl.check("ip1") is True


def test_reset_all_keys():
    rl = LoginRateLimiter(max_attempts=1, window_seconds=60)
    rl.record_attempt("a")
    rl.record_attempt("b")
    rl.reset(None)
    assert rl.check("a") is True
    assert rl.check("b") is True
