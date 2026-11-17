"""Recompute and reconcile the STEMStar renewal KPI."""

from __future__ import annotations

import re
from typing import Any

RENEWAL_THRESHOLD_PCT = 1.0
REFUND_ABSENCE_THRESHOLD = 5
COURSE_PATTERN = re.compile(
    r"^(spark|build|circuit|forge|pixel|brainlab)(?:_(\d+))?$",
    re.IGNORECASE,
)
METRIC_COLUMNS = (
    "enrolled_students",
    "renewals",
    "renewal_rate_pct",
    "total_absences",
    "refunds",
)


def next_academic_year(label: str) -> str:
    start, end = label.split("-")
    end_year = int(end)
    return f"{end_year:02d}-{(end_year + 1) % 100:02d}"


def parse_program(course: str) -> str:
    match = COURSE_PATTERN.match(str(course).strip())
    if not match:
        return str(course).strip().casefold()
    return match.group(1).casefold()


def recompute_renewal_kpi(
    enrolments: list[dict[str, Any]],
    absences: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Same rule as the operational KPI: cohort in year N vs enrolment in year N+1 (any course)."""
    by_year: dict[str, list[dict[str, Any]]] = {}
    for row in enrolments:
        year = str(row["academic_year"])
        by_year.setdefault(year, []).append(row)

    absence_total = _absence_totals(absences or [])
    rows: list[dict[str, Any]] = []
    for year, cohort_rows in sorted(by_year.items()):
        next_year = next_academic_year(year)
        next_tokens = {row["student_token"] for row in by_year.get(next_year, [])}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in cohort_rows:
            grouped.setdefault(str(row["course"]), []).append(row)
        if next_year not in by_year:
            continue
        for course, course_rows in grouped.items():
            enrolled = len(course_rows)
            renewed = sum(1 for row in course_rows if row["student_token"] in next_tokens)
            program = parse_program(course)
            absence_sum = 0
            refunds = 0
            for row in course_rows:
                total = absence_total.get((row["student_token"], year, program), 0)
                absence_sum += total
                if total > REFUND_ABSENCE_THRESHOLD:
                    refunds += 1
            rate = round(100.0 * renewed / enrolled, 2) if enrolled else 0.0
            rows.append(
                {
                    "academic_year": year,
                    "course": course,
                    "enrolled_students": enrolled,
                    "renewals": renewed,
                    "renewal_rate_pct": rate,
                    "total_absences": absence_sum,
                    "refunds": refunds,
                }
            )
    return rows


def reconcile_renewal_kpi(
    lakehouse_kpi: list[dict[str, Any]],
    rdbms_kpi: list[dict[str, Any]],
    *,
    threshold_pct: float = RENEWAL_THRESHOLD_PCT,
) -> list[dict[str, Any]]:
    """Compare the lakehouse recompute with the Bronze copy of the RDBMS KPI table."""
    rdbms_by_key = {
        (str(row["academic_year"]), str(row["course"])): row for row in rdbms_kpi
    }
    lake_by_key = {
        (str(row["academic_year"]), str(row["course"])): row for row in lakehouse_kpi
    }
    keys = sorted(set(rdbms_by_key) | set(lake_by_key))
    report: list[dict[str, Any]] = []
    for year, course in keys:
        lake = lake_by_key.get((year, course), {})
        rdbms = rdbms_by_key.get((year, course), {})
        item: dict[str, Any] = {
            "academic_year": year,
            "course": course,
            "in_lakehouse": bool(lake),
            "in_rdbms": bool(rdbms),
        }
        within = True
        for metric in METRIC_COLUMNS:
            lake_value = _as_float(lake.get(metric))
            rdbms_value = _as_float(rdbms.get(metric))
            item[f"{metric}_lakehouse"] = lake_value
            item[f"{metric}_rdbms"] = rdbms_value
            deviation = _relative_deviation_pct(lake_value, rdbms_value)
            item[f"{metric}_deviation_pct"] = deviation
            if metric in {"enrolled_students", "renewals", "renewal_rate_pct"}:
                within = within and deviation <= threshold_pct
        item["within_threshold"] = within and bool(lake) and bool(rdbms)
        item["threshold_pct"] = threshold_pct
        report.append(item)
    return report


def _absence_totals(absences: list[dict[str, Any]]) -> dict[tuple[Any, str, str], int]:
    totals: dict[tuple[Any, str, str], int] = {}
    for row in absences:
        token = row.get("student_token")
        year = str(row.get("academic_year"))
        program = str(row.get("program", "")).casefold()
        raw_total = row.get("year_total")
        total = int(raw_total) if raw_total is not None else 0
        key = (token, year, program)
        previous = totals.get(key, 0)
        if total > previous:
            totals[key] = total
    return totals


def _as_float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(value)


def _relative_deviation_pct(left: float, right: float) -> float:
    if left == 0.0 and right == 0.0:
        return 0.0
    baseline = max(abs(right), abs(left), 1e-9)
    return round(abs(left - right) / baseline * 100.0, 4)
