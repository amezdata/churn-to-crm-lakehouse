"""Tests for referential integrity and writing of the synthetic generator."""

from pathlib import Path

from synthgen.generate import generate_dataset
from synthgen.validate import collect_integrity_errors
from synthgen.writers import write_dataset


def test_clean_dataset_has_referential_integrity() -> None:
    tables = generate_dataset(seed=42, scale="small", apply_mess=False)
    assert collect_integrity_errors(tables) == []


def test_enrolment_keys_are_unique() -> None:
    tables = generate_dataset(seed=7, scale="small", apply_mess=False)
    keys = [row["enrolment_natural_key"] for row in tables["enrolments"]]
    assert len(keys) == len(set(keys))
    pairs = [
        (row["student_natural_key"], row["offering_natural_key"])
        for row in tables["enrolments"]
    ]
    assert len(pairs) == len(set(pairs))


def test_renewal_chain_points_at_existing_enrolment() -> None:
    tables = generate_dataset(seed=42, scale="small", apply_mess=False)
    keys = {row["enrolment_natural_key"] for row in tables["enrolments"]}
    renewals = [row for row in tables["enrolments"] if row["is_renewal"]]
    assert renewals
    by_key = {row["enrolment_natural_key"]: row for row in tables["enrolments"]}
    for row in renewals:
        previous_key = row["previous_enrolment_natural_key"]
        assert previous_key in keys
        assert by_key[previous_key]["start_date"] <= row["start_date"]


def test_writer_creates_csv_and_jsonl(tmp_path: Path) -> None:
    tables = generate_dataset(seed=42, scale="small", apply_mess=False)
    written = write_dataset(tables, tmp_path)
    assert (tmp_path / "brainlab_enrolments.csv").is_file()
    assert (tmp_path / "brainlab_attendance.csv").is_file()
    assert (tmp_path / "brainlab_occupancy.csv").is_file()
    assert (tmp_path / "brainlab_platform_logs.jsonl").is_file()
    assert (tmp_path / "manifest.json").is_file()
    assert "platform_logs" in written
    header = (tmp_path / "brainlab_attendance.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "attendance_status" in header
    assert "time_slot" in header
