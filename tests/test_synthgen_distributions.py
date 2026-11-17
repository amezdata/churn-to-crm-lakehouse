"""Tests for distributions, capacities and the operating calendar."""

from datetime import date

from synthgen.catalog import assert_catalog_invariants, l1_projects
from synthgen.constants import (
    GRADE_MAX,
    GRADE_MIN,
    L2_ROUND_CAPACITY,
    OPEN_WEEKDAYS,
    PLATFORM_EVENT_TYPES,
    PROJECT_HOURS_MAX,
    PROJECT_HOURS_MIN,
    SKILLS_COURSE_CAPACITY,
)
from synthgen.generate import generate_dataset


def test_catalog_respects_operations_envelope() -> None:
    assert_catalog_invariants()
    for project in l1_projects():
        assert PROJECT_HOURS_MIN <= project["duration_hours"] <= PROJECT_HOURS_MAX


def test_student_grades_and_capacity_caps() -> None:
    tables = generate_dataset(seed=42, scale="small", apply_mess=False)
    grades = [int(row["grade"]) for row in tables["students"]]
    assert min(grades) >= GRADE_MIN
    assert max(grades) <= GRADE_MAX

    enrol_counts: dict[str, int] = {}
    for row in tables["enrolments"]:
        enrol_counts[row["offering_natural_key"]] = (
            enrol_counts.get(row["offering_natural_key"], 0) + 1
        )
    by_offering = {row["offering_natural_key"]: row for row in tables["offerings"]}
    for offering_key, count in enrol_counts.items():
        offering = by_offering[offering_key]
        assert count <= int(offering["capacity"])
        if offering["program_natural_key"] == "prg_level_2":
            assert int(offering["capacity"]) <= L2_ROUND_CAPACITY
        if offering["program_natural_key"] == "prg_skills":
            assert int(offering["capacity"]) <= SKILLS_COURSE_CAPACITY
            assert count <= SKILLS_COURSE_CAPACITY


def test_sessions_only_on_open_weekdays() -> None:
    tables = generate_dataset(seed=42, scale="small", apply_mess=False)
    for row in tables["sessions"]:
        weekday = date.fromisoformat(row["session_date"]).weekday()
        assert weekday in OPEN_WEEKDAYS
        assert "slot_" in row["time_slot"]
        assert any(
            day in row["time_slot"]
            for day in ("wednesday", "thursday", "friday", "saturday", "sunday")
        )


def test_platform_logs_are_lifecycle_events_only() -> None:
    tables = generate_dataset(seed=42, scale="small", apply_mess=False)
    forbidden = {"question_text", "answer_text", "is_correct", "difficulty_score"}
    event_types = {row["event_type"] for row in tables["platform_logs"]}
    assert event_types <= set(PLATFORM_EVENT_TYPES)
    assert "session_started" in event_types
    assert {"session_completed", "session_abandoned"} & event_types
    for row in tables["platform_logs"]:
        assert forbidden.isdisjoint(row)
        assert "step_index" in row


def test_overlap_tokens_are_reused_when_provided(tmp_path) -> None:
    seed_file = tmp_path / "tokens.txt"
    seed_file.write_text("aaaaaaaaaaaaaaaa\nbbbbbbbbbbbbbbbb\nnot-a-token\n", encoding="utf-8")
    tables = generate_dataset(
        seed=42,
        scale="small",
        apply_mess=False,
        overlap_tokens_file=seed_file,
    )
    student_keys = {row["student_natural_key"] for row in tables["students"]}
    assert "aaaaaaaaaaaaaaaa" in student_keys
    assert "bbbbbbbbbbbbbbbb" in student_keys
    origins = {row["identity_origin"] for row in tables["students"]}
    assert "stemstar_overlap" in origins
    assert "brainlab_new" in origins
