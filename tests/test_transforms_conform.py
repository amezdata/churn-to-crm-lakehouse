"""Conforming of attendance aliases, event-type typos and whitespace."""

from transforms.conform import conform_row, conform_rows
from transforms.dedup import deduplicate_rows


def test_attendance_aliases_are_canonical() -> None:
    rows = [
        {"attendance_status": "attended"},
        {"attendance_status": "no_show"},
        {"attendance_status": "tardy"},
        {"attendance_status": "excused_absence"},
        {"attendance_status": "present"},
    ]
    conformed = conform_rows("attendance", rows)
    assert [row["attendance_status"] for row in conformed] == [
        "present",
        "absent",
        "late",
        "excused",
        "present",
    ]


def test_event_typos_are_normalized() -> None:
    started = conform_row("platform_logs", {"event_type": "session_startedd", "student_token": ""})
    paused = conform_row("platform_logs", {"event_type": "session_pause", "student_token": "  "})
    assert started["event_type"] == "session_started"
    assert started["student_token"] is None
    assert paused["event_type"] == "session_paused"
    assert paused["student_token"] is None


def test_room_name_is_stripped() -> None:
    row = conform_row("rooms", {"room_name": "Platform hall "})
    assert row["room_name"] == "Platform hall"


def test_logs_dedup_keeps_last_event_id() -> None:
    rows = [
        {"event_id": "aa", "event_type": "session_started"},
        {"event_id": "aa", "event_type": "session_started"},
        {"event_id": "bb", "event_type": "session_completed"},
    ]
    unique = deduplicate_rows("platform_logs", rows)
    assert len(unique) == 2
    assert {row["event_id"] for row in unique} == {"aa", "bb"}
