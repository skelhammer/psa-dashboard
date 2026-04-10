"""Provider factory. Reads config + vault and returns PSA provider instances.

Secrets (API tokens) are pulled from the SecretsManager at construction time.
Non-secret config (urls, subdomains, page size, ticket templates, custom
field overrides) still comes from config.yaml. The factory builds a copy of
the relevant config dataclass with secret fields populated from the vault,
then hands it to the provider constructor unchanged.

The vault is the source of truth for secrets. After the first-boot
migration runs, config.yaml contains placeholder strings for all secret
fields, and `vault.keys.clean_yaml_value` is used to ensure those
placeholders never escape into provider construction.
"""

from __future__ import annotations

import dataclasses

from app.config import Settings
from app.psa.base import PSAProvider
from app.vault.keys import clean_yaml_value
from app.vault.manager import SecretsManager


async def _vault_or_yaml(
    vault: SecretsManager, key: str, yaml_value: str
) -> str:
    """Return the vault value if present, else the (cleaned) yaml value.

    Used by the factory so secrets and credential fields work whether they
    have been migrated yet or not. After first-boot migration, the vault
    is the source of truth and the yaml field holds the placeholder.
    """
    val = await vault.get(key)
    if val is not None and val != "":
        return val
    return clean_yaml_value(yaml_value)


async def _create_provider(
    name: str, settings: Settings, vault: SecretsManager
) -> PSAProvider:
    """Create a single provider instance by name."""
    name = name.lower()
    if name == "superops":
        from app.psa.superops import SuperOpsProvider
        cfg = dataclasses.replace(
            settings.psa.superops,
            api_url=clean_yaml_value(settings.psa.superops.api_url),
            api_token=await _vault_or_yaml(
                vault, "psa.superops.api_token", settings.psa.superops.api_token
            ),
            subdomain=await _vault_or_yaml(
                vault, "psa.superops.subdomain", settings.psa.superops.subdomain
            ),
        )
        return SuperOpsProvider(cfg)

    if name == "zendesk":
        from app.psa.zendesk import ZendeskProvider
        cfg = dataclasses.replace(
            settings.psa.zendesk,
            api_token=await _vault_or_yaml(
                vault, "psa.zendesk.api_token", settings.psa.zendesk.api_token
            ),
            email=await _vault_or_yaml(
                vault, "psa.zendesk.email", settings.psa.zendesk.email
            ),
            subdomain=await _vault_or_yaml(
                vault, "psa.zendesk.subdomain", settings.psa.zendesk.subdomain
            ),
        )
        return ZendeskProvider(cfg)

    if name == "mock":
        from app.psa.mock import MockProvider
        return MockProvider()

    raise ValueError(
        f"Unknown PSA provider: {name}. Supported: superops, zendesk, mock"
    )


async def get_providers(
    settings: Settings, vault: SecretsManager
) -> list[PSAProvider]:
    """Create all configured PSA providers."""
    provider_names = settings.psa.providers
    if not provider_names:
        provider_names = ["mock"]
    return [await _create_provider(name, settings, vault) for name in provider_names]


async def get_provider(
    settings: Settings, vault: SecretsManager
) -> PSAProvider:
    """Create and return the first configured PSA provider (backward compat)."""
    providers = await get_providers(settings, vault)
    return providers[0]
