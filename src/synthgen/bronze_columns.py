"""File names and column names of the Bronze output, aligned with the STEMStar sources.

The generator builds every table with internal keys (``student_natural_key``,
``session_date``, ``status``, ...). This layer maps those keys to the Bronze column
names and drops the internal clocks.
"""

from __future__ import annotations

from typing import Any

CSV_FILES: dict[str, str] = {
    "programs": "brainlab_programs.csv",
    "projects": "brainlab_projects.csv",
    "rooms": "brainlab_rooms.csv",
    "employees": "brainlab_employees.csv",
    "students": "brainlab_students.csv",
    "guardians": "brainlab_guardians.csv",
    "leads": "brainlab_leads.csv",
    "offerings": "brainlab_offerings.csv",
    "enrolments": "brainlab_enrolments.csv",
    "payments": "brainlab_payments.csv",
    "sessions": "brainlab_sessions.csv",
    "attendance": "brainlab_attendance.csv",
    "occupancy": "brainlab_occupancy.csv",
}

LOGS_FILE = "brainlab_platform_logs.jsonl"

BRONZE_COLUMNS: dict[str, dict[str, str]] = {
    "programs": {
        "program_natural_key": "program_key",
        "program_name": "program_name",
        "program_family": "program_family",
        "domain": "domain",
        "target_grade_min": "grade_min",
        "target_grade_max": "grade_max",
        "has_phase_model": "has_phase_model",
        "default_session_count": "default_session_count",
        "unit_sold": "unit_sold",
        "is_active": "is_active",
    },
    "projects": {
        "project_id": "project_id",
        "project_name": "project_name",
        "program_natural_key": "program_key",
        "duration_hours": "duration_hours",
        "step_count": "step_count",
        "sessions_needed": "sessions_needed",
        "topics": "topics",
    },
    "rooms": {
        "room_natural_key": "room_key",
        "campus": "campus",
        "room_name": "room_name",
        "room_type": "room_type",
        "capacity": "capacity",
        "equipment": "equipment",
        "is_bookable": "is_bookable",
    },
    "employees": {
        "employee_natural_key": "employee_token",
        "campus": "campus",
        "role": "role",
        "is_educator": "is_educator",
        "specialty": "specialty",
        "hire_date": "start_date",
        "employment_status": "employment_status",
        "source_system": "source_system",
    },
    "students": {
        "student_natural_key": "student_token",
        "guardian_natural_key": "guardian_token",
        "campus": "campus",
        "grade": "grade",
        "gender": "gender",
        "school_type": "school_type",
        "identity_origin": "identity_origin",
        "first_enrolment_date": "first_enrolment_date",
        "source_system": "source_system",
    },
    "guardians": {
        "guardian_natural_key": "guardian_token",
        "student_natural_key": "student_token",
        "relationship": "relationship",
        "contact_token": "contact_token",
        "source_system": "source_system",
    },
    "leads": {
        "lead_natural_key": "lead_key",
        "campus": "campus",
        "channel": "channel",
        "interest_program_natural_key": "interest_program_key",
        "lead_created_date": "created_date",
        "lead_status": "lead_status",
        "converted_student_natural_key": "converted_student_token",
        "conversion_date": "conversion_date",
        "lost_reason": "lost_reason",
        "source_system": "source_system",
    },
    "offerings": {
        "offering_natural_key": "offering_key",
        "program_natural_key": "program_key",
        "project_id": "project_id",
        "campus": "campus",
        "term": "term",
        "term_start_date": "start_date",
        "term_end_date": "end_date",
        "schedule": "schedule",
        "list_price": "list_price",
        "currency": "currency",
        "capacity": "seats",
        "lead_educator_natural_key": "educator_token",
        "default_room_natural_key": "room_key",
        "offering_status": "offering_status",
        "source_system": "source_system",
        "round_index": "round_number",
        "launch_month": "launch_month",
    },
    "enrolments": {
        "enrolment_natural_key": "enrolment_key",
        "student_natural_key": "student_token",
        "guardian_natural_key": "guardian_token",
        "offering_natural_key": "offering_key",
        "program_natural_key": "program_key",
        "project_id": "project_id",
        "campus": "campus",
        "enrolment_date": "enrolment_date",
        "term": "term",
        "price_paid": "price_paid",
        "discount": "discount",
        "currency": "currency",
        "enrolment_status": "enrolment_status",
        "is_renewal": "is_renewal",
        "previous_enrolment_natural_key": "previous_enrolment_key",
        "start_date": "start_date",
        "end_date": "end_date",
        "source_system": "source_system",
    },
    "payments": {
        "payment_natural_key": "payment_key",
        "enrolment_natural_key": "enrolment_key",
        "guardian_natural_key": "guardian_token",
        "amount": "amount",
        "currency": "currency",
        "payment_date": "payment_date",
        "payment_method": "payment_method",
        "payment_status": "payment_status",
        "invoice_token": "invoice_token",
        "installment_no": "installment_number",
        "source_system": "source_system",
    },
    "sessions": {
        "session_natural_key": "session_key",
        "offering_natural_key": "offering_key",
        "program_natural_key": "program_key",
        "project_id": "project_id",
        "campus": "campus",
        "session_date": "class_date",
        "time_slot": "time_slot",
        "room_natural_key": "room_key",
        "educator_natural_key": "educator_token",
        "session_status": "session_status",
        "topic": "topic",
        "phase": "phase",
        "source_system": "source_system",
    },
    "attendance": {
        "attendance_natural_key": "attendance_key",
        "session_natural_key": "session_key",
        "student_natural_key": "student_token",
        "enrolment_natural_key": "enrolment_key",
        "status": "attendance_status",
        "time_slot": "time_slot",
        "check_in_time": "check_in_time",
        "recorded_by_natural_key": "recorded_by",
        "source_system": "source_system",
    },
    "occupancy": {
        "occupancy_natural_key": "occupancy_key",
        "room_natural_key": "room_key",
        "campus": "campus",
        "occupancy_date": "date",
        "time_slot": "time_slot",
        "occupancy_source": "occupancy_source",
        "session_natural_key": "session_key",
        "headcount": "headcount",
        "capacity": "capacity",
        "source_system": "source_system",
    },
    "platform_logs": {
        "event_id": "event_id",
        "event_ts": "event_ts",
        "event_type": "event_type",
        "platform_session_id": "platform_session_id",
        "student_natural_key": "student_token",
        "project_id": "project_id",
        "step_index": "step_index",
        "class_session_natural_key": "session_key",
        "source_system": "source_system",
        "client_build": "client_build",
    },
}

# Internal clocks are not exported (the time slot is exported as "thursday slot_1").
OMITTED_COLUMNS = {"start_time", "end_time"}


def to_bronze_rows(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping = BRONZE_COLUMNS[table_name]
    projected: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            if key in OMITTED_COLUMNS:
                continue
            item[mapping.get(key, key)] = value
        projected.append(item)
    return projected
