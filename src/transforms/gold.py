"""Gold star schema from Silver. No tokens; does not materialize churn features."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from transforms.kpi import parse_program
from transforms.keys import surrogate_id
from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS

SOURCE_STEMSTAR = "stemstar_rdbms"
SOURCE_BRAINLAB = "brainlab_csv"

SILVER_LAKEHOUSE_TABLES = {
    "stemstar_students": "silver.stemstar_students",
    "stemstar_enrolments": "silver.stemstar_enrolments",
    "stemstar_attendance": "silver.stemstar_attendance",
    "stemstar_employees": "silver.stemstar_employees",
    "brainlab_students": "silver.brainlab_students",
    "brainlab_programs": "silver.brainlab_programs",
    "brainlab_employees": "silver.brainlab_employees",
    "brainlab_rooms": "silver.brainlab_rooms",
    "brainlab_enrolments": "silver.brainlab_enrolments",
    "brainlab_payments": "silver.brainlab_payments",
    "brainlab_attendance": "silver.brainlab_attendance",
    "brainlab_occupancy": "silver.brainlab_occupancy",
    "brainlab_leads": "silver.brainlab_leads",
    "kpi_reconciliation": "silver.kpi_reconciliation",
}

GOLD_TABLES = (
    "dim_date",
    "dim_campus",
    "dim_student",
    "dim_program",
    "dim_employee",
    "dim_room",
    "fact_enrolment",
    "fact_attendance",
    "fact_payment",
    "fact_occupancy",
    "fact_lead",
    "fact_renewal_kpi",
)

MONTH_NAMES = (
    "",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

PRESENT_STATES = {"present"}
ABSENT_STATES = {"absent"}
LATE_STATES = {"late"}
EXCUSED_STATES = {"excused"}
CANCELLED_STATES = {"cancelled", "class_cancelled"}


def build_gold_star(silver: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Build dimensions + facts. `silver` uses the keys of SILVER_LAKEHOUSE_TABLES."""
    campus_ids = _campus_ids(silver)
    dim_campus = _dim_campus(campus_ids)
    dim_program = _ensure_kpi_programs(_dim_program(silver), silver.get("kpi_reconciliation", []))
    dim_student = _dim_student(silver, campus_ids)
    dim_employee = _dim_employee(silver, campus_ids)
    dim_room = _dim_room(silver, campus_ids)

    enrolment_id_by_key = {
        row["enrolment_key"]: row.get("enrolment_id")
        for row in silver.get("brainlab_enrolments", [])
        if row.get("enrolment_key") is not None
    }
    program_id_by_key = {row["program_key"]: row["program_id"] for row in dim_program}

    fact_enrolment = _fact_enrolment(silver, campus_ids, program_id_by_key)
    fact_attendance = _fact_attendance(silver, campus_ids, enrolment_id_by_key)
    fact_payment = _fact_payment(silver, enrolment_id_by_key)
    fact_occupancy = _fact_occupancy(silver, campus_ids)
    fact_lead = _fact_lead(silver, campus_ids, program_id_by_key)
    fact_kpi = _fact_renewal_kpi(silver.get("kpi_reconciliation", []), program_id_by_key)

    facts = (
        fact_enrolment,
        fact_attendance,
        fact_payment,
        fact_occupancy,
        fact_lead,
    )
    dim_date = _dim_date(_collect_dates(facts))

    gold = {
        "dim_date": dim_date,
        "dim_campus": dim_campus,
        "dim_student": dim_student,
        "dim_program": dim_program,
        "dim_employee": dim_employee,
        "dim_room": dim_room,
        "fact_enrolment": fact_enrolment,
        "fact_attendance": fact_attendance,
        "fact_payment": fact_payment,
        "fact_occupancy": fact_occupancy,
        "fact_lead": fact_lead,
        "fact_renewal_kpi": fact_kpi,
    }
    return {name: [_strip_gold_row(row) for row in rows] for name, rows in gold.items()}


