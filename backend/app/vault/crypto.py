"""AES-256-GCM primitives and KEK/DEK key wrapping.

Design notes:
- KEK (Key Encryption Key): 32 bytes loaded from an environment variable
  (base64 encoded). Never written to disk by the app. Lost KEK = lost vault.
- DEK (Data Encryption Key): 32 random bytes generated on first run, stored
  in the vault_meta row wrapped under the KEK using AES-256-GCM. Rotating
  the KEK only re-wraps the DEK (single row update), not every secret.
- Per-secret encryption uses AES-256-GCM with a fresh 96-bit nonce per
  record. The logical secret key name is bound as Additional Authenticated
  Data (AAD) so a ciphertext cannot be transplanted to a different row.

All functions in this module are pure (no I/O) and never log secret values.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets as _secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

KEK_BYTES = 32  # AES-256
DEK_BYTES = 32  # AES-256
NONCE_BYTES = 12  # 96-bit GCM nonce


class CryptoError(Exception):
    """Base class for vault crypto errors. Never includes plaintext in str()."""


class KekMissingError(CryptoError):
    """The KEK environment variable is unset or empty."""


class KekInvalidError(CryptoError):
    """The KEK environment variable is set but not a valid 32-byte base64 key."""


class DekUnwrapError(CryptoError):
    """The wrapped DEK could not be decrypted with the supplied KEK."""


class DecryptError(CryptoError):
    """A ciphertext failed to decrypt (wrong key, tampered data, or wrong AAD)."""


def generate_kek() -> bytes:
    """Return a fresh 32-byte KEK suitable for AES-256."""
    return _secrets.token_bytes(KEK_BYTES)


def generate_dek() -> bytes:
    """Return a fresh 32-byte DEK suitable for AES-256."""
    return _secrets.token_bytes(DEK_BYTES)


def encode_kek(kek: bytes) -> str:
    """Encode a raw KEK as a base64 string for storage in env vars or files."""
    if len(kek) != KEK_BYTES:
        raise KekInvalidError(f"KEK must be {KEK_BYTES} bytes, got {len(kek)}")
    return base64.b64encode(kek).decode("ascii")


def decode_kek(encoded: str) -> bytes:
    """Decode a base64 KEK string back to raw bytes. Raises KekInvalidError."""
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise KekInvalidError("KEK is not valid base64") from exc
    if len(raw) != KEK_BYTES:
        raise KekInvalidError(
            f"KEK must decode to {KEK_BYTES} bytes, got {len(raw)}"
        )
    return raw


def load_kek_from_env(env_var: str = "PSA_DASHBOARD_MASTER_KEY") -> bytes:
    """Load and validate the KEK from an environment variable.

    Raises KekMissingError if unset, KekInvalidError if malformed. Both errors
    are typed so the application can render a clear startup message without
    leaking key material. Used by the advanced env-var deployment mode; the
    default deployment uses load_or_create_kek_file() instead.
    """
    encoded = os.environ.get(env_var, "").strip()
    if not encoded:
        raise KekMissingError(
            f"Environment variable {env_var} is not set."
        )
    return decode_kek(encoded)


def load_or_create_kek_file(path: Path) -> bytes:
    """Load the master key from `path`, generating a new one if missing.

    This is the default key bootstrap path for the dashboard. The key file
    is written with mode 0600 (POSIX) so only the service user can read it.
    On Windows the chmod is best-effort (NTFS ACLs are inherited).

    The format is a single base64-encoded line so the file is text-editor
    friendly and can be copy-pasted into a backup.

    Raises KekInvalidError if an existing file is corrupted.
    """
    if path.exists():
        encoded = path.read_text(encoding="ascii").strip()
        if not encoded:
            raise KekInvalidError(
                f"Master key file {path} is empty. Either restore it from a "
                "backup or delete it to generate a new key (this will lose "
                "access to all currently stored secrets)."
            )
        return decode_kek(encoded)

    # First run: mint a fresh key, write it, lock down permissions.
    kek = generate_kek()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encode_kek(kek) + "\n", encoding="ascii")
    try:
        os.chmod(path, 0o600)
    except Exception:
        # Windows / FAT volumes do not honor POSIX modes; rely on directory ACLs.
        pass
    logger.warning(
        "Generated new vault master key at %s. BACK THIS FILE UP alongside "
        "your database. Losing it means losing access to all stored secrets.",
        path,
    )
    return kek


def wrap_dek(dek: bytes, kek: bytes) -> tuple[bytes, bytes]:
    """Encrypt the DEK under the KEK. Returns (nonce, ciphertext).

    AAD is the fixed string b'vault:dek' so the wrapped DEK cannot be
    confused with a per-secret ciphertext.
    """
    if len(dek) != DEK_BYTES:
        raise CryptoError(f"DEK must be {DEK_BYTES} bytes")
    if len(kek) != KEK_BYTES:
        raise KekInvalidError(f"KEK must be {KEK_BYTES} bytes")
    nonce = _secrets.token_bytes(NONCE_BYTES)
    ct = AESGCM(kek).encrypt(nonce, dek, b"vault:dek")
    return nonce, ct


def unwrap_dek(wrapped: bytes, nonce: bytes, kek: bytes) -> bytes:
    """Decrypt a wrapped DEK using the KEK. Raises DekUnwrapError on failure."""
    if len(kek) != KEK_BYTES:
        raise KekInvalidError(f"KEK must be {KEK_BYTES} bytes")
    try:
        return AESGCM(kek).decrypt(nonce, wrapped, b"vault:dek")
    except InvalidTag as exc:
        raise DekUnwrapError(
            "Failed to unwrap DEK. The KEK is wrong or the vault_meta row "
            "is corrupted."
        ) from exc


def encrypt(plaintext: str, dek: bytes, aad: str) -> tuple[bytes, bytes]:
    """Encrypt a UTF-8 string under the DEK. Returns (nonce, ciphertext).

    AAD should be the logical secret key name (e.g. 'superops.api_token').
    Binding the key name into the ciphertext prevents an attacker with DB
    write access from swapping ciphertexts between rows.
    """
    if len(dek) != DEK_BYTES:
        raise CryptoError(f"DEK must be {DEK_BYTES} bytes")
    nonce = _secrets.token_bytes(NONCE_BYTES)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
    return nonce, ct


def decrypt(nonce: bytes, ciphertext: bytes, dek: bytes, aad: str) -> str:
    """Decrypt a ciphertext to a UTF-8 string. Raises DecryptError on failure."""
    if len(dek) != DEK_BYTES:
        raise CryptoError(f"DEK must be {DEK_BYTES} bytes")
    try:
        pt = AESGCM(dek).decrypt(nonce, ciphertext, aad.encode("utf-8"))
    except InvalidTag as exc:
        raise DecryptError(
            "Failed to decrypt vault entry. Wrong key, tampered ciphertext, "
            "or AAD mismatch."
        ) from exc
    return pt.decode("utf-8")
