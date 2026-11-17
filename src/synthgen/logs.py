"""Platform session event logs (JSON). Lifecycle only, no pedagogical scoring."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from synthgen.constants import (
    ATTENDANCE_LATE,
    ATTENDANCE_PRESENT,
    EVENT_ABANDONED,
    EVENT_COMPLETED,
    EVENT_PAUSED,
    EVENT_RESUMED,
    EVENT_STARTED,
    PLATFORM_ABANDON_RATE,
    PLATFORM_EVENT_TYPES,
    PLATFORM_PAUSE_RATE,
    SOURCE_SYSTEM,
)
from synthgen.tokens import make_token


def build_platform_logs(
    rng: random.Random,
    attendance: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    enrolments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Emit started/paused/resumed/completed/abandoned events per visit."""
    session_by_key = {row["session_natural_key"]: row for row in sessions}
    enrolment_by_key = {row["enrolment_natural_key"]: row for row in enrolments}
    events: list[dict[str, Any]] = []

    for row in attendance:
        if row["status"] not in {ATTENDANCE_PRESENT, ATTENDANCE_LATE}:
            continue
        enrolment = enrolment_by_key.get(row["enrolment_natural_key"])
        session = session_by_key.get(row["session_natural_key"])
        if enrolment is None or session is None:
            continue
        if enrolment["program_natural_key"] not in {"prg_level_1", "prg_level_2"}:
            continue
        events.extend(_lifecycle_for_visit(rng, row, enrolment, session))

    assert events
    assert all(event["event_type"] in PLATFORM_EVENT_TYPES for event in events)
    return events


def _lifecycle_for_visit(
    rng: random.Random,
    attendance: dict[str, Any],
    enrolment: dict[str, Any],
    session: dict[str, Any],
) -> list[dict[str, Any]]:
    started_at = _event_clock(attendance, session, rng)
    platform_session_id = make_token(
        "platform_session",
        attendance["student_natural_key"],
        session["session_natural_key"],
    )
    events = [
        _event(
            event_type=EVENT_STARTED,
            event_ts=started_at,
            platform_session_id=platform_session_id,
            attendance=attendance,
            enrolment=enrolment,
            session=session,
            step_index=1,
        )
    ]
    cursor = started_at
    if rng.random() < PLATFORM_PAUSE_RATE:
        cursor = cursor + timedelta(minutes=rng.randint(8, 25))
        events.append(
            _event(
                event_type=EVENT_PAUSED,
                event_ts=cursor,
                platform_session_id=platform_session_id,
                attendance=attendance,
                enrolment=enrolment,
                session=session,
                step_index=rng.randint(1, 4),
            )
        )
        cursor = cursor + timedelta(minutes=rng.randint(3, 12))
        events.append(
            _event(
                event_type=EVENT_RESUMED,
                event_ts=cursor,
                platform_session_id=platform_session_id,
                attendance=attendance,
                enrolment=enrolment,
                session=session,
                step_index=events[-1]["step_index"],
            )
        )

    cursor = cursor + timedelta(minutes=rng.randint(20, 70))
    closing = (
        EVENT_ABANDONED if rng.random() < PLATFORM_ABANDON_RATE else EVENT_COMPLETED
    )
    events.append(
        _event(
            event_type=closing,
            event_ts=cursor,
            platform_session_id=platform_session_id,
            attendance=attendance,
            enrolment=enrolment,
            session=session,
            step_index=rng.randint(2, 8),
        )
    )
    return events


def _event_clock(
    attendance: dict[str, Any],
    session: dict[str, Any],
    rng: random.Random,
) -> datetime:
    if attendance["check_in_time"]:
        return datetime.fromisoformat(attendance["check_in_time"])
    base = datetime.fromisoformat(f"{session['session_date']}T{session['start_time']}:00")
    return base + timedelta(minutes=rng.randint(0, 8))


def _event(
    *,
    event_type: str,
    event_ts: datetime,
    platform_session_id: str,
    attendance: dict[str, Any],
    enrolment: dict[str, Any],
    session: dict[str, Any],
    step_index: int,
) -> dict[str, Any]:
    return {
        "event_id": make_token("event", platform_session_id, event_type, event_ts.isoformat()),
        "event_ts": event_ts.isoformat(timespec="seconds"),
        "event_type": event_type,
        "platform_session_id": platform_session_id,
        "student_natural_key": attendance["student_natural_key"],
        "project_id": enrolment["project_id"],
        "step_index": step_index,
        "class_session_natural_key": session["session_natural_key"],
        "source_system": SOURCE_SYSTEM,
    }
