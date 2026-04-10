"""Canonical registry of secret keys.

This is the single source of truth for which configuration fields are
secrets and how they map between vault key names and config.yaml paths.
The migration, the factories, and the admin Settings UI all reference
this list so they cannot drift out of sync.

Adding a new secret-bearing provider:
1. Add an entry to SECRET_KEYS below.
2. Update the corresponding factory in app/psa/ or app/phone/ to call
   `await vault.get(...)` for the new key.
3. The migration and the Settings UI will pick it up automatically.
"""

from __future__ import annotations

from dataclasses import dataclass

# Sentinel written into config.yaml fields after they have been migrated
# into the vault. Code that consumes config values must treat this string
# as "no value" so it never lands in an HTTP Authorization header.
PLACEHOLDER = "__stored_in_db__"


@dataclass(frozen=True)
class SecretKey:
    name: str           # vault key, e.g. "psa.superops.api_token"
    yaml_path: tuple    # path into the parsed yaml dict, e.g. ("psa", "superops", "api_token")
    label: str          # human-readable label for the Settings UI
    provider: str       # logical provider name for grouping in the UI
    secret: bool = True  # if False, the value is returned through the API for display
                         # in the Settings UI (e.g. usernames, subdomains). Both kinds
                         # are stored encrypted at rest; the flag only controls whether
                         # the plaintext value is allowed to leave the backend.


SECRET_KEYS: tuple[SecretKey, ...] = (
    # SuperOps
    SecretKey(
        name="psa.superops.subdomain",
        yaml_path=("psa", "superops", "subdomain"),
        label="SuperOps Subdomain",
        provider="superops",
        secret=False,
    ),
    SecretKey(
        name="psa.superops.api_token",
        yaml_path=("psa", "superops", "api_token"),
        label="SuperOps API Token",
        provider="superops",
    ),

    # Zendesk
    SecretKey(
        name="psa.zendesk.subdomain",
        yaml_path=("psa", "zendesk", "subdomain"),
        label="Zendesk Subdomain",
        provider="zendesk",
        secret=False,
    ),
    SecretKey(
        name="psa.zendesk.email",
        yaml_path=("psa", "zendesk", "email"),
        label="Zendesk Email",
        provider="zendesk",
        secret=False,
    ),
    SecretKey(
        name="psa.zendesk.api_token",
        yaml_path=("psa", "zendesk", "api_token"),
        label="Zendesk API Token",
        provider="zendesk",
    ),

    # Zoom Phone
    SecretKey(
        name="phone.zoom.account_id",
        yaml_path=("phone", "zoom", "account_id"),
        label="Zoom Account ID",
        provider="zoom",
    ),
    SecretKey(
        name="phone.zoom.client_id",
        yaml_path=("phone", "zoom", "client_id"),
        label="Zoom Client ID",
        provider="zoom",
    ),
    SecretKey(
        name="phone.zoom.client_secret",
        yaml_path=("phone", "zoom", "client_secret"),
        label="Zoom Client Secret",
        provider="zoom",
    ),
)


SECRET_KEY_NAMES: frozenset[str] = frozenset(k.name for k in SECRET_KEYS)


def is_placeholder(value) -> bool:
    """Return True if a value is the post-migration placeholder string."""
    return isinstance(value, str) and value.strip() == PLACEHOLDER


def clean_yaml_value(value) -> str:
    """Return '' if value is the placeholder, else value coerced to str.

    Used by factories so the placeholder string never escapes config-parsing
    into actual provider construction.
    """
    if value is None:
        return ""
    if is_placeholder(value):
        return ""
    return str(value)
