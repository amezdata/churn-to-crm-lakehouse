"""Reverse ETL: vault to crm.scores_churn; the token appears only there."""

from datetime import date

from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS
from transforms.reverse_etl import (
    BAND_HIGH,
    BAND_LOW,
    BAND_MEDIUM,
    CRM_COLUMNS,
    build_crm_scores_churn,
)


def _score(**overrides: object) -> dict:
    item = {
        "student_id": 1,
        "enrolment_id": 10,
        "source_system": "stemstar_rdbms",
        "score_churn": 0.8,
        "partition": "test",
        "is_churn": True,
    }
    item.update(overrides)
    return item


def _vault(**overrides: object) -> dict:
    item = {
        "student_id": 1,
        "student_token": "tok-1",
        "source_system": "stemstar_rdbms",
    }
    item.update(overrides)
    return item


def test_join_writes_token_only_in_crm_schema() -> None:
    scores = [
        _score(student_id=1, enrolment_id=10, score_churn=0.9),
        _score(student_id=2, enrolment_id=20, score_churn=0.2),
    ]
    vault = [_vault(student_id=1, student_token="tok-a"), _vault(student_id=2, student_token="tok-b")]
    rows, metrics = build_crm_scores_churn(scores, vault, scored_on=date(2026, 9, 12))
    assert metrics["n_written"] == 2
    assert metrics["n_missing_from_vault"] == 0
    assert {row["enrolment_id"]: row["student_token"] for row in rows} == {10: "tok-a", 20: "tok-b"}
    for row in rows:
        assert set(row) == set(CRM_COLUMNS)
        assert row["scoring_date"] == date(2026, 9, 12)
        leaked = {
            key
            for key in row
            if key in FORBIDDEN_COLUMNS or (key in TOKEN_COLUMNS and key != "student_token")
        }
        assert not leaked
        assert "partition" not in row
        assert "is_churn" not in row
        assert "name" not in row


def test_missing_vault_row_is_dropped() -> None:
    scores = [_score(student_id=1), _score(student_id=99, enrolment_id=99)]
    vault = [_vault(student_id=1)]
    rows, metrics = build_crm_scores_churn(scores, vault, scored_on=date(2026, 9, 12))
    assert metrics["n_missing_from_vault"] == 1
    assert [row["student_id"] for row in rows] == [1]


def test_top_decile_is_high() -> None:
    scores = [_score(student_id=i, enrolment_id=i, score_churn=i / 100) for i in range(1, 11)]
    vault = [_vault(student_id=i, student_token=f"tok-{i}") for i in range(1, 11)]
    rows, metrics = build_crm_scores_churn(scores, vault, scored_on=date(2026, 9, 12))
    by_enrolment = {row["enrolment_id"]: row for row in rows}
    assert by_enrolment[10]["risk_band"] == BAND_HIGH
    assert by_enrolment[1]["risk_band"] == BAND_LOW
    assert metrics["n_high"] == 1
    assert metrics["n_medium"] == 2
    assert metrics["n_low"] == 7
    assert {row["risk_band"] for row in rows} <= {BAND_HIGH, BAND_MEDIUM, BAND_LOW}


def test_does_not_mutate_gold_scores() -> None:
    scores = [_score()]
    vault = [_vault()]
    snapshot = dict(scores[0])
    build_crm_scores_churn(scores, vault, scored_on=date(2026, 9, 12))
    assert scores[0] == snapshot
    assert "student_token" not in scores[0]


def test_joins_when_id_types_differ() -> None:
    scores = [_score(student_id="1", enrolment_id=10, score_churn=0.9)]
    vault = [_vault(student_id=1, student_token="tok-a")]
    rows, metrics = build_crm_scores_churn(scores, vault, scored_on=date(2026, 9, 12))
    assert metrics["n_written"] == 1
    assert rows[0]["student_token"] == "tok-a"
