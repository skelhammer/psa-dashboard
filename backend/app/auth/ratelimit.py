"""Simple in-memory sliding-window rate limiter for the login endpoint.

Keyed by client IP. Stores a deque of recent attempt timestamps per key
and rejects when the count within the window exceeds the maximum.

This is in-memory only and resets on backend restart. That is acceptable
for a single-process dashboard. If we ever scale to multiple workers, this
should move to a shared store (redis / sqlite).

Successful logins do NOT clear the counter. The counter is purely a brake
against brute force, and a successful login from one IP should not give an
attacker on the same IP a fresh quota.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        attempts = self._attempts[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()

    def check(self, key: str) -> bool:
        """Return True if the key is currently allowed to attempt login."""
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            return len(self._attempts[key]) < self.max_attempts

    def record_attempt(self, key: str) -> None:
        """Record a login attempt (successful or not) against the key."""
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            self._attempts[key].append(now)

    def remaining(self, key: str) -> int:
        """Return how many attempts the key has left in the current window."""
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            return max(0, self.max_attempts - len(self._attempts[key]))

    def retry_after_seconds(self, key: str) -> int:
        """Seconds until the oldest in-window attempt falls out of the window."""
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            attempts = self._attempts[key]
            if len(attempts) < self.max_attempts:
                return 0
            oldest = attempts[0]
            return max(1, int(oldest + self.window_seconds - now))

    def reset(self, key: str | None = None) -> None:
        """Clear attempts. If key is None, clear everything (for tests)."""
        with self._lock:
            if key is None:
                self._attempts.clear()
            else:
                self._attempts.pop(key, None)
