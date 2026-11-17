"""Synthetic STEMStar extracts: four academic years of enrolments, attendance, absences and legacy KPIs.

Every row is invented: STEMStar is a fictional company. The parameters below are round numbers chosen to
give the data a realistic shape. Two things are built in on purpose:

* Renewal drops with absences, sharply above the refund threshold (more than 5), so the churn model and
  the analysis have a signal to find.
* The extracts are a little messy, the way exports from operational tools are: misspelled file names,
  duplicate bookings, group names that do not match course codes, students who booked and never came,
  and a few legacy KPI rows that were miscounted by hand. The Silver layer and the reconciliation have
  to catch these.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# ---- Parameters ---------------------------------------------------------------------------------

YEARS = ["22-23", "23-24", "24-25", "25-26"]
NEXT_LIST_YEAR = "26-27"  # early enrolment list for the following year, source of 25-26 renewals
CAMPUS = "campus_03"

# Programs in the order students move through them, with class groups and payment tier.
PROGRAMS = {
    "spark": {"groups": 3, "tier": 4, "next": ["build"]},
    "build": {"groups": 3, "tier": 3, "next": ["circuit", "forge"]},
    "circuit": {"groups": 2, "tier": 2, "next": ["forge", "pixel"]},
    "forge": {"groups": 2, "tier": 2, "next": ["circuit", "pixel"]},
    "pixel": {"groups": 1, "tier": 1, "next": []},  # last program: students graduate
}
NEW_STUDENTS = {"22-23": 800, "23-24": 420, "24-25": 360, "25-26": 330, NEXT_LIST_YEAR: 80}
NEW_STUDENT_PROGRAM_MIX = {"spark": 0.45, "build": 0.25, "circuit": 0.12, "forge": 0.12, "pixel": 0.06}

SESSIONS_PER_YEAR = 30
TIME_SLOTS = ["thursday slot_1", "friday slot_1", "saturday slot_1", "saturday slot_2",
              "saturday slot_3", "sunday slot_1", "sunday slot_2", "sunday slot_3"]

REFUND_THRESHOLD = 5          # more than 5 absences entitles the family to a partial refund
LEAVER_SHARE = 0.07           # students who stop coming mid-year: the rest of their sessions are cancelled
DISENGAGED_SHARE = 0.06       # students who keep coming but miss many sessions
BASE_RENEWAL = 0.62           # chance of renewing for a student with no absences
RENEWAL_FACTOR = {"0": 1.0, "1-2": 0.9, "3-5": 0.75, "6+": 0.15}

# Mess in the extracts.
ATTENDANCE_ONLY_SHARE = 0.05  # booked a trial, never enrolled, never came: only cancelled rows
DUPLICATE_BOOKING_SHARE = 0.005
PROGRAM_ONLY_GROUP_SHARE = 0.04  # rows whose class_name is just the program ("build")
PENDING_SESSIONS_LAST_YEAR = 3   # the last year was exported before its final sessions were marked
MISCOUNTED_KPI_ROWS = 3          # legacy KPI rows with renewals counted wrong by hand
ABSENCE_FILE_NAMES = {           # names as the operational tool exported them, typos included
    ("spark", "24-25"): "abscences_spark_24-25.csv",
    ("circuit", "24-25"): "absences_circit_24-25.csv",
    ("build", "25-26"): "absences_build_26-26.csv",
}
EMPLOYEES = {"educator": 25, "coordinator": 2, "reception": 5}


# ---- Model --------------------------------------------------------------------------------------

@dataclass
class StudentYear:
    token: str
    program: str
    group: int
    time_slot: str
    previous_course: str | None
    statuses: list[str] = field(default_factory=list)

    @property
    def course(self) -> str:
        return f"{self.program}_{self.group:02d}"

    @property
    def absences(self) -> int:
        return sum(status not in ("present", "pending") for status in self.statuses)


def token(seed: int, *parts: object) -> str:
    """16 lowercase hex characters, the format the pseudonymisation step expects."""
    material = "|".join(str(part) for part in ("stemstar_synth", seed, *parts))
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def session_dates(year: str) -> list[date]:
    """One session a week from mid-September, skipping two weeks at Christmas and one at Easter."""
    start = date(2000 + int(year[:2]), 9, 15)
    dates, day = [], start
    while len(dates) < SESSIONS_PER_YEAR:
        on_break = (day.month == 12 and day.day > 20) or (day.month == 1 and day.day < 5) \
            or (day.month == 4 and day.day < 8)
        if not on_break:
            dates.append(day)
        day += timedelta(days=7)
    return dates


def attendance_statuses(rng: random.Random) -> list[str]:
    """Statuses for one student's sessions in a year."""
    if rng.random() < LEAVER_SHARE:
        left_at = rng.randint(10, 24)
        return ["present" if rng.random() > 0.05 else "absent" for _ in range(left_at)] + \
            ["cancelled"] * (SESSIONS_PER_YEAR - left_at)
    miss_rate = rng.uniform(0.2, 0.45) if rng.random() < DISENGAGED_SHARE else rng.uniform(0.0, 0.06)
    # absences become more frequent towards the end of the year
    return ["absent" if rng.random() < miss_rate * (0.6 + 0.8 * k / SESSIONS_PER_YEAR) else "present"
            for k in range(SESSIONS_PER_YEAR)]


