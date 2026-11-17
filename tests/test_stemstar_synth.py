"""The synthetic STEMStar extracts are consistent with each other and carry the absence signal."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import pytest

from stemstar_synth.generate import MISCOUNTED_KPI_ROWS, NEXT_LIST_YEAR, YEARS, generate
from transforms.kpi import parse_program, reconcile_renewal_kpi, recompute_renewal_kpi
from transforms.refund import ABSENCES_FILE_PATTERN, ABSENCES_PROGRAM_ALIASES, ABSENCES_YEAR_ALIASES

TOKEN = re.compile(r"^[0-9a-f]{16}$")
ABSENCE_FILE = re.compile(ABSENCES_FILE_PATTERN.pattern.replace(r"\.xlsx", r"\.csv"), re.IGNORECASE)


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def out(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("stemstar")
    generate(path, seed=42)
    return path


@pytest.fixture(scope="module")
def lists(out) -> dict[str, list[dict[str, str]]]:
    result = {year: read(out / f"enrolled_students_{year}.csv") for year in YEARS}
    result[NEXT_LIST_YEAR] = read(out / "new_enrolments.csv")
    return result


@pytest.fixture(scope="module")
def absences(out) -> list[dict]:
    """Absence sheets parsed the way the loader does: file-name typos resolved, one row per student."""
    rows = []
    for path in out.glob("*.csv"):
        match = ABSENCE_FILE.match(path.name)
        if not match:
            continue
        program = ABSENCES_PROGRAM_ALIASES.get(match.group(1).lower(), match.group(1).lower())
        year = ABSENCES_YEAR_ALIASES.get((program, match.group(2)), match.group(2))
        for row in read(path):
            rows.append({"student_token": row["name"], "academic_year": year,
                         "program": program, "year_total": int(row["total"])})
    return rows


def test_every_file_in_the_manifest_has_its_row_count(out):
    manifest = json.loads((out / "manifest.json").read_text())
    for name, count in manifest["files"].items():
        assert len(read(out / name)) == count
    assert len(manifest["miscounted_kpi_rows"]) == MISCOUNTED_KPI_ROWS


def test_one_row_per_student_per_list_and_tokens_only(lists, out):
    for rows in lists.values():
        tokens = [row["name"] for row in rows]
        assert len(tokens) == len(set(tokens))
        assert all(TOKEN.match(t) for t in tokens)
    for path in out.glob("*.csv"):
        header = read(path)[0].keys()
        assert not {"first_name", "last_name", "email", "phone", "address"} & set(header)


def test_first_year_has_no_previous_course_column(lists):
    assert "previous_course" not in lists[YEARS[0]][0]
    assert "previous_course" in lists[YEARS[1]][0]


def test_reconciliation_flags_exactly_the_miscounted_rows(out, lists, absences):
    enrolments = [{"student_token": r["name"], "academic_year": year, "course": r["course"]}
                  for year, rows in lists.items() for r in rows]
    legacy = [{**row, "academic_year": year} for year in YEARS for row in read(out / f"kpi_{year}.csv")]
    report = reconcile_renewal_kpi(recompute_renewal_kpi(enrolments, absences), legacy)
    flagged = {(r["academic_year"], r["course"]) for r in report if not r["within_threshold"]}
    expected = {(m["academic_year"], m["course"])
                for m in json.loads((out / "manifest.json").read_text())["miscounted_kpi_rows"]}
    assert flagged == expected
    assert len(report) - len(flagged) > 30


def test_absence_sheets_match_attendance(out, lists, absences):
    from_sheets = {(r["student_token"], r["academic_year"]): r["year_total"] for r in absences}
    for year in YEARS[1:]:
        enrolled = {r["name"] for r in lists[year]}
        sessions: dict[tuple[str, str], set[str]] = defaultdict(set)
        for row in read(out / f"attendance_{year}.csv"):
            if row["name"] in enrolled:
                sessions[(row["name"], row["class_date"])].add(row["attendance_status"])
        derived: dict[str, int] = defaultdict(int)
        for (student, _), statuses in sessions.items():
            if not statuses & {"present", "pending"}:  # a duplicate booking does not make it an absence
                derived[student] += 1
        for student in enrolled:
            assert from_sheets.get((student, year), 0) == derived.get(student, 0)


def test_refunds_count_students_with_more_than_five_absences(out, absences):
    totals = {(r["student_token"], r["academic_year"]): r["year_total"] for r in absences}
    for year in YEARS[1:]:
        kpi_refunds = sum(int(row["refunds"]) for row in read(out / f"kpi_{year}.csv"))
        assert kpi_refunds == sum(1 for (_, y), total in totals.items() if y == year and total > 5)


def test_more_than_five_absences_predicts_non_renewal(lists, absences):
    totals = {(r["student_token"], r["academic_year"]): r["year_total"] for r in absences}
    order = [*YEARS, NEXT_LIST_YEAR]
    renewed = {"high": [], "low": []}
    for i, year in enumerate(YEARS[1:], start=1):
        next_tokens = {r["name"] for r in lists[order[i + 1]]}
        for row in lists[year]:
            if parse_program(row["course"]) == "pixel":  # last program: nothing to renew into
                continue
            group = "high" if totals.get((row["name"], year), 0) > 5 else "low"
            renewed[group].append(row["name"] in next_tokens)
    high = sum(renewed["high"]) / len(renewed["high"])
    low = sum(renewed["low"]) / len(renewed["low"])
    assert high < 0.25 < 0.45 < low


def test_same_seed_same_files_other_seed_different(tmp_path, out):
    generate(tmp_path / "again", seed=42)
    generate(tmp_path / "other", seed=7)
    for path in out.iterdir():
        assert (tmp_path / "again" / path.name).read_bytes() == path.read_bytes()
    name = "enrolled_students_23-24.csv"
    assert (tmp_path / "other" / name).read_bytes() != (out / name).read_bytes()
