"""Phone provider factory. Reads config and returns the correct phone provider."""

from __future__ import annotations

from app.config import Settings
from app.phone.base import PhoneProvider


def get_phone_provider(settings: Settings) -> PhoneProvider | None:
    """Create and return a phone provider based on configuration.

    Returns None if phone integration is not configured.
    """
    phone_cfg = getattr(settings, "phone", None)
    if phone_cfg is None:
        return None

    provider_name = phone_cfg.provider.lower()

    if provider_name == "zoom":
        from app.phone.zoom import ZoomPhoneProvider
        return ZoomPhoneProvider(
            account_id=phone_cfg.zoom.account_id,
            client_id=phone_cfg.zoom.client_id,
            client_secret=phone_cfg.zoom.client_secret,
            timezone=settings.server.timezone,
        )
    elif provider_name == "mock":
        from app.phone.mock import MockPhoneProvider
        return MockPhoneProvider()
    elif provider_name == "none":
        return None
    else:
        raise ValueError(
            f"Unknown phone provider: {provider_name}. Supported: zoom, mock, none"
        )
