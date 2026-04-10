"""Password hashing and verification using bcrypt.

verify_password is constant-time even when the username does not exist:
when the caller has no real hash to check, it verifies against a fixed
dummy hash so the response time of "user does not exist" matches the
response time of "user exists but wrong password". This prevents an
attacker from enumerating valid usernames via timing.
"""

from __future__ import annotations

import bcrypt

# Pre-computed hash of an unguessable string. Used as the comparison target
# when no real user hash exists, so the rejection path takes the same time
# as a real verification.
_DUMMY_HASH = bcrypt.hashpw(
    b"this-is-not-a-real-password-its-a-timing-decoy",
    bcrypt.gensalt(rounds=12),
)

MIN_PASSWORD_LENGTH = 12


class WeakPasswordError(ValueError):
    """Raised when a proposed password fails minimum strength requirements."""


def hash_password(password: str) -> str:
    """Hash a password with bcrypt at cost 12. Returns the encoded hash string."""
    if not isinstance(password, str):
        raise WeakPasswordError("password must be a string")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode(
        "ascii"
    )


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Constant-time-ish password verification.

    Always runs a bcrypt check, even when stored_hash is None, so the time
    to reject a nonexistent user matches the time to reject a real user
    with a wrong password. Both paths run one bcrypt verification.
    """
    if not isinstance(password, str):
        return False
    pw_bytes = password.encode("utf-8")
    if stored_hash is None or not stored_hash:
        # Compare against the dummy hash so timing matches.
        bcrypt.checkpw(pw_bytes, _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(pw_bytes, stored_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
