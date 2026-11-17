"""Typing, attendance aliases, event-type typos and blank strings."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

ATTENDANCE_ALIASES = {
    "attended": "present",
    "no_show": "absent",
    "tardy": "late",
    "excused_absence": "excused",
    "present": "present",
    "absent": "absent",
    "late": "late",
    "excused": "excused",
}
EVENT_ALIASES = {
    "session_startedd": "session_started",
    "session_pause": "session_paused",
    "session_started": "session_started",
    "session_paused": "session_paused",
    "session_resumed": "session_resumed",
    "session_completed": "session_completed",
    "session_abandoned": "session_abandoned",
}
DATE_COLUMNS = {
    "first_enrolment_date",
    "start_date",
    "end_date",
    "enrolment_date",
    "payment_date",
    "class_date",
    "date",
    "created_date",
    "conversion_date",
    "created_at",
    "updated_at",
    "computed_at",
}
TIMESTAMP_COLUMNS = {"check_in_time", "event_ts", "created_at", "updated_at"}
DECIMAL_COLUMNS = {
    "price_paid",
    "discount",
    "amount",
    "list_price",
    "renewal_rate_pct",
}
INT_COLUMNS = {
    "grade",
    "grade_min",
    "grade_max",
    "default_session_count",
    "duration_hours",
    "step_count",
    "sessions_needed",
    "capacity",
    "seats",
    "round_number",
    "installment_number",
    "phase",
    "step_index",
    "headcount",
    "week",
    "year_total",
    "enrolled_students",
    "renewals",
    "total_absences",
    "refunds",
    "enrolment_id",
    "attendance_id",
    "absence_id",
    "kpi_id",
}
BOOL_COLUMNS = {
    "has_phase_model",
    "is_active",
    "is_educator",
    "is_bookable",
    "is_renewal",
    "is_absent",
}
TRUE_VALUES = {"true", "1", "t", "yes"}
FALSE_VALUES = {"false", "0", "f", "no"}


def conform_rows(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy and conform a Bronze table (English Bronze column names)."""
    return [conform_row(table_name, row) for row in rows]


def conform_row(table_name: str, row: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: _blank_to_none(value) for key, value in row.items()}
    if table_name == "attendance" and "attendance_status" in cleaned:
        status = cleaned["attendance_status"]
        if isinstance(status, str):
            cleaned["attendance_status"] = ATTENDANCE_ALIASES.get(status, status)
    if table_name == "platform_logs" and "event_type" in cleaned:
        event_type = cleaned["event_type"]
        if isinstance(event_type, str):
            cleaned["event_type"] = EVENT_ALIASES.get(event_type, event_type)
    if table_name == "rooms" and isinstance(cleaned.get("room_name"), str):
        cleaned["room_name"] = cleaned["room_name"].strip()
    return {key: _coerce_value(key, value) for key, value in cleaned.items()}


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _coerce_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in BOOL_COLUMNS:
        return _as_bool(value)
    if column in INT_COLUMNS and column not in TIMESTAMP_COLUMNS:
        return _as_int(value)
    if column in DECIMAL_COLUMNS:
        return _as_decimal(value)
    if column in TIMESTAMP_COLUMNS:
        return _as_timestamp(value)
    if column in DATE_COLUMNS:
        return _as_date(value)
    if isinstance(value, str):
        return value.strip() if column == "room_name" else value
    return value


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise ValueError(f"unrecognized boolean: {value!r}")


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("a boolean is not coerced to an integer")
    if isinstance(value, int):
        return value
    return int(str(value).strip())


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value).strip())


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if "T" in text:
        return datetime.fromisoformat(text).date()
    return date.fromisoformat(text[:10])


def _as_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime.combine(value, datetime.min.time())
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
