"""One-time migration of plaintext secrets from config.yaml into the vault.

Behavior on first boot with an old plaintext config.yaml:
1. For each entry in vault.keys.SECRET_KEYS, look up the corresponding path
   in the parsed yaml. If the value is empty, missing, or already the
   placeholder, skip it.
2. If the vault already has a value for that key, skip the yaml value.
   This protects against a stale yaml overwriting a fresh value the user
   set through the Settings UI.
3. Otherwise, write the yaml value into the vault.
4. After processing all keys, if any value was migrated, write a one-time
   backup at config.yaml.pre-secrets.bak (mode 0600) and rewrite the live
   config.yaml in place with placeholder strings replacing each migrated
   secret.

The migration is idempotent: a second run with an already-redacted yaml
is a no-op. If the migration raises mid-way, the live yaml is left
untouched and the next startup retries.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.vault.keys import PLACEHOLDER, SECRET_KEYS, SecretKey, is_placeholder
from app.vault.manager import SecretsManager

logger = logging.getLogger(__name__)

BACKUP_SUFFIX = ".pre-secrets.bak"


@dataclass
class MigrationResult:
    migrated: list[str]       # vault key names that were just migrated
    skipped: list[str]        # vault key names skipped (empty / already in vault / placeholder)
    backup_written: Path | None  # path to the .pre-secrets.bak file, if created
    yaml_rewritten: bool       # True if config.yaml was rewritten with placeholders


def _get_in(data: dict, path: tuple) -> Any:
    """Walk a nested dict by tuple path. Returns None if any segment missing."""
    cur: Any = data
    for segment in path:
        if not isinstance(cur, dict) or segment not in cur:
            return None
        cur = cur[segment]
    return cur


def _set_in(data: dict, path: tuple, value: Any) -> None:
    """Set a value at a nested dict path, creating intermediate dicts as needed."""
    cur: Any = data
    for segment in path[:-1]:
        if segment not in cur or not isinstance(cur[segment], dict):
            cur[segment] = {}
        cur = cur[segment]
    cur[path[-1]] = value


def _value_is_migratable(value: Any) -> bool:
    """A value is worth migrating if it's a non-empty string that isn't already redacted."""
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if is_placeholder(stripped):
        return False
    return True


async def migrate_from_yaml(
    yaml_path: Path,
    manager: SecretsManager,
) -> MigrationResult:
    """Migrate plaintext secrets from a yaml file into the vault.

    Returns a MigrationResult describing what happened so the lifespan can
    log a useful summary. Never logs the secret values themselves.
    """
    result = MigrationResult(
        migrated=[], skipped=[], backup_written=None, yaml_rewritten=False
    )

    if not yaml_path.exists():
        logger.info("vault migrate: no config.yaml at %s, nothing to migrate", yaml_path)
        return result

    raw_text = yaml_path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        logger.error("vault migrate: failed to parse %s: %s", yaml_path, exc)
        return result

    # Determine which keys are eligible to migrate.
    to_migrate: list[tuple[SecretKey, str]] = []
    for sk in SECRET_KEYS:
        yaml_value = _get_in(parsed, sk.yaml_path)
        if not _value_is_migratable(yaml_value):
            result.skipped.append(sk.name)
            continue
        if await manager.has(sk.name):
            # Vault wins over yaml; the yaml is stale.
            result.skipped.append(sk.name)
            continue
        to_migrate.append((sk, yaml_value))

    if not to_migrate:
        logger.info(
            "vault migrate: nothing to migrate from %s (skipped %d keys)",
            yaml_path,
            len(result.skipped),
        )
        return result

    # Write each migratable value into the vault.
    for sk, value in to_migrate:
        await manager.set(sk.name, value, actor="migrate")
        result.migrated.append(sk.name)
        logger.info("vault migrate: stored %s", sk.name)

    # Back up the original yaml exactly once. If a backup already exists,
    # leave it alone (the first backup is the only authoritative one).
    backup_path = yaml_path.with_suffix(yaml_path.suffix + BACKUP_SUFFIX)
    if not backup_path.exists():
        backup_path.write_text(raw_text, encoding="utf-8")
        try:
            os.chmod(backup_path, 0o600)
        except Exception:
            pass
        result.backup_written = backup_path
        logger.warning(
            "vault migrate: wrote one-time plaintext backup at %s. "
            "DELETE OR MOVE THIS FILE once you have confirmed the migration "
            "succeeded; it still contains your original API keys.",
            backup_path,
        )

    # Rewrite the live yaml with placeholder values for everything migrated.
    redacted = parsed
    for sk, _ in to_migrate:
        _set_in(redacted, sk.yaml_path, PLACEHOLDER)
    yaml_path.write_text(
        yaml.safe_dump(redacted, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    result.yaml_rewritten = True
    logger.info(
        "vault migrate: redacted %d secret(s) from %s",
        len(result.migrated),
        yaml_path,
    )

    return result
