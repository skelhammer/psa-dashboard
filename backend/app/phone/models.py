"""Normalized phone data models. PSA-agnostic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Call:
    id: str
    direction: str  # inbound, outbound
    caller_number: str
    caller_name: str
    callee_number: str
    callee_name: str
    start_time: datetime
    answer_time: datetime | None
    end_time: datetime
    duration: int  # seconds
    wait_time: int  # seconds (queue wait)
    hold_time: int  # seconds
    result: str  # connected, missed, voicemail, abandoned
    user_id: str | None  # agent who handled
    user_email: str | None  # for matching to technicians
    queue_id: str | None
    queue_name: str | None
    has_recording: bool = False
    has_voicemail: bool = False
    client_id: str | None = None  # matched via caller number


@dataclass
class PhoneUser:
    id: str
    email: str
    name: str
    extension: str
    department: str | None = None
    status: str = "active"  # active, inactive


@dataclass
class CallQueue:
    id: str
    name: str
    extension: str
    member_count: int


@dataclass
class Voicemail:
    id: str
    caller_number: str
    caller_name: str
    user_id: str
    duration: int
    timestamp: datetime
    status: str = "unread"  # read, unread


@dataclass
class PaginatedCalls:
    items: list[Call]
    page: int
    page_size: int
    has_more: bool
    total_count: int
