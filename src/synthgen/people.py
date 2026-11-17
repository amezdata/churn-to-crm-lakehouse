"""Students, guardians, leads and optional token overlap with STEMStar."""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from synthgen.catalog import employees, programs
from synthgen.constants import (
    CAMPUS_CODE,
    GENDERS,
    GRADE_MAX,
    GRADE_MIN,
    LAUNCH_YEAR_START,
    LEAD_CHANNEL_WEIGHTS,
    LEAD_CHANNELS,
    LEAD_MULTIPLIER,
    LEAD_STATUS_CONVERTED,
    LEAD_STATUSES_OPEN,
    LOST_REASONS,
    ORIGIN_NEW,
    ORIGIN_OVERLAP,
    OVERLAP_RATIO,
    RELATIONSHIP_WEIGHTS,
    RELATIONSHIPS,
    SCHOOL_TYPE_WEIGHTS,
    SCHOOL_TYPES,
    SOURCE_SYSTEM,
)
from synthgen.tokens import make_token, read_seed_tokens


def load_overlap_tokens(tokens_file: Path | None) -> list[str]:
    """Read STEMStar hex tokens if the file exists; otherwise return an empty list."""
    if tokens_file is None or not tokens_file.is_file():
        return []
    return read_seed_tokens(tokens_file.read_text(encoding="utf-8").splitlines())


def build_people(
    rng: random.Random,
    n_students: int,
    overlap_tokens: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Generate synthetic students, guardians, coaches and leads."""
    assert n_students >= 1, "n_students must be at least 1"
    overlap_count = min(len(overlap_tokens or []), int(round(n_students * OVERLAP_RATIO)))
    students: list[dict[str, Any]] = []
    guardians: list[dict[str, Any]] = []

    for index in range(n_students):
        if index < overlap_count:
            student_token = overlap_tokens[index]
            origin = ORIGIN_OVERLAP
        else:
            student_token = make_token("student", SOURCE_SYSTEM, index)
            origin = ORIGIN_NEW
        guardian_token = make_token("guardian", student_token)
        first_date = LAUNCH_YEAR_START + timedelta(days=rng.randint(0, 40))
        students.append(
            {
                "student_natural_key": student_token,
                "guardian_natural_key": guardian_token,
                "campus": CAMPUS_CODE,
                "grade": rng.randint(GRADE_MIN, GRADE_MAX),
                "gender": rng.choice(GENDERS),
                "school_type": rng.choices(SCHOOL_TYPES, weights=SCHOOL_TYPE_WEIGHTS, k=1)[0],
                "identity_origin": origin,
                "first_enrolment_date": first_date.isoformat(),
                "source_system": SOURCE_SYSTEM,
            }
        )
        guardians.append(
            {
                "guardian_natural_key": guardian_token,
                "student_natural_key": student_token,
                "relationship": rng.choices(
                    RELATIONSHIPS, weights=RELATIONSHIP_WEIGHTS, k=1
                )[0],
                "contact_token": make_token("contact", guardian_token),
                "source_system": SOURCE_SYSTEM,
            }
        )

    program_keys = [row["program_natural_key"] for row in programs()]
    converted_students = list(students)
    rng.shuffle(converted_students)
    leads = _build_leads(rng, converted_students, program_keys)
    return {
        "employees": employees(),
        "students": students,
        "guardians": guardians,
        "leads": leads,
    }


def _build_leads(
    rng: random.Random,
    students: list[dict[str, Any]],
    program_keys: list[str],
) -> list[dict[str, Any]]:
    lead_count = max(len(students), int(round(len(students) * LEAD_MULTIPLIER)))
    lost_count = lead_count - len(students)
    leads: list[dict[str, Any]] = []

    for index, student in enumerate(students):
        created = date.fromisoformat(student["first_enrolment_date"]) - timedelta(
            days=rng.randint(3, 21)
        )
        leads.append(
            {
                "lead_natural_key": make_token("lead", "converted", student["student_natural_key"]),
                "campus": CAMPUS_CODE,
                "channel": rng.choices(LEAD_CHANNELS, weights=LEAD_CHANNEL_WEIGHTS, k=1)[0],
                "interest_program_natural_key": rng.choice(program_keys),
                "lead_created_date": created.isoformat(),
                "lead_status": LEAD_STATUS_CONVERTED,
                "converted_student_natural_key": student["student_natural_key"],
                "conversion_date": student["first_enrolment_date"],
                "lost_reason": "",
                "source_system": SOURCE_SYSTEM,
            }
        )

    for index in range(lost_count):
        created = LAUNCH_YEAR_START + timedelta(days=rng.randint(0, 200))
        status = rng.choice(LEAD_STATUSES_OPEN)
        leads.append(
            {
                "lead_natural_key": make_token("lead", "open", index),
                "campus": CAMPUS_CODE,
                "channel": rng.choices(LEAD_CHANNELS, weights=LEAD_CHANNEL_WEIGHTS, k=1)[0],
                "interest_program_natural_key": rng.choice(program_keys),
                "lead_created_date": created.isoformat(),
                "lead_status": status,
                "converted_student_natural_key": "",
                "conversion_date": "",
                "lost_reason": rng.choice(LOST_REASONS) if status == "lost" else "",
                "source_system": SOURCE_SYSTEM,
            }
        )
    return leads
