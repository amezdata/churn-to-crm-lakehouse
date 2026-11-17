"""Churn feature table from Gold. No tokens; does not modify the star schema."""

from __future__ import annotations

from datetime import date
from typing import Any

from transforms.kpi import REFUND_ABSENCE_THRESHOLD, next_academic_year, parse_program
from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS

SOURCE_STEMSTAR = "stemstar_rdbms"
SOURCE_BRAINLAB = "brainlab_csv"

FEATURES_CHURN_TABLE = "features_churn"

GOLD_FACT_TABLES = (
    "fact_enrolment",
    "fact_attendance",
    "fact_payment",
)

NEXT_TERM = {
    "2026-Autumn": "2027-Spring",
}

TERM_WINDOWS: dict[str, tuple[date, date]] = {
    "2026-Autumn": (date(2026, 8, 1), date(2026, 12, 31)),
    "2027-Spring": (date(2027, 1, 1), date(2027, 7, 31)),
}


def build_features_churn(gold: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """One row per `fact_enrolment`. Label is null if period N+1 does not exist in Gold."""
    enrolments = gold.get("fact_enrolment", [])
    attendance = gold.get("fact_attendance", [])
    payments = gold.get("fact_payment", [])

    periods_present = {
        row["academic_period"] for row in enrolments if row.get("academic_period") is not None
    }
    first_date_by_student = _first_enrolment_dates(enrolments)
    periods_by_student = _periods_by_student(enrolments)
    students_by_period = _students_by_period(enrolments)
    students_by_period_program = _students_by_period_program(enrolments)
    attendance_by_enrolment, attendance_by_student = _index_attendance(attendance)
    payments_by_enrolment = _index_payments(payments)
    absences_by_key = _index_absences(gold.get("stemstar_absences", []))

    features: list[dict[str, Any]] = []
    for row in enrolments:
        enrolment_id = row.get("enrolment_id")
        student_id = row.get("student_id")
        if enrolment_id is None or student_id is None:
            continue
        period = row.get("academic_period")
        period_type = row.get("period_type")
        origin = row.get("source_system")
        program_id = row.get("program_id")
        event_date = _date_from_date_id(row.get("date_id"))

        next_period = _next_period(period, period_type)
        has_label = next_period is not None and next_period in periods_present
        renewed = None
        if has_label:
            if period_type == "term":
                renewed = student_id in students_by_period_program.get((next_period, program_id), set())
            else:
                renewed = student_id in students_by_period.get(next_period, set())

        first_date = first_date_by_student.get(student_id)
        tenure_days = None
        if event_date is not None and first_date is not None:
            tenure_days = (event_date - first_date).days

        prior_periods = {
            other_period
            for other_period, other_type in periods_by_student.get(student_id, set())
            if _period_is_before(other_period, other_type, period, period_type)
        }
        prior_count = len(prior_periods)
        is_renewal = row.get("is_renewal")
        if is_renewal is None:
            is_renewal = prior_count > 0

        attendance_rows = attendance_by_enrolment.get(enrolment_id)
        if not attendance_rows:
            window = _period_window(period, period_type)
            attendance_rows = [
                item
                for item in attendance_by_student.get(student_id, [])
                if _date_id_in_window(item.get("date_id"), window)
            ]
        present_count, denominator = _attendance_counts(attendance_rows)
        attendance_rate = None if denominator == 0 else round(present_count / denominator, 4)

        if origin == SOURCE_STEMSTAR:
            amount_paid = None
            payment_count = None
        else:
            pay_rows = payments_by_enrolment.get(enrolment_id, [])
            payment_count = len(pay_rows)
            amount_paid = round(sum(_as_float(item.get("amount")) or 0.0 for item in pay_rows), 2)
            if payment_count == 0:
                amount_paid = None
                payment_count = 0

        absence_total, is_refund = _absence_feature(row, student_id, period, origin, absences_by_key)

        features.append(
            _strip_feature_row(
                {
                    "student_id": student_id,
                    "enrolment_id": enrolment_id,
                    "campus_id": row.get("campus_id"),
                    "program_id": program_id,
                    "source_system": origin,
                    "academic_period": period,
                    "period_type": period_type,
                    "date_id": row.get("date_id"),
                    "tenure_days": tenure_days,
                    "attendance_rate": attendance_rate,
                    "n_present": present_count,
                    "n_attendance_denominator": denominator,
                    "n_prior_renewals": prior_count,
                    "is_renewal": bool(is_renewal),
                    "amount_paid": amount_paid,
                    "n_payments": payment_count,
                    "n_absences": absence_total,
                    "is_refund": is_refund,
                    "renewed_next_period": renewed,
                    "is_churn": None if renewed is None else (not renewed),
                }
            )
        )
    return features


def _first_enrolment_dates(enrolments: list[dict[str, Any]]) -> dict[Any, date]:
    first_dates: dict[Any, date] = {}
    for row in enrolments:
        student_id = row.get("student_id")
        event_date = _date_from_date_id(row.get("date_id"))
        if student_id is None or event_date is None:
            continue
        current = first_dates.get(student_id)
        if current is None or event_date < current:
            first_dates[student_id] = event_date
    return first_dates


def _periods_by_student(enrolments: list[dict[str, Any]]) -> dict[Any, set[tuple[Any, Any]]]:
    by_student: dict[Any, set[tuple[Any, Any]]] = {}
    for row in enrolments:
        student_id = row.get("student_id")
        period = row.get("academic_period")
        if student_id is None or period is None:
            continue
        by_student.setdefault(student_id, set()).add((period, row.get("period_type")))
    return by_student


def _students_by_period(enrolments: list[dict[str, Any]]) -> dict[Any, set[Any]]:
    by_period: dict[Any, set[Any]] = {}
    for row in enrolments:
        period = row.get("academic_period")
        student_id = row.get("student_id")
        if period is None or student_id is None:
            continue
        by_period.setdefault(period, set()).add(student_id)
    return by_period


def _students_by_period_program(enrolments: list[dict[str, Any]]) -> dict[tuple[Any, Any], set[Any]]:
    by_key: dict[tuple[Any, Any], set[Any]] = {}
    for row in enrolments:
        period = row.get("academic_period")
        student_id = row.get("student_id")
        program_id = row.get("program_id")
        if period is None or student_id is None:
            continue
        by_key.setdefault((period, program_id), set()).add(student_id)
    return by_key


def _index_attendance(
    rows: list[dict[str, Any]],
) -> tuple[dict[Any, list[dict[str, Any]]], dict[Any, list[dict[str, Any]]]]:
    by_enrolment: dict[Any, list[dict[str, Any]]] = {}
    by_student: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        enrolment_id = row.get("enrolment_id")
        if enrolment_id is not None:
            by_enrolment.setdefault(enrolment_id, []).append(row)
        student_id = row.get("student_id")
        if student_id is not None:
            by_student.setdefault(student_id, []).append(row)
    return by_enrolment, by_student


def _index_payments(rows: list[dict[str, Any]]) -> dict[Any, list[dict[str, Any]]]:
    by_enrolment: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        enrolment_id = row.get("enrolment_id")
        if enrolment_id is None:
            continue
        by_enrolment.setdefault(enrolment_id, []).append(row)
    return by_enrolment


def _index_absences(rows: list[dict[str, Any]]) -> dict[tuple[Any, str, str], int]:
    totals: dict[tuple[Any, str, str], int] = {}
    for row in rows:
        student_id = row.get("student_id")
        year = row.get("academic_year")
        program = row.get("program")
        if student_id is None or year is None or program is None:
            continue
        family = parse_program(str(program))
        raw_total = row.get("year_total")
        total = int(raw_total) if raw_total is not None and raw_total != "" else 0
        key = (student_id, str(year), family)
        previous = totals.get(key, 0)
        if total > previous:
            totals[key] = total
    return totals


def _absence_feature(
    enrolment: dict[str, Any],
    student_id: Any,
    period: Any,
    origin: Any,
    absences_by_key: dict[tuple[Any, str, str], int],
) -> tuple[int | None, bool | None]:
    if origin != SOURCE_STEMSTAR:
        return None, None
    course = enrolment.get("course")
    if period is None or course is None:
        return 0, False
    family = parse_program(str(course))
    total = absences_by_key.get((student_id, str(period), family), 0)
    return total, total > REFUND_ABSENCE_THRESHOLD


def _attendance_counts(rows: list[dict[str, Any]]) -> tuple[int, int]:
    present_count = 0
    denominator = 0
    for row in rows:
        is_present = bool(row.get("is_present"))
        in_denominator = (
            is_present
            or bool(row.get("is_absent"))
            or bool(row.get("is_late"))
            or bool(row.get("is_excused"))
        )
        if is_present:
            present_count += 1
        if in_denominator:
            denominator += 1
    return present_count, denominator


def _next_period(period: Any, period_type: Any) -> str | None:
    if period is None:
        return None
    label = str(period)
    if period_type == "term" or label in NEXT_TERM:
        return NEXT_TERM.get(label)
    try:
        return next_academic_year(label)
    except (ValueError, IndexError):
        return None


def _period_window(period: Any, period_type: Any) -> tuple[date, date] | None:
    if period is None:
        return None
    label = str(period)
    if period_type == "term" or label in TERM_WINDOWS:
        return TERM_WINDOWS.get(label)
    parts = label.split("-")
    if len(parts) != 2:
        return None
    try:
        start_year = 2000 + int(parts[0])
    except ValueError:
        return None
    return date(start_year, 9, 1), date(start_year + 1, 8, 31)


def _period_is_before(
    other_period: Any,
    other_type: Any,
    current_period: Any,
    current_type: Any,
) -> bool:
    other_start = _period_start(other_period, other_type)
    current_start = _period_start(current_period, current_type)
    if other_start is None or current_start is None:
        return False
    return other_start < current_start


def _period_start(period: Any, period_type: Any) -> date | None:
    window = _period_window(period, period_type)
    if window is None:
        return None
    return window[0]


def _date_id_in_window(date_id: Any, window: tuple[date, date] | None) -> bool:
    if window is None:
        return False
    event_date = _date_from_date_id(date_id)
    if event_date is None:
        return False
    start, stop = window
    return start <= event_date <= stop


def _date_from_date_id(value: Any) -> date | None:
    if value is None:
        return None
    number = int(value)
    year, month_day = divmod(number, 10000)
    month, day = divmod(month_day, 100)
    return date(year, month, day)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _strip_feature_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key in FORBIDDEN_COLUMNS or key in TOKEN_COLUMNS:
            continue
        if key.endswith("_token"):
            continue
        cleaned[key] = value
    return cleaned