def renews(rng: random.Random, student: StudentYear) -> bool:
    if not PROGRAMS[student.program]["next"]:
        return False
    if "cancelled" in student.statuses:
        return rng.random() < 0.08
    n = student.absences
    bucket = "0" if n == 0 else "1-2" if n <= 2 else "3-5" if n <= REFUND_THRESHOLD else "6+"
    return rng.random() < BASE_RENEWAL * RENEWAL_FACTOR[bucket]


def simulate(seed: int) -> dict[str, list[StudentYear]]:
    """Enrolment lists per year, each student carrying their attendance for that year."""
    rng = random.Random(seed)
    lists: dict[str, list[StudentYear]] = {}
    returning: list[tuple[str, str, str]] = []  # (token, next program, previous course)
    counter = 0
    for year in [*YEARS, NEXT_LIST_YEAR]:
        cohort = []
        programs = list(NEW_STUDENT_PROGRAM_MIX)
        weights = list(NEW_STUDENT_PROGRAM_MIX.values())
        newcomers = [(token(seed, "student", counter + i), rng.choices(programs, weights)[0], None)
                     for i in range(NEW_STUDENTS[year])]
        counter += NEW_STUDENTS[year]
        for student_token, program, previous in returning + newcomers:
            student = StudentYear(student_token, program, rng.randint(1, PROGRAMS[program]["groups"]),
                                  rng.choice(TIME_SLOTS), previous)
            if year != NEXT_LIST_YEAR:
                student.statuses = attendance_statuses(rng)
            if year == YEARS[-1]:  # exported before the last sessions were marked
                student.statuses[-PENDING_SESSIONS_LAST_YEAR:] = ["pending"] * PENDING_SESSIONS_LAST_YEAR
            cohort.append(student)
        lists[year] = cohort
        returning = [(s.token, rng.choice(PROGRAMS[s.program]["next"]), s.course)
                     for s in cohort if year != NEXT_LIST_YEAR and renews(rng, s)]
    return lists


# ---- Extract files ------------------------------------------------------------------------------

def enrolment_rows(year: str, cohort: list[StudentYear]) -> list[dict]:
    rows = []
    for s in cohort:
        row = {"name": s.token, "campus": CAMPUS,
               # the early next-year list only records the program, not the group
               "course": s.program if year == NEXT_LIST_YEAR else s.course,
               "payment_tier": f"tier_{PROGRAMS[s.program]['tier']}", "first_time_slot": s.time_slot}
        if year != YEARS[0]:  # the first extract predates the previous_course column
            row["previous_course"] = s.previous_course or ""
        rows.append(row)
    return rows


def attendance_rows(rng: random.Random, seed: int, year: str, cohort: list[StudentYear]) -> list[dict]:
    dates = session_dates(year)
    rows = []

    def add(s: StudentYear, k: int, status: str) -> None:
        group = s.program if rng.random() < PROGRAM_ONLY_GROUP_SHARE else f"{s.program}{s.group:02d}"
        rows.append({"campus": CAMPUS, "class_name": group, "class_date": dates[k].isoformat(),
                     "time_slot": s.time_slot, "attendance_status": status, "name": s.token})

    for s in cohort:
        for k, status in enumerate(s.statuses):
            add(s, k, status)
            if status == "present" and rng.random() < DUPLICATE_BOOKING_SHARE:
                add(s, k, "cancelled")  # the same seat booked twice, one booking cancelled
    trials = int(len(cohort) * ATTENDANCE_ONLY_SHARE)
    for i in range(trials):
        program = rng.choice(list(PROGRAMS))
        ghost = StudentYear(token(seed, "trial", year, i), program, 1, rng.choice(TIME_SLOTS), None)
        for k in range(rng.randint(1, 4)):
            add(ghost, k, "cancelled")
    return rows


