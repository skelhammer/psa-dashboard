"""Zoom Phone provider stub.

Requires a Zoom Server-to-Server OAuth app with the following scopes:
  - phone:read:admin
  - phone:read:call_log:admin

Auth flow:
  POST https://zoom.us/oauth/token
  grant_type=account_credentials
  account_id=YOUR_ACCOUNT_ID

Key API endpoints:
  GET /phone/call_logs       (30-day max range, cursor pagination, max 300/page)
  GET /phone/users           (list phone-enabled users)
  GET /phone/call_queues     (list call queues)
  GET /phone/users/{userId}/call_logs
  GET /phone/users/{userId}/voice_mails

Rate limits: 30 req/sec (medium), 10 req/sec (heavy)

To set up:
  1. Go to https://marketplace.zoom.us and create a Server-to-Server OAuth app
  2. Add scopes: phone:read:admin, phone:read:call_log:admin
  3. Copy account_id, client_id, client_secret to config.yaml
"""

from __future__ import annotations

from datetime import datetime

from app.phone.base import PhoneProvider
from app.phone.models import Call, CallQueue, PaginatedCalls, PhoneUser, Voicemail


class ZoomPhoneProvider(PhoneProvider):
    """Zoom Phone provider stub. Not yet implemented.

    Set phone.provider to 'mock' in config.yaml for development.
    """

    def __init__(self, account_id: str, client_id: str, client_secret: str):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = None

    async def get_call_logs(
        self, from_date: datetime, to_date: datetime, page: int = 1
    ) -> PaginatedCalls:
        raise NotImplementedError(
            "Zoom Phone integration not yet implemented. "
            "Configure phone.zoom.account_id, client_id, and client_secret in config.yaml, "
            "then implement OAuth token exchange and call log fetching."
        )

    async def get_users(self) -> list[PhoneUser]:
        raise NotImplementedError(
            "Zoom Phone integration not yet implemented. "
            "See zoom.py module docstring for setup instructions."
        )

    async def get_call_queues(self) -> list[CallQueue]:
        raise NotImplementedError(
            "Zoom Phone integration not yet implemented."
        )

    async def get_queue_calls(
        self, queue_id: str, from_date: datetime, to_date: datetime
    ) -> list[Call]:
        raise NotImplementedError(
            "Zoom Phone integration not yet implemented."
        )

    async def get_voicemails(self, user_id: str) -> list[Voicemail]:
        raise NotImplementedError(
            "Zoom Phone integration not yet implemented."
        )

    def get_provider_name(self) -> str:
        return "Zoom Phone"
