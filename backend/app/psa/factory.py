"""Provider factory. Reads config and returns PSA provider instances."""

from __future__ import annotations

from app.config import Settings
from app.psa.base import PSAProvider


def _create_provider(name: str, settings: Settings) -> PSAProvider:
    """Create a single provider instance by name."""
    name = name.lower()
    if name == "superops":
        from app.psa.superops import SuperOpsProvider
        return SuperOpsProvider(settings.psa.superops)
    elif name == "zendesk":
        from app.psa.zendesk import ZendeskProvider
        return ZendeskProvider(settings.psa.zendesk)
    elif name == "mock":
        from app.psa.mock import MockProvider
        return MockProvider()
    else:
        raise ValueError(f"Unknown PSA provider: {name}. Supported: superops, zendesk, mock")


def get_provider(settings: Settings) -> PSAProvider:
    """Create and return the first configured PSA provider (backward compat)."""
    providers = get_providers(settings)
    return providers[0]


def get_providers(settings: Settings) -> list[PSAProvider]:
    """Create all configured PSA providers."""
    provider_names = settings.psa.providers
    if not provider_names:
        provider_names = ["mock"]
    return [_create_provider(name, settings) for name in provider_names]
