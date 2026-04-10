"""Unit tests for password hashing/verification."""

from __future__ import annotations

import time

import pytest

from app.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
    hash_password,
    verify_password,
)


def test_hash_then_verify_succeeds():
    pw = "this-is-a-strong-password"
    h = hash_password(pw)
    assert verify_password(pw, h) is True


def test_verify_wrong_password_fails():
    h = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password-here", h) is False


def test_short_password_rejected():
    with pytest.raises(WeakPasswordError):
        hash_password("short")
    assert MIN_PASSWORD_LENGTH >= 12


def test_verify_with_no_stored_hash_returns_false_but_runs_bcrypt():
    """Constant-time-ish: even when there's no real user, verify_password
    runs a bcrypt check against a dummy hash and returns False, so the
    response time is similar to a real verification."""
    start = time.perf_counter()
    result = verify_password("any-password", None)
    elapsed = time.perf_counter() - start
    assert result is False
    # bcrypt at cost 12 takes O(100ms+); we just want to confirm we actually
    # did some work (not an instant return).
    assert elapsed > 0.01


def test_verify_with_empty_hash_returns_false():
    assert verify_password("any-password", "") is False


def test_verify_with_corrupt_hash_returns_false():
    assert verify_password("any-password", "not-a-bcrypt-hash") is False


def test_hash_is_unique_per_call():
    """Bcrypt salts make each hash unique even for the same password."""
    pw = "the-same-password-twice"
    assert hash_password(pw) != hash_password(pw)


def test_non_string_password_returns_false():
    assert verify_password(None, "any-hash") is False  # type: ignore
    assert verify_password(12345, "any-hash") is False  # type: ignore
