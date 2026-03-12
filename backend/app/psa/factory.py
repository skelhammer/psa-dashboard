"""Provider factory. Reads config and returns the correct PSA provider instance."""

from __future__ import annotations

from app.config import Settings
from app.psa.base import PSAProvider


def get_provider(settings: Settings) -> PSAProvider:
    """Create and return a PSA provider based on configuration."""
    provider_name = settings.psa.provider.lower()

    if provider_name == "superops":
        from app.psa.superops import SuperOpsProvider
        return SuperOpsProvider(settings.psa.superops)
    elif provider_name == "mock":
        from app.psa.mock import MockProvider
        return MockProvider()
    else:
        raise ValueError(f"Unknown PSA provider: {provider_name}. Supported: superops, mock")
