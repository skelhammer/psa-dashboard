"""Tests for migrate_from_yaml: first run, idempotency, vault-wins."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from app.database import Database
from app.vault import crypto
from app.vault.keys import PLACEHOLDER
from app.vault.manager import SecretsManager
from app.vault.migrate import migrate_from_yaml


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def manager(db: Database) -> SecretsManager:
    return SecretsManager(db, crypto.generate_kek())


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _sample_config_with_secrets() -> dict:
    return {
        "psa": {
            "providers": ["superops"],
            "superops": {
                "api_url": "https://api.superops.ai/msp",
                "api_token": "live-superops-token-123",
                "subdomain": "acme",
            },
            "zendesk": {
                "subdomain": "acme",
                "email": "agent@acme.com",
                "api_token": "live-zendesk-token-456",
            },
        },
        "phone": {
            "provider": "zoom",
            "zoom": {
                "account_id": "zoom-account-789",
                "client_id": "zoom-client-id",
                "client_secret": "zoom-client-secret",
            },
        },
        "sync": {"interval_minutes": 15},
    }


async def test_migrates_secrets_from_yaml(
    tmp_path: Path, manager: SecretsManager
):
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(yaml_path, _sample_config_with_secrets())

    result = await migrate_from_yaml(yaml_path, manager)

    assert "psa.superops.api_token" in result.migrated
    assert "psa.zendesk.api_token" in result.migrated
    assert "phone.zoom.account_id" in result.migrated
    assert "phone.zoom.client_id" in result.migrated
    assert "phone.zoom.client_secret" in result.migrated
    assert result.yaml_rewritten is True
    assert result.backup_written is not None
    assert result.backup_written.exists()

    # Vault now contains the values
    assert await manager.get("psa.superops.api_token") == "live-superops-token-123"
    assert await manager.get("psa.zendesk.api_token") == "live-zendesk-token-456"
    assert await manager.get("phone.zoom.client_secret") == "zoom-client-secret"


async def test_redacts_yaml_in_place(
    tmp_path: Path, manager: SecretsManager
):
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(yaml_path, _sample_config_with_secrets())

    await migrate_from_yaml(yaml_path, manager)

    redacted = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    # All migrated fields (secrets AND non-secret credentials) are placeholdered
    assert redacted["psa"]["superops"]["api_token"] == PLACEHOLDER
    assert redacted["psa"]["superops"]["subdomain"] == PLACEHOLDER
    assert redacted["psa"]["zendesk"]["api_token"] == PLACEHOLDER
    assert redacted["psa"]["zendesk"]["email"] == PLACEHOLDER
    assert redacted["psa"]["zendesk"]["subdomain"] == PLACEHOLDER
    assert redacted["phone"]["zoom"]["client_secret"] == PLACEHOLDER

    # Non-credential fields are preserved unchanged
    assert redacted["psa"]["superops"]["api_url"] == "https://api.superops.ai/msp"
    assert redacted["sync"]["interval_minutes"] == 15


async def test_backup_contains_original_plaintext(
    tmp_path: Path, manager: SecretsManager
):
    yaml_path = tmp_path / "config.yaml"
    original = _sample_config_with_secrets()
    _write_yaml(yaml_path, original)

    result = await migrate_from_yaml(yaml_path, manager)

    backup = yaml.safe_load(result.backup_written.read_text(encoding="utf-8"))
    assert backup["psa"]["superops"]["api_token"] == "live-superops-token-123"
    assert backup["phone"]["zoom"]["client_secret"] == "zoom-client-secret"


async def test_idempotent_second_run(
    tmp_path: Path, manager: SecretsManager
):
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(yaml_path, _sample_config_with_secrets())

    first = await migrate_from_yaml(yaml_path, manager)
    # Five tokens/secrets + zendesk email + two subdomains = 8 entries.
    assert len(first.migrated) == 8

    second = await migrate_from_yaml(yaml_path, manager)
    assert second.migrated == []
    assert second.yaml_rewritten is False
    assert second.backup_written is None  # backup not rewritten on second run


async def test_vault_already_set_wins_over_yaml(
    tmp_path: Path, manager: SecretsManager
):
    """A value already in the vault is NOT overwritten by a stale yaml value."""
    await manager.set("psa.superops.api_token", "fresh-ui-set-value", actor="test")

    yaml_path = tmp_path / "config.yaml"
    _write_yaml(yaml_path, _sample_config_with_secrets())

    result = await migrate_from_yaml(yaml_path, manager)

    assert "psa.superops.api_token" not in result.migrated
    assert "psa.superops.api_token" in result.skipped
    # Vault still has the UI-set value, not the stale yaml value
    assert await manager.get("psa.superops.api_token") == "fresh-ui-set-value"


async def test_skips_empty_and_placeholder_values(
    tmp_path: Path, manager: SecretsManager
):
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(
        yaml_path,
        {
            "psa": {
                "superops": {"api_token": ""},
                "zendesk": {"api_token": PLACEHOLDER},
            },
            "phone": {"zoom": {"account_id": "   "}},
        },
    )

    result = await migrate_from_yaml(yaml_path, manager)
    assert result.migrated == []
    assert result.yaml_rewritten is False
    # No backup written when nothing was migrated
    assert result.backup_written is None


async def test_missing_yaml_is_no_op(
    tmp_path: Path, manager: SecretsManager
):
    yaml_path = tmp_path / "does-not-exist.yaml"
    result = await migrate_from_yaml(yaml_path, manager)
    assert result.migrated == []
    assert result.yaml_rewritten is False


async def test_partial_yaml_migrates_what_it_can(
    tmp_path: Path, manager: SecretsManager
):
    """Yaml with only some secret sections still migrates the present ones."""
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(
        yaml_path,
        {
            "psa": {
                "providers": ["superops"],
                "superops": {"api_token": "only-superops"},
            },
            # No zendesk, no phone section at all
        },
    )

    result = await migrate_from_yaml(yaml_path, manager)
    assert result.migrated == ["psa.superops.api_token"]
    assert await manager.get("psa.superops.api_token") == "only-superops"
    assert await manager.get("psa.zendesk.api_token") is None


async def test_backup_not_overwritten_by_subsequent_runs(
    tmp_path: Path, manager: SecretsManager
):
    """If a .pre-secrets.bak already exists, do not clobber it."""
    yaml_path = tmp_path / "config.yaml"
    backup_path = tmp_path / "config.yaml.pre-secrets.bak"
    backup_path.write_text("PRE-EXISTING BACKUP CONTENT", encoding="utf-8")

    _write_yaml(yaml_path, _sample_config_with_secrets())
    result = await migrate_from_yaml(yaml_path, manager)

    # Migration still runs, but does not touch the existing backup file.
    assert result.migrated  # secrets were migrated
    assert backup_path.read_text(encoding="utf-8") == "PRE-EXISTING BACKUP CONTENT"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission check")
async def test_backup_file_is_0600_on_posix(
    tmp_path: Path, manager: SecretsManager
):
    import stat
    yaml_path = tmp_path / "config.yaml"
    _write_yaml(yaml_path, _sample_config_with_secrets())
    result = await migrate_from_yaml(yaml_path, manager)
    mode = stat.S_IMODE(result.backup_written.stat().st_mode)
    assert mode == 0o600
