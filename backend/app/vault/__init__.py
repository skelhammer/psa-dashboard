"""Vault: encrypted secrets storage backed by SQLite + AES-256-GCM.

Named 'vault' rather than 'secrets' to avoid shadowing the Python stdlib
secrets module.
"""

from app.vault.crypto import (
    KEK_BYTES,
    NONCE_BYTES,
    CryptoError,
    KekInvalidError,
    KekMissingError,
    decrypt,
    encrypt,
    generate_dek,
    generate_kek,
    load_kek_from_env,
    load_or_create_kek_file,
    unwrap_dek,
    wrap_dek,
)
from app.vault.manager import SecretStatus, SecretsManager

__all__ = [
    "KEK_BYTES",
    "NONCE_BYTES",
    "CryptoError",
    "KekInvalidError",
    "KekMissingError",
    "SecretStatus",
    "SecretsManager",
    "decrypt",
    "encrypt",
    "generate_dek",
    "generate_kek",
    "load_kek_from_env",
    "load_or_create_kek_file",
    "unwrap_dek",
    "wrap_dek",
]
