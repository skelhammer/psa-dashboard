"""Mock phone provider for testing and frontend development.

Generates realistic call data: 8 agents, 2 queues, 50-100 calls/day.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from app.phone.base import PhoneProvider
from app.phone.models import Call, CallQueue, PaginatedCalls, PhoneUser, Voicemail

MOCK_PHONE_USERS = [
    PhoneUser(id="pu1", email="alex@example.com", name="Alex Morgan", extension="101", department="Support"),
    PhoneUser(id="pu2", email="mike@example.com", name="Mike Chen", extension="102", department="Support"),
    PhoneUser(id="pu3", email="sarah@example.com", name="Sarah Johnson", extension="103", department="Support"),
    PhoneUser(id="pu4", email="james@example.com", name="James Wilson", extension="104", department="Support"),
    PhoneUser(id="pu5", email="lisa@example.com", name="Lisa Park", extension="105", department="Support"),
    PhoneUser(id="pu6", email="david@example.com", name="David Brown", extension="106", department="Support"),
    PhoneUser(id="pu7", email="emma@example.com", name="Emma Davis", extension="107", department="Dispatch"),
    PhoneUser(id="pu8", email="ryan@example.com", name="Ryan Taylor", extension="108", department="Dispatch"),
]

MOCK_QUEUES = [
    CallQueue(id="q1", name="Main Line", extension="200", member_count=6),
    CallQueue(id="q2", name="Support Queue", extension="201", member_count=4),
]

# Client phone number mapping (for call-to-client matching)
_CLIENT_PHONES = {
    "5035551001": ("c1", "Acme Corp"),
    "5035551002": ("c2", "Riverside Dental"),
    "5035551003": ("c3", "Greenfield County"),
    "5035551004": ("c4", "Valley Credit Union"),
    "5035551005": ("c5", "Summit Manufacturing"),
}

_CALLER_NAMES = [
    "John Smith", "Jane Doe", "Bob Wilson", "Alice Brown", "Tom Harris",
    "Susan Lee", "Mark Davis", "Karen Miller", "Paul Anderson", "Nancy White",
    "Chris Martin", "Laura Clark", "Steve Hall", "Julie Young", "Brian King",
]


def _deterministic_seed(date: datetime, index: int) -> int:
    """Generate a deterministic seed from date and index for repeatable mock data."""
    key = f"{date.strftime('%Y-%m-%d')}-{index}"
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def _generate_calls_for_day(date: datetime) -> list[Call]:
    """Generate 50-100 mock calls for a given day."""
    day_seed = int(hashlib.md5(date.strftime("%Y-%m-%d").encode()).hexdigest()[:8], 16)
    rng = random.Random(day_seed)

    # Skip weekends (fewer calls)
    if date.weekday() >= 5:
        num_calls = rng.randint(5, 15)
    else:
        num_calls = rng.randint(50, 100)

    calls = []
    for i in range(num_calls):
        call_rng = random.Random(_deterministic_seed(date, i))

        # Time distribution: peaks at 9-11 AM and 1-3 PM
        hour_weights = [0] * 24
        for h in range(8, 18):
            if 9 <= h <= 11:
                hour_weights[h] = 3
            elif 13 <= h <= 15:
                hour_weights[h] = 2.5
            else:
                hour_weights[h] = 1
        hour = call_rng.choices(range(24), weights=hour_weights, k=1)[0]
        minute = call_rng.randint(0, 59)
        second = call_rng.randint(0, 59)
        start_time = date.replace(hour=hour, minute=minute, second=second)

        # Direction: 70% inbound, 30% outbound
        direction = call_rng.choices(["inbound", "outbound"], weights=[70, 30], k=1)[0]

        # Result: 85% connected, 5% missed, 5% voicemail, 5% abandoned
        result = call_rng.choices(
            ["connected", "missed", "voicemail", "abandoned"],
            weights=[85, 5, 5, 5],
            k=1,
        )[0]

        # Assign agent
        agent = call_rng.choice(MOCK_PHONE_USERS)

        # Queue (60% through queue for inbound, 0% for outbound)
        queue = None
        wait_time = 0
        if direction == "inbound" and call_rng.random() < 0.6:
            queue = call_rng.choice(MOCK_QUEUES)
            wait_time = call_rng.randint(10, 120)

        # Duration: 2-15 min average for connected, 0 for missed/abandoned
        if result == "connected":
            duration = call_rng.randint(120, 900)  # 2-15 min
            answer_time = start_time + timedelta(seconds=wait_time)
        elif result == "voicemail":
            duration = call_rng.randint(15, 90)
            answer_time = None
        else:
            duration = 0
            answer_time = None

        hold_time = call_rng.randint(0, 60) if result == "connected" and call_rng.random() < 0.2 else 0
        end_time = start_time + timedelta(seconds=wait_time + duration)

        # Caller info
        phone_keys = list(_CLIENT_PHONES.keys())
        if direction == "inbound":
            if call_rng.random() < 0.7:  # 70% from known clients
                phone_num = call_rng.choice(phone_keys)
                client_id, _ = _CLIENT_PHONES[phone_num]
                caller_name = call_rng.choice(_CALLER_NAMES)
            else:
                phone_num = f"503555{call_rng.randint(2000, 9999)}"
                client_id = None
                caller_name = call_rng.choice(_CALLER_NAMES)
            caller_number = phone_num
            callee_number = queue.extension if queue else agent.extension
            callee_name = queue.name if queue else agent.name
        else:
            caller_number = agent.extension
            caller_name = agent.name
            if call_rng.random() < 0.7:
                phone_num = call_rng.choice(phone_keys)
                client_id, _ = _CLIENT_PHONES[phone_num]
            else:
                phone_num = f"503555{call_rng.randint(2000, 9999)}"
                client_id = None
            callee_number = phone_num
            callee_name = call_rng.choice(_CALLER_NAMES)

        call_id = f"call-{date.strftime('%Y%m%d')}-{i:04d}"

        calls.append(Call(
            id=call_id,
            direction=direction,
            caller_number=caller_number,
            caller_name=caller_name,
            callee_number=callee_number,
            callee_name=callee_name,
            start_time=start_time,
            answer_time=answer_time,
            end_time=end_time,
            duration=duration,
            wait_time=wait_time,
            hold_time=hold_time,
            result=result,
            user_id=agent.id,
            user_email=agent.email,
            queue_id=queue.id if queue else None,
            queue_name=queue.name if queue else None,
            has_recording=result == "connected" and call_rng.random() < 0.9,
            has_voicemail=result == "voicemail",
            client_id=client_id,
        ))

    return calls


class MockPhoneProvider(PhoneProvider):
    """Mock phone provider for development without a live phone system."""

    async def get_call_logs(
        self, from_date: datetime, to_date: datetime, page: int = 1
    ) -> PaginatedCalls:
        all_calls: list[Call] = []
        current = from_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = to_date.replace(hour=23, minute=59, second=59, microsecond=0)

        while current <= end:
            all_calls.extend(_generate_calls_for_day(current))
            current += timedelta(days=1)

        # Sort by start_time descending
        all_calls.sort(key=lambda c: c.start_time, reverse=True)

        page_size = 300
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = all_calls[start_idx:end_idx]

        return PaginatedCalls(
            items=page_items,
            page=page,
            page_size=page_size,
            has_more=end_idx < len(all_calls),
            total_count=len(all_calls),
        )

    async def get_users(self) -> list[PhoneUser]:
        return list(MOCK_PHONE_USERS)

    async def get_call_queues(self) -> list[CallQueue]:
        return list(MOCK_QUEUES)

    async def get_queue_calls(
        self, queue_id: str, from_date: datetime, to_date: datetime
    ) -> list[Call]:
        result = await self.get_call_logs(from_date, to_date)
        return [c for c in result.items if c.queue_id == queue_id]

    async def get_voicemails(self, user_id: str) -> list[Voicemail]:
        # Generate a few mock voicemails
        rng = random.Random(42)
        vms = []
        now = datetime.now()
        for i in range(rng.randint(2, 5)):
            vms.append(Voicemail(
                id=f"vm-{user_id}-{i}",
                caller_number=f"503555{rng.randint(1000, 9999)}",
                caller_name=rng.choice(_CALLER_NAMES),
                user_id=user_id,
                duration=rng.randint(15, 120),
                timestamp=now - timedelta(hours=rng.randint(1, 72)),
                status=rng.choice(["read", "unread"]),
            ))
        return vms

    def get_provider_name(self) -> str:
        return "Mock Phone"
