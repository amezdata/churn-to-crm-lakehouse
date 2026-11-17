"""Experimental STEMStar label: refund if year_total > 5. Does not replace the churn label."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from transforms.features_churn import SOURCE_STEMSTAR
from transforms.keys import attach_student_id, surrogate_id
from transforms.kpi import REFUND_ABSENCE_THRESHOLD, parse_program

ABSENCES_FILE_PATTERN = re.compile(
    r"^abs[cens]+_(\w+)_(\d{2}-\d{2})\.xlsx$",
    re.IGNORECASE,
)
ABSENCES_PROGRAM_ALIASES = {"circit": "circuit"}
ABSENCES_YEAR_ALIASES = {("build", "26-26"): "25-26"}


def relabel_stemstar_refund(
    features: list[dict[str, Any]],
    absences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """STEMStar only. `is_churn` = max year_total of the student/year/program > 5.

    Does not write `year_total` into the features (leakage). A student who does not
    appear in absences gets total 0 (same rule as the KPI: the file lists only absentees).
    """
    totals = _absence_totals_by_student_period_program(absences)
    labeled: list[dict[str, Any]] = []
    for row in features:
        if row.get("source_system") != SOURCE_STEMSTAR:
            continue
        item = dict(row)
        key = _feature_join_key(item)
        total = totals.get(key, 0) if key is not None else 0
        item["is_churn"] = total > REFUND_ABSENCE_THRESHOLD
        item["renewed_next_period"] = None
        labeled.append(item)
    return labeled


def load_stemstar_absences_from_excel(source_dir: Path) -> list[dict[str, Any]]:
    """Read `absences_*_YY-YY.xlsx` (column `name` = token, `total` = year_total)."""
    import pandas as pd

    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source folder not found: {source_dir}")
    rows: list[dict[str, Any]] = []
    for path in sorted(source_dir.glob("*.xlsx")):
        match = ABSENCES_FILE_PATTERN.match(path.name)
        if not match:
            continue
        program = ABSENCES_PROGRAM_ALIASES.get(match.group(1).casefold(), match.group(1).casefold())
        year = ABSENCES_YEAR_ALIASES.get((program, match.group(2)), match.group(2))
        frame = pd.read_excel(path, engine="openpyxl")
        if "name" not in frame.columns or "total" not in frame.columns:
            raise KeyError(f"{path.name} is missing name/total columns: {list(frame.columns)}")
        for raw in frame[["name", "total"]].to_dict(orient="records"):
            token = raw.get("name")
            if token is None or (isinstance(token, float) and pd.isna(token)):
                continue
            total_raw = raw.get("total")
            total = 0 if total_raw is None or (isinstance(total_raw, float) and pd.isna(total_raw)) else int(total_raw)
            rows.append(
                {
                    "student_token": str(token).strip(),
                    "academic_year": year,
                    "program": program,
                    "year_total": total,
                }
            )
    return attach_student_id(rows)


def _absence_totals_by_student_period_program(
    absences: list[dict[str, Any]],
) -> dict[tuple[Any, str, Any], int]:
    enriched = attach_student_id(absences)
    totals: dict[tuple[Any, str, Any], int] = {}
    for row in enriched:
        student_id = _as_join_int(row.get("student_id"))
        year = row.get("academic_year")
        if student_id is None or year is None:
            continue
        program_id = _as_join_int(row.get("program_id"))
        if program_id is None:
            key_value = row.get("program") or row.get("program_key")
            if not key_value:
                continue
            program_id = surrogate_id("program_key", parse_program(str(key_value)))
        key = (student_id, str(year), program_id)
        total = int(row.get("year_total") or 0)
        previous = totals.get(key, 0)
        if total > previous:
            totals[key] = total
    return totals


def _as_join_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _feature_join_key(row: dict[str, Any]) -> tuple[Any, str, Any] | None:
    student_id = _as_join_int(row.get("student_id"))
    period = row.get("academic_period")
    program_id = _as_join_int(row.get("program_id"))
    if student_id is None or period is None or program_id is None:
        return None
    return (student_id, str(period), program_id)
