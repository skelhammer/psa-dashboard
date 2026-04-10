"""Phone provider factory. Reads config + vault and returns a phone provider.

Zoom credentials (account_id, client_id, client_secret) are pulled from the
SecretsManager. The non-secret yaml settings (provider name, timezone) still
come from config.yaml.
"""

from __future__ import annotations

from app.config import Settings
from app.phone.base import PhoneProvider
from app.vault.manager import SecretsManager


async def get_phone_provider(
    settings: Settings, vault: SecretsManager
) -> PhoneProvider | None:
    """Create and return a phone provider based on configuration.

    Returns None if phone integration is not configured.
    """
    phone_cfg = getattr(settings, "phone", None)
    if phone_cfg is None:
        return None

    provider_name = phone_cfg.provider.lower()

    if provider_name == "zoom":
        from app.phone.zoom import ZoomPhoneProvider
        account_id = await vault.get("phone.zoom.account_id") or ""
        client_id = await vault.get("phone.zoom.client_id") or ""
        client_secret = await vault.get("phone.zoom.client_secret") or ""
        return ZoomPhoneProvider(
            account_id=account_id,
            client_id=client_id,
            client_secret=client_secret,
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
