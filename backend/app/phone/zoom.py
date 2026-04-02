"""Zoom Phone provider implementation.

Connects to the Zoom Phone API via Server-to-Server OAuth.

Setup:
  1. Go to https://marketplace.zoom.us and create a Server-to-Server OAuth app.
  2. Add scopes: phone:read:list_users:admin, phone:read:list_call_logs:admin,
     phone:read:call_log:admin, phone:read:list_call_queues:admin,
     phone:read:list_voicemails:admin, phone:read:voicemail:admin,
     phone:read:call:admin.
  3. Copy account_id, client_id, client_secret into config.yaml under phone.zoom.

Auth flow:
  POST https://zoom.us/oauth/token
  grant_type=account_credentials
  account_id=YOUR_ACCOUNT_ID
  Basic auth with client_id:client_secret

Key API endpoints:
  GET /phone/call_logs       (30-day max range, cursor pagination, max 300/page)
  GET /phone/users           (list phone-enabled users)
  GET /phone/call_queues     (list call queues)
  GET /phone/voice_mails     (list voicemails, account-level)

Rate limits: 30 req/sec (medium), 10 req/sec (heavy).
Heavy endpoints include call_logs; we add a delay between requests to stay safe.

Call deduplication: Zoom returns one record per call leg (e.g. auto-receptionist leg
and user leg share the same call_id). We deduplicate by call_id, keeping only the
"user" or "callQueue" owner types so each physical call appears once.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.phone.base import PhoneProvider
from app.phone.models import Call, CallQueue, PaginatedCalls, PhoneUser, Voicemail

logger = logging.getLogger(__name__)

BASE_URL = "https://api.zoom.us/v2"
TOKEN_URL = "https://zoom.us/oauth/token"
MAX_PAGE_SIZE = 300
USER_PAGE_SIZE = 100
MAX_RANGE_DAYS = 30
RATE_LIMIT_DELAY = 0.12  # seconds between heavy requests

# Zoom result string -> normalized result.
# Values observed from real API data (307 records analyzed).
RESULT_MAP: dict[str, str] = {
    "Call connected": "connected",
    "Connected": "connected",
    "Answered": "connected",
    "No Answer": "missed",
    "Missed": "missed",
    "Call Cancel": "abandoned",
    "Rejected": "abandoned",
    "Busy": "abandoned",
    "Cancelled": "abandoned",
    "Canceled": "abandoned",
    "Call cancelled": "abandoned",
    "Call canceled": "abandoned",
    "Blocked": "abandoned",
    "Voicemail": "voicemail",
    "Voice Mail": "voicemail",
    "Call failed": "missed",
    "Failed": "missed",
}

# Owner types to skip during deduplication.
# Auto-receptionist legs are routing intermediaries, not the final handler.
_SKIP_OWNER_TYPES = {"autoReceptionist"}


def _parse_dt(value: str | None, tz: ZoneInfo | None = None) -> datetime | None:
    """Parse an ISO 8601 UTC timestamp from Zoom into a naive local datetime.

    Zoom returns UTC timestamps. We convert to the configured local timezone
    and strip tzinfo so all stored times are naive local, matching the
    convention used by the rest of the app (mock provider, PSA sync).
    """
    if not value:
        return None
    # Zoom returns "2026-03-25T14:30:00Z" format
    cleaned = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if tz is not None:
        dt = dt.astimezone(tz).replace(tzinfo=None)
    else:
        # Fall back to stripping timezone if no tz configured
        dt = dt.replace(tzinfo=None)
    return dt


def _safe_str(value: object, default: str = "") -> str:
    """Convert a value to string safely, returning default for None."""
    if value is None:
        return default
    return str(value)


class ZoomPhoneProvider(PhoneProvider):
    """Zoom Phone provider using Server-to-Server OAuth.

    Handles token caching with proactive refresh, rate limit backoff,
    cursor-based pagination, and call deduplication across legs.
    """

    def __init__(
        self, account_id: str, client_id: str, client_secret: str,
        timezone: str = "UTC",
    ):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self._tz = ZoneInfo(timezone)
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._client: httpx.AsyncClient | None = None
        self._next_page_token: str | None = None
        self._pagination_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # HTTP / Auth infrastructure
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> None:
        """Refresh the OAuth token if expired or about to expire (5 min buffer)."""
        if time.time() < self._token_expires_at - 300:
            return

        client = await self._get_client()
        response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "account_credentials",
                "account_id": self.account_id,
            },
            auth=(self.client_id, self.client_secret),
        )
        response.raise_for_status()
        data = response.json()

        self._access_token = data["access_token"]
        expires_in = data["expires_in"]
        self._token_expires_at = time.time() + expires_in
        logger.info("Zoom OAuth token refreshed, expires in %d seconds", expires_in)

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared httpx client, creating it if needed."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30)
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
    ) -> dict:
        """Make an authenticated request to the Zoom API.

        Handles token refresh on 401, rate limit backoff on 429,
        and adds a small delay between requests to respect rate limits.
        """
        await self._ensure_token()
        url = BASE_URL + path
        headers = {"Authorization": f"Bearer {self._access_token}"}
        client = await self._get_client()

        response = await client.request(method, url, headers=headers, params=params)

        # Handle 401: token may have expired between check and request
        if response.status_code == 401:
            logger.warning("Zoom API returned 401; refreshing token and retrying")
            self._token_expires_at = 0
            await self._ensure_token()
            headers = {"Authorization": f"Bearer {self._access_token}"}
            response = await client.request(
                method, url, headers=headers, params=params
            )

        # Handle 429: respect Retry-After header (capped at 60s)
        if response.status_code == 429:
            retry_after = min(int(response.headers.get("Retry-After", "5")), 60)
            logger.warning(
                "Zoom API rate limited; waiting %d seconds before retry",
                retry_after,
            )
            await asyncio.sleep(retry_after)
            response = await client.request(
                method, url, headers=headers, params=params
            )

        if response.status_code >= 400:
            logger.error(
                "Zoom API error: %d %s for %s %s",
                response.status_code,
                response.text[:500],
                method,
                path,
            )
            response.raise_for_status()

        # Rate limit courtesy delay
        await asyncio.sleep(RATE_LIMIT_DELAY)

        return response.json()

    async def _paginate_all(
        self, path: str, key: str, params: dict | None = None, page_size: int = 100
    ) -> list[dict]:
        """Fetch all pages from a cursor-paginated Zoom endpoint.

        Returns the combined list of records from all pages.
        """
        params = dict(params or {})
        params["page_size"] = page_size
        all_items: list[dict] = []

        while True:
            data = await self._request("GET", path, params=params)
            items = data.get(key, [])
            all_items.extend(items)

            next_token = data.get("next_page_token", "")
            if not next_token:
                break
            params["next_page_token"] = next_token

        return all_items

    # ------------------------------------------------------------------
    # PhoneProvider interface: Users
    # ------------------------------------------------------------------

    async def get_users(self) -> list[PhoneUser]:
        """Fetch all Zoom Phone users."""
        raw_users = await self._paginate_all(
            "/phone/users", "users", page_size=USER_PAGE_SIZE
        )
        users: list[PhoneUser] = []
        for u in raw_users:
            users.append(
                PhoneUser(
                    id=u["id"],
                    email=u.get("email", ""),
                    name=u.get("name", ""),
                    extension=str(u.get("extension_number", "")),
                    department=u.get("department") or None,
                    status="active" if u.get("status") == "activate" else "inactive",
                )
            )
        logger.info("Fetched %d Zoom Phone users", len(users))
        return users

    # ------------------------------------------------------------------
    # PhoneProvider interface: Call Queues
    # ------------------------------------------------------------------

    async def get_call_queues(self) -> list[CallQueue]:
        """Fetch all Zoom Phone call queues."""
        raw_queues = await self._paginate_all(
            "/phone/call_queues", "call_queues", page_size=USER_PAGE_SIZE
        )
        queues: list[CallQueue] = []
        for q in raw_queues:
            # member_count is not directly in the list response;
            # we use 0 as default and it gets updated if available
            queues.append(
                CallQueue(
                    id=q["id"],
                    name=q.get("name", ""),
                    extension=str(q.get("extension_number", "")),
                    member_count=q.get("member_count", 0),
                )
            )
        logger.info("Fetched %d Zoom Phone call queues", len(queues))
        return queues

    # ------------------------------------------------------------------
    # PhoneProvider interface: Call Logs
    # ------------------------------------------------------------------

    async def get_call_logs(
        self, from_date: datetime, to_date: datetime, page: int = 1
    ) -> PaginatedCalls:
        """Fetch call logs for a date range with cursor-based pagination.

        The sync engine calls this with incrementing page numbers (1, 2, 3...).
        We translate this to Zoom's cursor pagination internally:
        page=1 starts a fresh query; page>1 uses the cached next_page_token.

        Zoom enforces a 30-day maximum range. If the requested range exceeds
        30 days, we fetch multiple 30-day chunks and combine them.
        """
        # Clamp range to MAX_RANGE_DAYS
        total_days = (to_date - from_date).days
        if total_days > MAX_RANGE_DAYS:
            # For multi-chunk ranges, fetch all at once on page 1
            if page > 1:
                return PaginatedCalls(
                    items=[], page=page, page_size=MAX_PAGE_SIZE,
                    has_more=False, total_count=0,
                )
            return await self._fetch_chunked_call_logs(from_date, to_date)

        # Lock prevents concurrent pagination from clobbering cursor state
        async with self._pagination_lock:
            # Reset cursor on page 1
            if page == 1:
                self._next_page_token = None

            params: dict = {
                "from": from_date.strftime("%Y-%m-%d"),
                "to": to_date.strftime("%Y-%m-%d"),
                "page_size": MAX_PAGE_SIZE,
                "type": "all",
            }
            if self._next_page_token:
                params["next_page_token"] = self._next_page_token

            data = await self._request("GET", "/phone/call_logs", params=params)
            raw_logs = data.get("call_logs", [])
            next_token = data.get("next_page_token", "")
            total = data.get("total_records", 0)

            # Cache cursor for next page call
            self._next_page_token = next_token if next_token else None

        calls = self._map_call_logs(raw_logs)

        return PaginatedCalls(
            items=calls,
            page=page,
            page_size=MAX_PAGE_SIZE,
            has_more=bool(next_token),
            total_count=total,
        )

    async def _fetch_chunked_call_logs(
        self, from_date: datetime, to_date: datetime
    ) -> PaginatedCalls:
        """Fetch call logs in 30-day chunks when range exceeds the API limit."""
        all_calls: list[Call] = []
        chunk_start = from_date

        while chunk_start < to_date:
            chunk_end = min(chunk_start + timedelta(days=MAX_RANGE_DAYS), to_date)
            logger.info(
                "Fetching Zoom call logs chunk: %s to %s",
                chunk_start.strftime("%Y-%m-%d"),
                chunk_end.strftime("%Y-%m-%d"),
            )

            # Fetch all pages for this chunk
            params: dict = {
                "from": chunk_start.strftime("%Y-%m-%d"),
                "to": chunk_end.strftime("%Y-%m-%d"),
                "page_size": MAX_PAGE_SIZE,
                "type": "all",
            }
            while True:
                data = await self._request("GET", "/phone/call_logs", params=params)
                raw_logs = data.get("call_logs", [])
                all_calls.extend(self._map_call_logs(raw_logs))

                next_token = data.get("next_page_token", "")
                if not next_token:
                    break
                params["next_page_token"] = next_token

            chunk_start = chunk_end

        return PaginatedCalls(
            items=all_calls,
            page=1,
            page_size=len(all_calls),
            has_more=False,
            total_count=len(all_calls),
        )

    def _map_call_logs(self, raw_logs: list[dict]) -> list[Call]:
        """Map raw Zoom call log records to normalized Call objects.

        Deduplicates by call_id, keeping only user/callQueue owner types
        to avoid counting auto-receptionist legs separately.
        """
        seen_call_ids: set[str] = set()
        calls: list[Call] = []

        for entry in raw_logs:
            # Deduplicate: skip auto-receptionist routing legs
            owner_type = entry.get("owner", {}).get("type", "")
            if owner_type in _SKIP_OWNER_TYPES:
                continue
            if owner_type and owner_type not in ("user", "callQueue", "commonArea", "sharedLineGroup"):
                logger.debug("Unknown Zoom call owner type: %s", owner_type)

            call_id = entry.get("call_id", entry.get("id", ""))
            if call_id in seen_call_ids:
                continue
            seen_call_ids.add(call_id)

            # Parse timestamps
            start_time = _parse_dt(entry.get("date_time"), self._tz)
            if not start_time:
                continue  # skip records without a start time

            answer_time = _parse_dt(entry.get("answer_start_time"), self._tz)
            call_end_time = _parse_dt(entry.get("call_end_time"), self._tz)
            duration = entry.get("duration", 0)

            # Compute end_time: prefer call_end_time, fall back to start + duration
            if call_end_time:
                end_time = call_end_time
            else:
                end_time = start_time + timedelta(seconds=duration)

            # Map result
            raw_result = entry.get("result", "")
            result = RESULT_MAP.get(raw_result, "missed")
            if raw_result and raw_result not in RESULT_MAP:
                logger.warning(
                    "Unknown Zoom call result '%s' for call %s; defaulting to 'missed'",
                    raw_result,
                    entry.get("id", "?"),
                )

            # Extract queue info from path
            path = entry.get("path", "")
            queue_id = None
            queue_name = None
            if path == "callQueue":
                owner = entry.get("owner", {})
                if owner.get("type") == "callQueue":
                    queue_id = owner.get("id")
                    queue_name = owner.get("name")

            calls.append(
                Call(
                    id=entry.get("id", ""),
                    direction=entry.get("direction", "inbound"),
                    caller_number=_safe_str(entry.get("caller_number")),
                    caller_name=_safe_str(entry.get("caller_name")),
                    callee_number=_safe_str(entry.get("callee_number")),
                    callee_name=_safe_str(entry.get("callee_name")),
                    start_time=start_time,
                    answer_time=answer_time,
                    end_time=end_time,
                    duration=duration,
                    wait_time=entry.get("waiting_time", 0) or 0,
                    hold_time=entry.get("hold_time", 0) or 0,
                    result=result,
                    user_id=entry.get("user_id"),
                    user_email=None,  # not in call log response; matched via user table
                    queue_id=queue_id,
                    queue_name=queue_name,
                    has_recording=entry.get("has_recording", False),
                    has_voicemail=entry.get("has_voicemail", False),
                )
            )

        return calls

    # ------------------------------------------------------------------
    # PhoneProvider interface: Queue Calls
    # ------------------------------------------------------------------

    async def get_queue_calls(
        self, queue_id: str, from_date: datetime, to_date: datetime
    ) -> list[Call]:
        """Fetch calls for a specific queue by filtering call logs.

        Zoom does not have a dedicated queue call log endpoint, so we
        fetch all call logs and filter by queue_id. This matches the
        pattern used by the mock provider.
        """
        all_calls: list[Call] = []
        page = 1
        max_pages = 50

        while page <= max_pages:
            result = await self.get_call_logs(from_date, to_date, page)
            for call in result.items:
                if call.queue_id == queue_id:
                    all_calls.append(call)
            if not result.has_more:
                break
            page += 1

        return all_calls

    # ------------------------------------------------------------------
    # PhoneProvider interface: Voicemails
    # ------------------------------------------------------------------

    async def get_voicemails(self, user_id: str) -> list[Voicemail]:
        """Fetch voicemails for a specific user."""
        raw_vms = await self._paginate_all(
            f"/phone/users/{user_id}/voice_mails",
            "voice_mails",
            page_size=USER_PAGE_SIZE,
        )
        voicemails: list[Voicemail] = []
        for vm in raw_vms:
            timestamp = _parse_dt(vm.get("date_time"), self._tz)
            if not timestamp:
                continue

            # Normalize caller number: Zoom sometimes omits the "+" prefix
            caller_number = _safe_str(vm.get("caller_number"))
            if caller_number and not caller_number.startswith("+"):
                caller_number = "+" + caller_number

            voicemails.append(
                Voicemail(
                    id=vm.get("id", ""),
                    caller_number=caller_number,
                    caller_name=_safe_str(vm.get("caller_name")),
                    user_id=user_id,
                    duration=vm.get("duration", 0),
                    timestamp=timestamp,
                    status=vm.get("status", "unread"),
                )
            )

        logger.info("Fetched %d voicemails for user %s", len(voicemails), user_id)
        return voicemails

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def get_provider_name(self) -> str:
        return "Zoom Phone"

    async def close(self) -> None:
        """Close the underlying httpx client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("Zoom Phone HTTP client closed")
