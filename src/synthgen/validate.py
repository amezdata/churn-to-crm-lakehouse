"""Integrity checks used by the tests and by the CLI before writing."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from synthgen.constants import (
    GRADE_MAX,
    GRADE_MIN,
    L2_ROUND_CAPACITY,
    OPEN_WEEKDAYS,
    SKILLS_COURSE_CAPACITY,
    TOKEN_HEX_LENGTH,
)
from synthgen.tokens import TOKEN_PATTERN

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?:\+\d{6,}|\d{3}[-.\s]\d{3}[-.\s]\d{3,})")
NAME_COLUMNS = {
    "full_name",
    "contact_name",
    "contact_email",
    "contact_phone",
    "phone",
    "email",
    "school_name",
    "home_district",
    "birth_date",
}


def collect_integrity_errors(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Return referential integrity and capacity failures."""
    errors: list[str] = []
    required = (
        "students",
        "guardians",
        "leads",
        "employees",
        "rooms",
        "programs",
        "projects",
        "offerings",
        "enrolments",
        "payments",
        "sessions",
        "attendance",
        "occupancy",
        "platform_logs",
    )
    for name in required:
        if name not in tables or not tables[name]:
            errors.append(f"table missing or empty: {name}")
    if errors:
        return errors

    student_keys = {row["student_natural_key"] for row in tables["students"]}
    guardian_keys = {row["guardian_natural_key"] for row in tables["guardians"]}
    offering_keys = {row["offering_natural_key"] for row in tables["offerings"]}
    enrolment_keys = {row["enrolment_natural_key"] for row in tables["enrolments"]}
    session_keys = {row["session_natural_key"] for row in tables["sessions"]}
    room_keys = {row["room_natural_key"] for row in tables["rooms"]}
    employee_keys = {row["employee_natural_key"] for row in tables["employees"]}
    program_keys = {row["program_natural_key"] for row in tables["programs"]}
    project_ids = {row["project_id"] for row in tables["projects"]}

    for row in tables["students"]:
        if not TOKEN_PATTERN.fullmatch(row["student_natural_key"]):
            errors.append(f"the student token is not {TOKEN_HEX_LENGTH} hex characters")
        if not GRADE_MIN <= int(row["grade"]) <= GRADE_MAX:
            errors.append(f"grade out of range: {row['grade']}")
        if row["guardian_natural_key"] not in guardian_keys:
            errors.append("guardian FK missing in the student")

    for row in tables["enrolments"]:
        if row["student_natural_key"] not in student_keys:
            errors.append("student FK missing in the enrolment")
        if row["offering_natural_key"] not in offering_keys:
            errors.append("offering FK missing in the enrolment")
        previous = row["previous_enrolment_natural_key"]
        if previous and previous not in enrolment_keys:
            errors.append("previous enrolment FK missing")
    enrolment_by_key = {row["enrolment_natural_key"]: row for row in tables["enrolments"]}
    for row in tables["enrolments"]:
        previous = row["previous_enrolment_natural_key"]
        if not previous:
            continue
        prior = enrolment_by_key[previous]
        if prior["start_date"] > row["start_date"]:
            errors.append("the renewal chain is not chronological")

    for row in tables["payments"]:
        if row["enrolment_natural_key"] not in enrolment_keys:
            errors.append("enrolment FK missing in the payment")
        if row["guardian_natural_key"] not in guardian_keys:
            errors.append("guardian FK missing in the payment")

    for row in tables["sessions"]:
        if row["offering_natural_key"] not in offering_keys:
            errors.append("offering FK missing in the session")
        if row["room_natural_key"] not in room_keys:
            errors.append("room FK missing in the session")
        if row["educator_natural_key"] not in employee_keys:
            errors.append("educator FK missing in the session")
        session_date = row["session_date"]
        weekday = date.fromisoformat(session_date).weekday()
        if weekday not in OPEN_WEEKDAYS:
            errors.append(f"session on a closed day: {session_date}")

    for row in tables["attendance"]:
        if row["session_natural_key"] not in session_keys:
            errors.append("session FK missing in the attendance row")
        if row["student_natural_key"] not in student_keys:
            errors.append("student FK missing in the attendance row")
        if row["enrolment_natural_key"] not in enrolment_keys:
            errors.append("enrolment FK missing in the attendance row")

    for row in tables["occupancy"]:
        if row["room_natural_key"] not in room_keys:
            errors.append("room FK missing in the occupancy row")
        if row["session_natural_key"] and row["session_natural_key"] not in session_keys:
            errors.append("session FK missing in the occupancy row")

    for row in tables["offerings"]:
        if row["program_natural_key"] not in program_keys:
            errors.append("program FK missing in the offering")
        if row["project_id"] not in project_ids:
            errors.append("project FK missing in the offering")
        if row["program_natural_key"] == "prg_level_2" and int(row["capacity"]) > L2_ROUND_CAPACITY:
            errors.append("the L2 offering exceeds the round capacity")
        if row["program_natural_key"] == "prg_skills" and int(row["capacity"]) > SKILLS_COURSE_CAPACITY:
            errors.append("the Skills offering exceeds the course capacity")

    enrol_counts: dict[str, int] = {}
    for row in tables["enrolments"]:
        enrol_counts[row["offering_natural_key"]] = enrol_counts.get(row["offering_natural_key"], 0) + 1
    offering_capacity = {row["offering_natural_key"]: int(row["capacity"]) for row in tables["offerings"]}
    for offering_key, count in enrol_counts.items():
        if count > offering_capacity[offering_key]:
            errors.append(f"enrolments exceed the capacity of {offering_key}")

    return errors


def collect_pii_errors(tables: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Return clear-text PII leaks (names, email, phone)."""
    errors: list[str] = []
    for table_name, rows in tables.items():
        for row in rows:
            leaked = NAME_COLUMNS.intersection(row)
            if leaked:
                errors.append(f"{table_name} exposes columns {sorted(leaked)}")
            for value in row.values():
                if not isinstance(value, str) or not value:
                    continue
                if EMAIL_PATTERN.search(value):
                    errors.append(f"{table_name} contains an email address")
                if PHONE_PATTERN.search(value):
                    errors.append(f"{table_name} contains a value that looks like a phone number")
    return errors


def assert_dataset(tables: dict[str, list[dict[str, Any]]]) -> None:
    errors = collect_integrity_errors(tables) + collect_pii_errors(tables)
    assert not errors, "; ".join(errors[:12])
