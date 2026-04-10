"""Session signing key bootstrap.

Sessions are signed cookies (Starlette SessionMiddleware uses itsdangerous
under the hood). The signing key is a random 32-byte secret stored in a file
alongside the vault master key. Auto-generated on first run.

If this key is rotated or lost, all existing sessions are invalidated and
users will need to log in again. That is acceptable behavior.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

KEY_BYTES = 32


def load_or_create_signing_key(path: Path) -> str:
    """Load the session signing key from `path`, generating one if missing.

    Returns a hex-encoded 64-character string suitable for passing to
    Starlette's SessionMiddleware as `secret_key`.
    """
    if path.exists():
        encoded = path.read_text(encoding="ascii").strip()
        if not encoded:
            raise ValueError(
                f"Session signing key file {path} is empty. Delete it to "
                "generate a new one (existing sessions will be invalidated)."
            )
        return encoded

    raw = secrets.token_bytes(KEY_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = raw.hex()
    path.write_text(encoded + "\n", encoding="ascii")
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    logger.info("Generated new session signing key at %s", path)
    return encoded
