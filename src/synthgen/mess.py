"""Deliberate Bronze defects. Cleaning them up is the job of Silver/Gold."""

from __future__ import annotations

import copy
import random
from typing import Any

from synthgen.constants import (
    EVENT_PAUSED,
    EVENT_STARTED,
    MESS_DUPLICATE_EVENT_RATE,
    MESS_MISSING_CHECKIN_RATE,
    MESS_MISSING_TOKEN_RATE,
    MESS_MIXED_ATTENDANCE_RATE,
    MESS_TYPO_EVENT_RATE,
)

ATTENDANCE_ALIASES = {
    "present": "attended",
    "absent": "no_show",
    "late": "tardy",
    "excused": "excused_absence",
}
EVENT_TYPOS = {
    EVENT_STARTED: "session_startedd",
    EVENT_PAUSED: "session_pause",
}


def apply_bronze_mess(
    rng: random.Random, tables: dict[str, list[dict[str, Any]]]
) -> dict[str, list[dict[str, Any]]]:
    """Copy the tables and apply the typical mess of an operational source (Bronze)."""
    dirty = {name: [copy.deepcopy(row) for row in rows] for name, rows in tables.items()}
    _mess_attendance(rng, dirty.get("attendance", []))
    _mess_logs(rng, dirty.get("platform_logs", []))
    _mess_rooms(dirty.get("rooms", []))
    return dirty


def _mess_attendance(rng: random.Random, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        if rng.random() < MESS_MIXED_ATTENDANCE_RATE:
            row["status"] = ATTENDANCE_ALIASES.get(row["status"], row["status"])
        if row["check_in_time"] and rng.random() < MESS_MISSING_CHECKIN_RATE:
            row["check_in_time"] = ""


def _mess_logs(rng: random.Random, rows: list[dict[str, Any]]) -> None:
    extras: list[dict[str, Any]] = []
    for row in rows:
        if rng.random() < MESS_MISSING_TOKEN_RATE:
            row["student_natural_key"] = ""
        if rng.random() < MESS_TYPO_EVENT_RATE:
            row["event_type"] = EVENT_TYPOS.get(row["event_type"], row["event_type"])
        if rng.random() < MESS_DUPLICATE_EVENT_RATE:
            extras.append(copy.deepcopy(row))
        if rng.random() < 0.03:
            row["client_build"] = "dev-local"
    rows.extend(extras)


def _mess_rooms(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        if row["room_natural_key"] == "room_platform_hall":
            row["room_name"] = "Platform hall "
            break
