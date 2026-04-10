"""Unit tests for vault crypto primitives."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.vault import crypto


def test_generate_kek_is_32_bytes():
    kek = crypto.generate_kek()
    assert len(kek) == crypto.KEK_BYTES == 32


def test_generate_dek_is_32_bytes():
    dek = crypto.generate_dek()
    assert len(dek) == 32


def test_kek_roundtrip_via_base64():
    kek = crypto.generate_kek()
    encoded = crypto.encode_kek(kek)
    assert isinstance(encoded, str)
    assert crypto.decode_kek(encoded) == kek


def test_decode_kek_rejects_invalid_base64():
    with pytest.raises(crypto.KekInvalidError):
        crypto.decode_kek("not!base64!")


def test_decode_kek_rejects_wrong_length():
    short = crypto.encode_kek(b"\x00" * 32)[:20]
    with pytest.raises(crypto.KekInvalidError):
        crypto.decode_kek(short)


def test_load_kek_from_env_missing(monkeypatch):
    monkeypatch.delenv("PSA_DASHBOARD_MASTER_KEY", raising=False)
    with pytest.raises(crypto.KekMissingError):
        crypto.load_kek_from_env()


def test_load_kek_from_env_invalid(monkeypatch):
    monkeypatch.setenv("PSA_DASHBOARD_MASTER_KEY", "not-a-real-key")
    with pytest.raises(crypto.KekInvalidError):
        crypto.load_kek_from_env()


def test_load_kek_from_env_success(monkeypatch):
    kek = crypto.generate_kek()
    monkeypatch.setenv("PSA_DASHBOARD_MASTER_KEY", crypto.encode_kek(kek))
    loaded = crypto.load_kek_from_env()
    assert loaded == kek


def test_dek_wrap_unwrap_roundtrip():
    kek = crypto.generate_kek()
    dek = crypto.generate_dek()
    nonce, wrapped = crypto.wrap_dek(dek, kek)
    assert len(nonce) == crypto.NONCE_BYTES
    assert wrapped != dek
    assert crypto.unwrap_dek(wrapped, nonce, kek) == dek


def test_dek_unwrap_with_wrong_kek_fails():
    kek = crypto.generate_kek()
    other = crypto.generate_kek()
    dek = crypto.generate_dek()
    nonce, wrapped = crypto.wrap_dek(dek, kek)
    with pytest.raises(crypto.DekUnwrapError):
        crypto.unwrap_dek(wrapped, nonce, other)


def test_encrypt_decrypt_roundtrip():
    dek = crypto.generate_dek()
    plaintext = "super-secret-api-token-12345"
    nonce, ct = crypto.encrypt(plaintext, dek, aad="superops.api_token")
    assert plaintext.encode() not in ct  # plaintext is not in the ciphertext
    assert crypto.decrypt(nonce, ct, dek, aad="superops.api_token") == plaintext


def test_decrypt_wrong_key_fails():
    dek = crypto.generate_dek()
    other = crypto.generate_dek()
    nonce, ct = crypto.encrypt("hello", dek, aad="k")
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(nonce, ct, other, aad="k")


def test_decrypt_tampered_ciphertext_fails():
    dek = crypto.generate_dek()
    nonce, ct = crypto.encrypt("hello world", dek, aad="k")
    tampered = bytes([ct[0] ^ 0x01]) + ct[1:]
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(nonce, tampered, dek, aad="k")


def test_decrypt_wrong_aad_fails():
    """Cross-row swap protection: AAD bound to logical key name."""
    dek = crypto.generate_dek()
    nonce, ct = crypto.encrypt("hello", dek, aad="superops.api_token")
    with pytest.raises(crypto.DecryptError):
        crypto.decrypt(nonce, ct, dek, aad="zendesk.api_token")


def test_nonce_uniqueness_over_many_encryptions():
    dek = crypto.generate_dek()
    seen = set()
    for _ in range(10_000):
        nonce, _ = crypto.encrypt("x", dek, aad="k")
        seen.add(nonce)
    assert len(seen) == 10_000


def test_encrypt_unicode_plaintext():
    dek = crypto.generate_dek()
    plaintext = "tökeñ-with-üñîçødé-😀"
    nonce, ct = crypto.encrypt(plaintext, dek, aad="k")
    assert crypto.decrypt(nonce, ct, dek, aad="k") == plaintext


# ----- file-based KEK bootstrap -----


def test_load_or_create_kek_file_creates_when_missing(tmp_path: Path):
    key_path = tmp_path / "subdir" / ".vault_master_key"
    assert not key_path.exists()
    kek = crypto.load_or_create_kek_file(key_path)
    assert len(kek) == crypto.KEK_BYTES
    assert key_path.exists()
    # File should contain a base64 line that decodes back to the same key.
    encoded = key_path.read_text(encoding="ascii").strip()
    assert crypto.decode_kek(encoded) == kek


def test_load_or_create_kek_file_reads_existing(tmp_path: Path):
    key_path = tmp_path / ".vault_master_key"
    kek = crypto.load_or_create_kek_file(key_path)
    # Second call returns the same key, not a new one.
    same = crypto.load_or_create_kek_file(key_path)
    assert kek == same


def test_load_or_create_kek_file_empty_raises(tmp_path: Path):
    key_path = tmp_path / ".vault_master_key"
    key_path.write_text("", encoding="ascii")
    with pytest.raises(crypto.KekInvalidError):
        crypto.load_or_create_kek_file(key_path)


def test_load_or_create_kek_file_corrupted_raises(tmp_path: Path):
    key_path = tmp_path / ".vault_master_key"
    key_path.write_text("not-valid-base64!!", encoding="ascii")
    with pytest.raises(crypto.KekInvalidError):
        crypto.load_or_create_kek_file(key_path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission check")
def test_load_or_create_kek_file_sets_0600_on_posix(tmp_path: Path):
    import stat
    key_path = tmp_path / ".vault_master_key"
    crypto.load_or_create_kek_file(key_path)
    mode = stat.S_IMODE(key_path.stat().st_mode)
    assert mode == 0o600
