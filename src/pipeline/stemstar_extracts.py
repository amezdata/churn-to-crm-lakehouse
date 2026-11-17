"""Read the STEMStar operational extracts into the row shape of the three Postgres silos.

In Fabric, the extracts are loaded into Postgres (`scripts/load_supabase.py`) and Fabric copied the
silos to Bronze. Locally the pipeline skips Postgres: the same parsing turns the synthetic CSV extracts
straight into Bronze rows. Both paths share this module, so the parsing rules live in one place.

Extracts can be `.xlsx` or `.csv`. Rows are dicts keyed by the silo column names (`supabase/01_silos.sql`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_CAMPUS = "campus_03"
EXTENSIONS = (".xlsx", ".csv")
NEXT_LIST_YEAR = "26-27"

ENROLLED_STUDENTS_FILE = re.compile(r"^enrolled_students_(\d{2}-\d{2})\.(xlsx|csv)$", re.IGNORECASE)
ATTENDANCE_FILE = re.compile(r"^attendance_(\d{2}-\d{2})\.(xlsx|csv)$", re.IGNORECASE)
KPI_FILE = re.compile(r"^kpi_(\d{2}-\d{2})\.(xlsx|csv)$", re.IGNORECASE)
# Matches the misspelled names the operational tool exported (abscences_, ausencias-style typos).
ABSENCES_FILE = re.compile(r"^abs[cens]+_(\w+)_(\d{2}-\d{2})\.(xlsx|csv)$", re.IGNORECASE)
ABSENCES_PROGRAM_ALIASES = {"circit": "circuit"}
ABSENCES_YEAR_ALIASES = {("build", "26-26"): "25-26"}
COURSE = re.compile(r"^(spark|build|circuit|forge|pixel|brainlab)(?:_(\d+))?$", re.IGNORECASE)
TOKEN = re.compile(r"^[0-9a-f]{16}$")
IGNORED_PREFIXES = ("~$", ".", "_")

# Column order of each silo table, as loaded into Postgres.
SILO_COLUMNS = {
    "student": ("student_token", "campus"),
    "employee": ("employee_token", "campus", "role", "specialty", "gender", "start_date", "end_date", "is_active"),
    "kpi": ("academic_year", "course", "enrolled_students", "renewals", "renewal_rate_pct",
            "total_absences", "refunds"),
    "enrolment": ("student_token", "campus", "academic_year", "course", "program", "section",
                  "payment_tier", "time_slot"),
    "attendance": ("student_token", "campus", "academic_year", "class_name", "class_date", "time_slot",
                   "attendance_status"),
    "absence": ("student_token", "academic_year", "program", "week", "is_absent", "year_total"),
}


def files(source: Path, pattern: re.Pattern) -> list[tuple[Path, re.Match]]:
    found = []
    for path in sorted(source.iterdir()):
        match = pattern.match(path.name)
        if match and path.suffix.lower() in EXTENSIONS and not path.name.startswith(IGNORED_PREFIXES):
            found.append((path, match))
    return found


def read_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.read_excel(path, engine="openpyxl")


def new_enrolments_file(source: Path) -> Path:
    candidates = [p for p in sorted(source.glob("new_*")) if p.suffix.lower() in EXTENSIONS]
    if len(candidates) != 1:
        raise FileNotFoundError(f"expected one new_enrolments file in {source}, found {len(candidates)}")
    return candidates[0]


def empty_to_none(value: object) -> object:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    if not isinstance(value, str) and pd.isna(value):
        return None
    return value


def parse_course(course: str) -> tuple[str, str | None]:
    match = COURSE.match(str(course).strip())
    if not match:
        raise ValueError(f"unrecognised course: {course!r}")
    section = match.group(2)
    return match.group(1).casefold(), f"{int(section):02d}" if section else None


def normalize_token(raw: object) -> str:
    token = str(raw).strip().casefold()
    if not TOKEN.fullmatch(token):
        raise ValueError(f"token is not 16 lowercase hex characters: {raw!r}")
    return token


def parse_date(value: object) -> str | None:
    cleaned = empty_to_none(value)
    return None if cleaned is None else pd.to_datetime(cleaned).date().isoformat()


def parse_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "t", "1", "yes"}
    return bool(value)


def campus_of(record: dict) -> str:
    return str(empty_to_none(record.get("campus")) or DEFAULT_CAMPUS).strip()


def enrolment_lists(source: Path) -> list[tuple[Path, str]]:
    lists = [(path, match.group(1)) for path, match in files(source, ENROLLED_STUDENTS_FILE)]
    return lists + [(new_enrolments_file(source), NEXT_LIST_YEAR)]


def collect_students(source: Path) -> list[dict]:
    """Every token seen in any extract, with its campus."""
    campus: dict[str, str] = {}
    paths = [path for path, _ in enrolment_lists(source)]
    paths += [path for path, _ in files(source, ATTENDANCE_FILE)]
    paths += [path for path, _ in files(source, ABSENCES_FILE)]
    for path in paths:
        for record in read_frame(path).to_dict(orient="records"):
            campus.setdefault(normalize_token(record["name"]), campus_of(record))
    return [{"student_token": t, "campus": c} for t, c in sorted(campus.items())]


def collect_employees(source: Path) -> list[dict]:
    path = next((p for p in sorted(source.glob("employees.*")) if p.suffix.lower() in EXTENSIONS), None)
    if path is None:
        raise FileNotFoundError(f"missing employees extract in {source}")
    rows = []
    for record in read_frame(path).to_dict(orient="records"):
        specialty = empty_to_none(record.get("specialty"))
        rows.append({
            "employee_token": normalize_token(record["name"]),
            "campus": campus_of(record),
            "role": str(record["role"]).strip().casefold(),
            "specialty": str(specialty).strip().casefold() if specialty is not None else None,
            "gender": str(record["gender"]).strip().casefold(),
            "start_date": parse_date(record["start_date"]),
            "end_date": parse_date(record.get("end_date")),
            "is_active": parse_bool(record["is_active"]),
        })
    return rows


def collect_kpis(source: Path) -> list[dict]:
    rows = []
    for path, match in files(source, KPI_FILE):
        for record in read_frame(path).to_dict(orient="records"):
            rows.append({
                "academic_year": match.group(1),
                "course": str(record["course"]).strip(),
                "enrolled_students": int(record["enrolled_students"]),
                "renewals": int(record["renewals"]),
                "renewal_rate_pct": float(record["renewal_rate_pct"]),
                "total_absences": int(record["total_absences"]),
                "refunds": int(record["refunds"]),
            })
    return rows


def collect_enrolments(source: Path) -> list[dict]:
    """One row per student and year (the silo's unique key), from the yearly lists and the early next-year list."""
    rows, seen = [], set()
    for path, academic_year in enrolment_lists(source):
        frame = read_frame(path)
        missing = {"name", "course", "payment_tier"} - set(frame.columns)
        if missing:
            raise KeyError(f"{path.name}: missing columns {sorted(missing)}")
        for record in frame.to_dict(orient="records"):
            token = normalize_token(record["name"])
            if (token, academic_year) in seen:
                continue
            seen.add((token, academic_year))
            course = str(record["course"]).strip()
            program, section = parse_course(course)
            rows.append({
                "student_token": token, "campus": campus_of(record), "academic_year": academic_year,
                "course": course, "program": program, "section": section,
                "payment_tier": str(record["payment_tier"]).strip().casefold(),
                "time_slot": empty_to_none(record.get("first_time_slot")),
            })
    return rows


def collect_attendance(source: Path) -> list[dict]:
    rows = []
    for path, match in files(source, ATTENDANCE_FILE):
        frame = read_frame(path)
        missing = {"name", "class_name", "class_date", "time_slot", "attendance_status"} - set(frame.columns)
        if missing:
            raise KeyError(f"{path.name}: missing columns {sorted(missing)}")
        dates = pd.to_datetime(frame["class_date"]).dt.date.astype(str)
        for record, class_date in zip(frame.to_dict(orient="records"), dates):
            rows.append({
                "student_token": normalize_token(record["name"]), "campus": campus_of(record),
                "academic_year": match.group(1), "class_name": str(record["class_name"]).strip(),
                "class_date": class_date, "time_slot": str(record["time_slot"]).strip(),
                "attendance_status": str(record["attendance_status"]).strip().casefold(),
            })
    return rows


def collect_absences(source: Path) -> list[dict]:
    """Wide week_N sheets to long rows, one per flagged week. File-name typos are resolved here."""
    rows, seen = [], set()
    for path, match in files(source, ABSENCES_FILE):
        program = ABSENCES_PROGRAM_ALIASES.get(match.group(1).casefold(), match.group(1).casefold())
        academic_year = ABSENCES_YEAR_ALIASES.get((program, match.group(2)), match.group(2))
        frame = read_frame(path)
        if "name" not in frame.columns:
            raise KeyError(f"{path.name}: missing name")
        weeks = [c for c in frame.columns if str(c).startswith("week_")]
        for record in frame.to_dict(orient="records"):
            token = normalize_token(record["name"])
            total = empty_to_none(record.get("total"))
            for column in weeks:
                flag = empty_to_none(record.get(column))
                if flag is None or float(flag) == 0:
                    continue
                week = int(str(column).split("_", 1)[1])
                if (token, academic_year, program, week) in seen:
                    continue
                seen.add((token, academic_year, program, week))
                rows.append({
                    "student_token": token, "academic_year": academic_year, "program": program,
                    "week": week, "is_absent": True, "year_total": int(float(total)) if total is not None else None,
                })
    return rows


def collect_all(source: Path) -> dict[str, list[dict]]:
    """All six silo tables, keyed by silo table name."""
    return {
        "student": collect_students(source),
        "employee": collect_employees(source),
        "kpi": collect_kpis(source),
        "enrolment": collect_enrolments(source),
        "attendance": collect_attendance(source),
        "absence": collect_absences(source),
    }


def as_tuples(table: str, rows: list[dict[str, Any]]) -> list[tuple]:
    """Rows in silo column order, for Postgres inserts."""
    return [tuple(row[column] for column in SILO_COLUMNS[table]) for row in rows]
