"""Stable surrogate keys. Source HMAC tokens are never re-hashed."""

from __future__ import annotations

import hashlib
from typing import Any

SURROGATE_SPECS: dict[str, tuple[str, str]] = {
    "students": ("student_id", "student_token"),
    "guardians": ("guardian_id", "guardian_token"),
    "employees": ("employee_id", "employee_token"),
    "programs": ("program_id", "program_key"),
    "projects": ("project_sk", "project_id"),
    "rooms": ("room_id", "room_key"),
    "leads": ("lead_id", "lead_key"),
    "offerings": ("offering_id", "offering_key"),
    "enrolments": ("enrolment_id", "enrolment_key"),
    "payments": ("payment_id", "payment_key"),
    "sessions": ("session_id", "session_key"),
    "attendance": ("attendance_id", "attendance_key"),
    "occupancy": ("occupancy_id", "occupancy_key"),
    "stemstar_students": ("student_id", "student_token"),
    "stemstar_employees": ("employee_id", "employee_token"),
}


def surrogate_id(*parts: object) -> int:
    """Positive 63-bit integer, deterministic from the parts."""
    material = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
    return value or 1


def add_surrogate_keys(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add the `*_id` column if missing. Never overwrite a source id (e.g. STEMStar `enrolment_id`)."""
    spec = SURROGATE_SPECS.get(table_name)
    if spec is None:
        return [dict(row) for row in rows]
    id_column, natural_column = spec
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get(id_column) is None:
            natural = item.get(natural_column)
            if natural is not None:
                item[id_column] = surrogate_id(natural_column, natural)
        enriched.append(item)
    return enriched


def attach_student_id(rows: list[dict[str, Any]], token_column: str = "student_token") -> list[dict[str, Any]]:
    """Add `student_id` derived from the token alone (same identity across systems)."""
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        token = item.get(token_column)
        if token is not None:
            item["student_id"] = surrogate_id("student_token", token)
        enriched.append(item)
    return enriched