def absence_files(year: str, cohort: list[StudentYear]) -> dict[str, list[dict]]:
    """Wide absence sheets per program: one row per student with at least one non-present session."""
    files: dict[str, list[dict]] = {}
    for program in PROGRAMS:
        rows = []
        for s in cohort:
            if s.program != program or s.absences == 0:
                continue
            row = {"name": s.token}
            for k, status in enumerate(s.statuses, start=1):
                row[f"week_{k}"] = "1.0" if status not in ("present", "pending") else ""
            row["total"] = s.absences
            rows.append(row)
        if rows:
            name = ABSENCE_FILE_NAMES.get((program, year), f"absences_{program}_{year}.csv")
            files[name] = rows
    return files


def kpi_rows(year: str, cohort: list[StudentYear], next_tokens: set[str]) -> list[dict]:
    """Legacy KPI per course: renewal into the next list, absences and refunds.

    Absences were not recorded in the first year, so its absence and refund columns are 0.
    """
    by_course: dict[str, list[StudentYear]] = {}
    for s in cohort:
        by_course.setdefault(s.course, []).append(s)
    rows = []
    for course, students in sorted(by_course.items()):
        renewed = sum(s.token in next_tokens for s in students)
        recorded = year != YEARS[0]
        rows.append({
            "course": course, "enrolled_students": len(students), "renewals": renewed,
            "renewal_rate_pct": f"{100 * renewed / len(students):.2f}",
            "total_absences": sum(s.absences for s in students) if recorded else 0,
            "refunds": sum(s.absences > REFUND_THRESHOLD for s in students) if recorded else 0,
        })
    return rows


def miscount(rng: random.Random, kpis: dict[str, list[dict]]) -> list[dict]:
    """Shift renewals in a few legacy KPI rows, as a hand-maintained spreadsheet would. Returns what changed."""
    candidates = [(year, row) for year, rows in kpis.items() for row in rows if row["renewals"] >= 10]
    changed = []
    for year, row in rng.sample(candidates, MISCOUNTED_KPI_ROWS):
        delta = rng.choice([-4, -3, 3, 4])
        row["renewals"] = max(0, min(row["enrolled_students"], row["renewals"] + delta))
        row["renewal_rate_pct"] = f"{100 * row['renewals'] / row['enrolled_students']:.2f}"
        changed.append({"academic_year": year, "course": row["course"], "renewals_shifted_by": delta})
    return changed


def employee_rows(rng: random.Random, seed: int) -> list[dict]:
    rows, i = [], 0
    for role, count in EMPLOYEES.items():
        for _ in range(count):
            start = date(2018, 1, 1) + timedelta(days=rng.randint(0, 8 * 365))
            left = rng.random() < 0.3
            end = start + timedelta(days=rng.randint(180, 900)) if left else None
            rows.append({
                "name": token(seed, "employee", i), "campus": CAMPUS, "role": role,
                "specialty": rng.choice(list(PROGRAMS)) if role == "educator" else "",
                "gender": rng.choice(["male", "female"]), "start_date": start.isoformat(),
                "end_date": end.isoformat() if end else "", "is_active": str(not left),
            })
            i += 1
    return rows


def write_csv(path: Path, rows: list[dict]) -> int:
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def generate(output: Path, seed: int = 42) -> dict:
    """Write every extract to `output` and return the manifest."""
    output.mkdir(parents=True, exist_ok=True)
    lists = simulate(seed)
    rng = random.Random(seed + 1)
    counts: dict[str, int] = {}

    def emit(name: str, rows: list[dict]) -> None:
        counts[name] = write_csv(output / name, rows)

    kpis = {}
    for i, year in enumerate(YEARS):
        cohort = lists[year]
        next_year = YEARS[i + 1] if i + 1 < len(YEARS) else NEXT_LIST_YEAR
        emit(f"enrolled_students_{year}.csv", enrolment_rows(year, cohort))
        emit(f"attendance_{year}.csv", attendance_rows(rng, seed, year, cohort))
        if year != YEARS[0]:  # absence sheets started in the second year
            for name, rows in absence_files(year, cohort).items():
                emit(name, rows)
        kpis[year] = kpi_rows(year, cohort, {s.token for s in lists[next_year]})
    miscounted = miscount(rng, kpis)
    for year, rows in kpis.items():
        emit(f"kpi_{year}.csv", rows)
    emit("new_enrolments.csv", enrolment_rows(NEXT_LIST_YEAR, lists[NEXT_LIST_YEAR]))
    emit("employees.csv", employee_rows(rng, seed))

    manifest = {"generator": "stemstar_synth", "seed": seed, "files": dict(sorted(counts.items())),
                "miscounted_kpi_rows": miscounted}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