def _campus_ids(silver: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    names: set[str] = set()
    for table_name, rows in silver.items():
        if table_name == "kpi_reconciliation":
            continue
        for row in rows:
            campus = row.get("campus")
            if campus:
                names.add(str(campus))
    return {name: surrogate_id("campus", name) for name in sorted(names)}


def _dim_campus(campus_ids: dict[str, int]) -> list[dict[str, Any]]:
    return [{"campus_id": campus_id, "campus": name} for name, campus_id in sorted(campus_ids.items())]


def _dim_program(silver: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for row in silver.get("stemstar_enrolments", []):
        key = row.get("program")
        if not key:
            continue
        program_id = surrogate_id("program_key", key)
        by_id.setdefault(
            program_id,
            {
                "program_id": program_id,
                "program_key": key,
                "program_name": key,
                "program_family": key,
                "source_system": SOURCE_STEMSTAR,
            },
        )
    for row in silver.get("brainlab_programs", []):
        key = row.get("program_key")
        if not key:
            continue
        program_id = row.get("program_id") or surrogate_id("program_key", key)
        existing = by_id.get(program_id, {})
        by_id[program_id] = {
            "program_id": program_id,
            "program_key": key,
            "program_name": row.get("program_name") or existing.get("program_name") or key,
            "program_family": row.get("program_family") or existing.get("program_family") or key,
            "source_system": existing.get("source_system") or SOURCE_BRAINLAB,
        }
        if existing.get("source_system") and existing["source_system"] != SOURCE_BRAINLAB:
            by_id[program_id]["source_system"] = existing["source_system"]
    return list(by_id.values())


def _ensure_kpi_programs(
    dim_program: list[dict[str, Any]], kpi_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_key = {row["program_key"]: row for row in dim_program}
    for row in kpi_rows:
        course = row.get("course")
        if not course:
            continue
        family = parse_program(str(course))
        if family in by_key:
            continue
        program_id = surrogate_id("program_key", family)
        item = {
            "program_id": program_id,
            "program_key": family,
            "program_name": family,
            "program_family": family,
            "source_system": SOURCE_STEMSTAR,
        }
        dim_program.append(item)
        by_key[family] = item
    return dim_program


def _dim_student(
    silver: dict[str, list[dict[str, Any]]], campus_ids: dict[str, int]
) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for row in silver.get("stemstar_students", []):
        student_id = row.get("student_id")
        if student_id is None:
            continue
        by_id[student_id] = {
            "student_id": student_id,
            "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
            "source_system": row.get("source_system") or SOURCE_STEMSTAR,
            "grade": None,
            "gender": None,
            "school_type": None,
            "first_enrolment_date": None,
        }
    for row in silver.get("brainlab_students", []):
        student_id = row.get("student_id")
        if student_id is None:
            continue
        existing = by_id.get(student_id, {})
        by_id[student_id] = {
            "student_id": student_id,
            "campus_id": existing.get("campus_id")
            or (campus_ids.get(str(row.get("campus"))) if row.get("campus") else None),
            "source_system": existing.get("source_system") or row.get("source_system") or SOURCE_BRAINLAB,
            "grade": existing.get("grade") or _as_int(row.get("grade")),
            "gender": existing.get("gender") or row.get("gender"),
            "school_type": existing.get("school_type") or row.get("school_type"),
            "first_enrolment_date": existing.get("first_enrolment_date")
            or _as_date(row.get("first_enrolment_date")),
        }
    return list(by_id.values())


def _dim_employee(
    silver: dict[str, list[dict[str, Any]]], campus_ids: dict[str, int]
) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for row in silver.get("stemstar_employees", []):
        employee_id = row.get("employee_id")
        if employee_id is None:
            continue
        role = row.get("role")
        by_id[employee_id] = {
            "employee_id": employee_id,
            "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
            "role": role,
            "specialty": row.get("specialty"),
            "is_educator": role == "educator" if role is not None else None,
            "is_active": row.get("is_active"),
            "start_date": _as_date(row.get("start_date")),
            "source_system": row.get("source_system") or SOURCE_STEMSTAR,
        }
    for row in silver.get("brainlab_employees", []):
        employee_id = row.get("employee_id")
        if employee_id is None:
            continue
        existing = by_id.get(employee_id, {})
        status = row.get("employment_status")
        by_id[employee_id] = {
            "employee_id": employee_id,
            "campus_id": existing.get("campus_id")
            or (campus_ids.get(str(row.get("campus"))) if row.get("campus") else None),
            "role": existing.get("role") or row.get("role"),
            "specialty": existing.get("specialty") or row.get("specialty"),
            "is_educator": existing.get("is_educator")
            if existing.get("is_educator") is not None
            else row.get("is_educator"),
            "is_active": existing.get("is_active") if existing.get("is_active") is not None else (status == "active"),
            "start_date": existing.get("start_date") or _as_date(row.get("start_date")),
            "source_system": existing.get("source_system") or row.get("source_system") or SOURCE_BRAINLAB,
        }
    return list(by_id.values())


def _dim_room(
    silver: dict[str, list[dict[str, Any]]], campus_ids: dict[str, int]
) -> list[dict[str, Any]]:
    rooms: list[dict[str, Any]] = []
    for row in silver.get("brainlab_rooms", []):
        key = row.get("room_key")
        room_id = row.get("room_id") or (surrogate_id("room_key", key) if key else None)
        if room_id is None:
            continue
        rooms.append(
            {
                "room_id": room_id,
                "room_key": key,
                "room_name": row.get("room_name"),
                "room_type": row.get("room_type"),
                "capacity": _as_int(row.get("capacity")),
                "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
            }
        )
    return rooms


def _fact_enrolment(
    silver: dict[str, list[dict[str, Any]]],
    campus_ids: dict[str, int],
    program_id_by_key: dict[str, int],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for row in silver.get("stemstar_enrolments", []):
        enrollment_id = row.get("enrolment_id")
        if enrollment_id is None:
            continue
        key = row.get("program")
        event_date = _as_date(row.get("created_at") or row.get("enrolment_date"))
        facts.append(
            {
                "enrolment_id": enrollment_id,
                "student_id": row.get("student_id"),
                "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
                "program_id": program_id_by_key.get(str(key)) if key else None,
                "date_id": _date_id(event_date),
                "source_system": row.get("source_system") or SOURCE_STEMSTAR,
                "academic_period": row.get("academic_year"),
                "period_type": "year",
                "course": row.get("course"),
                "amount": None,
                "n_enrolments": 1,
                "enrolment_status": None,
                "is_renewal": None,
            }
        )
    for row in silver.get("brainlab_enrolments", []):
        enrollment_id = row.get("enrolment_id")
        if enrollment_id is None:
            continue
        key = row.get("program_key")
        event_date = _as_date(row.get("enrolment_date"))
        facts.append(
            {
                "enrolment_id": enrollment_id,
                "student_id": row.get("student_id"),
                "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
                "program_id": program_id_by_key.get(str(key)) if key else None,
                "date_id": _date_id(event_date),
                "source_system": row.get("source_system") or SOURCE_BRAINLAB,
                "academic_period": row.get("term"),
                "period_type": "term",
                "course": None,
                "amount": _as_decimal_float(row.get("price_paid")),
                "n_enrolments": 1,
                "enrolment_status": row.get("enrolment_status"),
                "is_renewal": row.get("is_renewal"),
            }
        )
    return facts


def _fact_attendance(
    silver: dict[str, list[dict[str, Any]]],
    campus_ids: dict[str, int],
    enrolment_id_by_key: dict[str, int],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for row in silver.get("stemstar_attendance", []):
        attendance_id = row.get("attendance_id")
        if attendance_id is None:
            continue
        event_date = _as_date(row.get("class_date"))
        status = row.get("attendance_status")
        facts.append(
            {
                "attendance_id": attendance_id,
                "student_id": row.get("student_id"),
                "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
                "date_id": _date_id(event_date),
                "enrolment_id": None,
                "session_id": None,
                "source_system": row.get("source_system") or SOURCE_STEMSTAR,
                "attendance_status": status,
                **_attendance_flags(status),
            }
        )
    for row in silver.get("brainlab_attendance", []):
        attendance_id = row.get("attendance_id")
        if attendance_id is None:
            continue
        event_date = _as_date(row.get("check_in_time") or row.get("class_date"))
        session_key = row.get("session_key")
        enrolment_key = row.get("enrolment_key")
        status = row.get("attendance_status")
        facts.append(
            {
                "attendance_id": attendance_id,
                "student_id": row.get("student_id"),
                "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
                "date_id": _date_id(event_date),
                "enrolment_id": enrolment_id_by_key.get(enrolment_key) if enrolment_key else None,
                "session_id": surrogate_id("session_key", session_key) if session_key else None,
                "source_system": row.get("source_system") or SOURCE_BRAINLAB,
                "attendance_status": status,
                **_attendance_flags(status),
            }
        )
    return facts


def _fact_payment(
    silver: dict[str, list[dict[str, Any]]], enrolment_id_by_key: dict[str, int]
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for row in silver.get("brainlab_payments", []):
        payment_id = row.get("payment_id")
        if payment_id is None:
            continue
        enrolment_key = row.get("enrolment_key")
        event_date = _as_date(row.get("payment_date"))
        facts.append(
            {
                "payment_id": payment_id,
                "enrolment_id": enrolment_id_by_key.get(enrolment_key) if enrolment_key else None,
                "date_id": _date_id(event_date),
                "amount": _as_decimal_float(row.get("amount")),
                "payment_status": row.get("payment_status"),
                "source_system": row.get("source_system") or SOURCE_BRAINLAB,
            }
        )
    return facts


def _fact_occupancy(
    silver: dict[str, list[dict[str, Any]]], campus_ids: dict[str, int]
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for row in silver.get("brainlab_occupancy", []):
        occupancy_id = row.get("occupancy_id")
        if occupancy_id is None:
            continue
        room_key = row.get("room_key")
        occupied = _as_int(row.get("headcount"))
        capacity = _as_int(row.get("capacity"))
        pct = None
        if occupied is not None and capacity:
            pct = round(100.0 * occupied / capacity, 2)
        event_date = _as_date(row.get("date"))
        facts.append(
            {
                "occupancy_id": occupancy_id,
                "room_id": surrogate_id("room_key", room_key) if room_key else None,
                "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
                "date_id": _date_id(event_date),
                "headcount": occupied,
                "capacity": capacity,
                "occupancy_pct": pct,
                "session_key": row.get("session_key"),
                "time_slot": row.get("time_slot"),
                "source_system": row.get("source_system") or SOURCE_BRAINLAB,
            }
        )
    return facts


def _fact_lead(
    silver: dict[str, list[dict[str, Any]]],
    campus_ids: dict[str, int],
    program_id_by_key: dict[str, int],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for row in silver.get("brainlab_leads", []):
        lead_id = row.get("lead_id")
        if lead_id is None:
            continue
        program_key = row.get("interest_program_key")
        event_date = _as_date(row.get("created_date"))
        facts.append(
            {
                "lead_id": lead_id,
                "campus_id": campus_ids.get(str(row.get("campus"))) if row.get("campus") else None,
                "program_id": program_id_by_key.get(str(program_key)) if program_key else None,
                "student_id": row.get("student_id"),
                "date_id": _date_id(event_date),
                "channel": row.get("channel"),
                "lead_status": row.get("lead_status"),
                "source_system": row.get("source_system") or SOURCE_BRAINLAB,
            }
        )
    return facts


def _fact_renewal_kpi(
    rows: list[dict[str, Any]], program_id_by_key: dict[str, int]
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for row in rows:
        year = row.get("academic_year")
        course = row.get("course")
        if year is None or course is None:
            continue
        family = parse_program(str(course))
        program_id = program_id_by_key.get(family) or surrogate_id("program_key", family)
        facts.append(
            {
                "academic_year": year,
                "course": course,
                "program_id": program_id,
                "enrolled_students": _kpi_metric(row, "enrolled_students"),
                "renewals": _kpi_metric(row, "renewals"),
                "renewal_rate_pct": _kpi_metric(row, "renewal_rate_pct"),
                "total_absences": _kpi_metric(row, "total_absences"),
                "refunds": _kpi_metric(row, "refunds"),
            }
        )
    return facts


def _kpi_metric(row: dict[str, Any], name: str) -> Any:
    lakehouse_key = f"{name}_lakehouse"
    if lakehouse_key in row and row[lakehouse_key] is not None:
        return row[lakehouse_key]
    return row.get(name)


def _attendance_flags(status: Any) -> dict[str, bool]:
    text = str(status).strip() if status is not None else ""
    return {
        "is_present": text in PRESENT_STATES,
        "is_absent": text in ABSENT_STATES,
        "is_late": text in LATE_STATES,
        "is_excused": text in EXCUSED_STATES,
        "is_cancelled": text in CANCELLED_STATES,
    }


def _collect_dates(facts: tuple[list[dict[str, Any]], ...]) -> list[date]:
    found: list[date] = []
    for table in facts:
        for row in table:
            date_id = row.get("date_id")
            parsed = _date_from_date_id(date_id)
            if parsed is not None:
                found.append(parsed)
    return found


def _dim_date(dates: list[date]) -> list[dict[str, Any]]:
    if not dates:
        return []
    start = min(dates)
    stop = max(dates)
    rows: list[dict[str, Any]] = []
    cursor = start
    while cursor <= stop:
        rows.append(
            {
                "date_id": _date_id(cursor),
                "date": cursor,
                "year": cursor.year,
                "month": cursor.month,
                "day": cursor.day,
                "month_name": MONTH_NAMES[cursor.month],
                "iso_weekday": cursor.isoweekday(),
            }
        )
        cursor += timedelta(days=1)
    return rows


def _strip_gold_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key in FORBIDDEN_COLUMNS or key in TOKEN_COLUMNS:
            continue
        if key.endswith("_token"):
            continue
        cleaned[key] = value
    return cleaned


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "T" in text:
        return datetime.fromisoformat(text).date()
    return date.fromisoformat(text[:10])


def _date_id(value: date | None) -> int | None:
    if value is None:
        return None
    return value.year * 10000 + value.month * 100 + value.day


def _date_from_date_id(value: Any) -> date | None:
    if value is None:
        return None
    number = int(value)
    year, month_day = divmod(number, 10000)
    month, day = divmod(month_day, 100)
    return date(year, month, day)


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    return int(value)


def _as_decimal_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)
