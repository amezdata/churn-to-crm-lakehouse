"""The pipeline package: stage selection, settings, local storage, extract parsing and a full local run."""

from __future__ import annotations

from dataclasses import replace

import pytest

from pipeline.cli import run, select_stages
from pipeline.config import load_settings
from pipeline.stages import STAGES, StageFailed, observability
from pipeline.stemstar_extracts import collect_absences
from pipeline.storage import LocalStorage
from stemstar_synth import generate
from transforms.pii import FORBIDDEN_COLUMNS


def test_stages_run_in_layer_order():
    assert list(STAGES) == ["bronze", "silver", "kpi", "gold", "features", "train", "reverse-etl", "observability"]
    assert select_stages() == list(STAGES)
    assert select_stages("train,gold") == ["gold", "train"]
    assert select_stages(start="gold", stop="train") == ["gold", "features", "train"]
    with pytest.raises(SystemExit):
        select_stages("silver,medallion")


def test_settings_come_from_config_then_environment(monkeypatch):
    assert load_settings("local").storage == "local"
    assert load_settings("fabric").storage == "spark"
    assert load_settings("fabric").expected_volumes["gold.fact_attendance"] == 93920
    monkeypatch.setenv("PIPELINE_SEED", "7")
    assert load_settings("local").seed == 7
    assert load_settings("local", {"seed": 3}).seed == 3
    with pytest.raises(FileNotFoundError):
        load_settings("staging")


def test_local_storage_round_trip(tmp_path):
    storage = LocalStorage(tmp_path)
    rows = [{"a": 1, "b": None, "mixed": 5}, {"a": 2, "b": "x", "mixed": "five"}]
    assert storage.write("silver.t", rows) == 2
    assert storage.read("silver.t") == [{"a": 1, "b": None, "mixed": "5"}, {"a": 2, "b": "x", "mixed": "five"}]
    storage.write("silver.t", [])
    assert not storage.exists("silver.t") and storage.read("silver.t") == []
    storage.write("silver.empty", [], empty_columns=("rule",))
    assert storage.exists("silver.empty") and storage.read("silver.empty") == []


def test_bronze_reads_only_the_latest_ingestion(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.write("bronze.t", [{"k": 1, "_ingestion_date": "2026-01-01"}, {"k": 2, "_ingestion_date": "2026-02-01"}],
                  keep_metadata=True)
    assert [row["k"] for row in storage.read("bronze.t", latest_ingestion=True)] == [2]


def test_absence_file_typos_are_resolved(tmp_path):
    generate(tmp_path, seed=42)
    keys = {(row["program"], row["academic_year"]) for row in collect_absences(tmp_path)}
    assert ("circuit", "24-25") in keys and ("build", "25-26") in keys
    assert not any(program == "circit" or year == "26-26" for program, year in keys)


@pytest.fixture(scope="module")
def local_run(tmp_path_factory):
    root = tmp_path_factory.mktemp("run")
    settings = replace(load_settings("local"), lakehouse_dir=root / "lakehouse", stemstar_source=root / "stemstar")
    storage = LocalStorage(settings.lakehouse_dir)
    ok = run(settings, list(STAGES), storage=storage)
    return settings, storage, ok


def test_full_local_run_passes_every_gate(local_run):
    _, storage, ok = local_run
    assert ok
    crm = storage.read("crm.scores_churn")
    assert crm and all(row["student_token"] for row in crm)
    assert {row["risk_band"] for row in crm} == {"high", "medium", "low"}


def test_reconciliation_catches_the_miscounted_legacy_rows(local_run):
    _, storage, _ = local_run
    off = [row for row in storage.read("silver.kpi_reconciliation") if not row["within_threshold"]]
    assert len(off) == 3


def test_no_personal_columns_or_tokens_reach_gold(local_run):
    settings, storage, _ = local_run
    for path in (settings.lakehouse_dir / "gold").glob("*.parquet"):
        columns = set(storage.read(f"gold.{path.stem}")[0]) if storage.read(f"gold.{path.stem}") else set()
        assert not columns & FORBIDDEN_COLUMNS, path.stem
        assert not [c for c in columns if c.endswith("_token")], path.stem


def test_volume_gate_blocks_when_a_table_drifts(local_run):
    settings, storage, _ = local_run
    drifted = replace(settings, expected_volumes={**settings.expected_volumes, "gold.fact_enrolment": 10})
    with pytest.raises(StageFailed, match="fact_enrolment"):
        observability(drifted, storage)
