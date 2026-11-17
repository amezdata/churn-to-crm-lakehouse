"""PII policy: DROP forbidden columns and build the identity vault. Never re-hashes tokens."""

from __future__ import annotations

from typing import Any

FORBIDDEN_COLUMNS = {
    "name",
    "email",
    "school_name",
    "full_name",
    "contact_name",
    "contact_email",
    "contact_phone",
    "phone",
    "birth_date",
    "home_district",
    "question_text",
    "answer_text",
    "is_correct",
    "difficulty_score",
}

TOKEN_COLUMNS = {
    "student_token",
    "guardian_token",
    "employee_token",
    "contact_token",
    "educator_token",
    "converted_student_token",
    "invoice_token",
}


def drop_forbidden_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove PII / pedagogical columns in case the source delivers them by mistake."""
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        cleaned.append({key: value for key, value in row.items() if key not in FORBIDDEN_COLUMNS})
    return cleaned


def identity_rows(
    students: list[dict[str, Any]],
    *,
    source_system: str,
) -> list[dict[str, Any]]:
    """Analytical vault: student_id <-> student_token <-> source_system."""
    vault: list[dict[str, Any]] = []
    seen: set[tuple[object, object]] = set()
    for row in students:
        token = row.get("student_token")
        student_id = row.get("student_id")
        if token is None or student_id is None:
            continue
        key = (student_id, token)
        if key in seen:
            continue
        seen.add(key)
        vault.append(
            {
                "student_id": student_id,
                "student_token": token,
                "source_system": row.get("source_system") or source_system,
            }
        )
    return vault


def tokens_unchanged(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> bool:
    """Check that no HMAC token has been rewritten."""
    if len(before) != len(after):
        return False
    for old, new in zip(before, after, strict=True):
        for column in TOKEN_COLUMNS:
            if column in old and old[column] != new.get(column):
                return False
    return True
