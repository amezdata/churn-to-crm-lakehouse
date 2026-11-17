"""Experimental STEMStar refund label (year_total > 5)."""

from transforms.features_churn import SOURCE_BRAINLAB, SOURCE_STEMSTAR
from transforms.keys import surrogate_id
from transforms.kpi import REFUND_ABSENCE_THRESHOLD
from transforms.refund import relabel_stemstar_refund


def test_brainlab_rows_are_dropped() -> None:
    features = [
        {
            "student_id": 1,
            "enrolment_id": 10,
            "program_id": surrogate_id("program_key", "spark"),
            "source_system": SOURCE_STEMSTAR,
            "academic_period": "22-23",
            "is_churn": False,
        },
        {
            "student_id": 2,
            "enrolment_id": 11,
            "program_id": surrogate_id("program_key", "prg_level_1"),
            "source_system": SOURCE_BRAINLAB,
            "academic_period": "2026-Autumn",
            "is_churn": True,
        },
    ]
    labeled = relabel_stemstar_refund(features, [])
    assert len(labeled) == 1
    assert labeled[0]["enrolment_id"] == 10
    assert labeled[0]["is_churn"] is False


def test_refund_threshold_matches_kpi() -> None:
    program_id = surrogate_id("program_key", "spark")
    features = [
        {
            "student_id": 7,
            "enrolment_id": 1,
            "program_id": program_id,
            "source_system": SOURCE_STEMSTAR,
            "academic_period": "23-24",
            "is_churn": None,
        },
        {
            "student_id": 8,
            "enrolment_id": 2,
            "program_id": program_id,
            "source_system": SOURCE_STEMSTAR,
            "academic_period": "23-24",
            "is_churn": None,
        },
    ]
    absences = [
        {
            "student_id": 7,
            "academic_year": "23-24",
            "program": "spark",
            "year_total": REFUND_ABSENCE_THRESHOLD,
        },
        {
            "student_id": 8,
            "academic_year": "23-24",
            "program": "spark",
            "year_total": REFUND_ABSENCE_THRESHOLD + 1,
        },
    ]
    labeled = {row["enrolment_id"]: row for row in relabel_stemstar_refund(features, absences)}
    assert labeled[1]["is_churn"] is False
    assert labeled[2]["is_churn"] is True
    assert "year_total" not in labeled[1]
    assert labeled[2]["renewed_next_period"] is None
