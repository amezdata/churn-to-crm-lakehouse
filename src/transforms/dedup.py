"""Deduplication by business key (a defense against duplicate appends and the log mess)."""

from __future__ import annotations

from typing import Any

DEDUP_KEYS = {
    "platform_logs": "event_id",
    "students": "student_token",
    "guardians": "guardian_token",
    "employees": "employee_token",
    "programs": "program_key",
    "projects": "project_id",
    "rooms": "room_key",
    "leads": "lead_key",
    "offerings": "offering_key",
    "enrolments": "enrolment_key",
    "payments": "payment_key",
    "sessions": "session_key",
    "attendance": "attendance_key",
    "occupancy": "occupancy_key",
    "stemstar_students": "student_token",
    "stemstar_enrolments": "enrolment_id",
    "stemstar_attendance": "attendance_id",
    "stemstar_absences": "absence_id",
    "stemstar_employees": "employee_token",
    "stemstar_kpi": "kpi_id",
}


def deduplicate_rows(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last occurrence of each key. With no key, leave the order untouched."""
    key_column = DEDUP_KEYS.get(table_name)
    if key_column is None:
        return list(rows)
    by_key: dict[Any, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []
    for row in rows:
        key = row.get(key_column)
        if key is None:
            passthrough.append(row)
            continue
        by_key[key] = row
    return list(by_key.values()) + passthrough
