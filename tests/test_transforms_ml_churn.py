"""Churn model: split, scores in [0, 1], zero PII."""

from transforms.features_churn import SOURCE_BRAINLAB, SOURCE_STEMSTAR, build_features_churn
from transforms.gold import build_gold_star
from transforms.ml_churn import (
    PARTITION_BRAINLAB,
    PARTITION_UNLABELED,
    PARTITION_TEST,
    PARTITION_TRAIN,
    split_churn_rows,
    train_and_score_churn,
)
from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS

from test_transforms_gold import _silver_bundle


def _gold_features() -> list[dict]:
    return build_features_churn(build_gold_star(_silver_bundle()))


def _row(**overrides: object) -> dict:
    item = {
        "student_id": 1,
        "enrolment_id": 1,
        "source_system": SOURCE_STEMSTAR,
        "academic_period": "21-22",
        "tenure_days": 0,
        "attendance_rate": 0.8,
        "n_prior_renewals": 0,
        "is_renewal": False,
        "amount_paid": None,
        "n_payments": None,
        "is_churn": False,
    }
    item.update(overrides)
    return item


def test_stemstar_holdout_is_last_labeled_period() -> None:
    rows = [
        _row(enrolment_id=1, student_id=1, academic_period="21-22", is_churn=False),
        _row(enrolment_id=2, student_id=1, academic_period="22-23", is_churn=True, n_prior_renewals=1),
        _row(enrolment_id=3, student_id=2, academic_period="22-23", is_churn=False),
        _row(enrolment_id=4, student_id=1, academic_period="23-24", is_churn=None),
        _row(
            enrolment_id=10,
            student_id=10,
            source_system=SOURCE_BRAINLAB,
            academic_period="2026-Autumn",
            is_churn=True,
            amount_paid=100.0,
            n_payments=1,
        ),
        _row(
            enrolment_id=11,
            student_id=11,
            source_system=SOURCE_BRAINLAB,
            academic_period="2026-Autumn",
            is_churn=False,
            amount_paid=80.0,
            n_payments=1,
        ),
        _row(
            enrolment_id=12,
            student_id=12,
            source_system=SOURCE_BRAINLAB,
            academic_period="2026-Autumn",
            is_churn=True,
            amount_paid=90.0,
            n_payments=1,
        ),
        _row(
            enrolment_id=13,
            student_id=13,
            source_system=SOURCE_BRAINLAB,
            academic_period="2026-Autumn",
            is_churn=False,
            amount_paid=70.0,
            n_payments=1,
        ),
    ]
    train, test, unlabeled, brainlab = split_churn_rows(rows)
    assert {row["enrolment_id"] for row in unlabeled} == {4}
    assert {row["enrolment_id"] for row in brainlab} == {10, 11, 12, 13}
    assert all(row["source_system"] == SOURCE_STEMSTAR for row in train)
    assert all(row["source_system"] == SOURCE_STEMSTAR for row in test)
    stemstar_train = [row for row in train if row["source_system"] == SOURCE_STEMSTAR]
    stemstar_test = [row for row in test if row["source_system"] == SOURCE_STEMSTAR]
    assert {row["academic_period"] for row in stemstar_train} == {"21-22"}
    assert {row["academic_period"] for row in stemstar_test} == {"22-23"}
    assert {row["enrolment_id"] for row in stemstar_test} == {2, 3}


def test_unlabeled_never_in_train_or_test() -> None:
    features = _gold_features()
    train, test, unlabeled, brainlab = split_churn_rows(features)
    labeled_stemstar = {
        row["enrolment_id"]
        for row in features
        if row["is_churn"] is not None and row["source_system"] == SOURCE_STEMSTAR
    }
    train_ids = {row["enrolment_id"] for row in train}
    test_ids = {row["enrolment_id"] for row in test}
    unlabeled_ids = {row["enrolment_id"] for row in unlabeled}
    brainlab_ids = {row["enrolment_id"] for row in brainlab}
    assert train
    assert not (train_ids & test_ids)
    assert train_ids | test_ids <= labeled_stemstar
    assert all(row["source_system"] == SOURCE_STEMSTAR for row in train)
    assert all(row["source_system"] == SOURCE_STEMSTAR for row in test)
    assert unlabeled_ids == {
        row["enrolment_id"]
        for row in features
        if row["is_churn"] is None and row["source_system"] == SOURCE_STEMSTAR
    }
    assert brainlab_ids == {
        row["enrolment_id"] for row in features if row["source_system"] == SOURCE_BRAINLAB
    }


def test_scores_cover_all_rows_without_tokens() -> None:
    features = _gold_features()
    scores, metrics = train_and_score_churn(features)
    assert len(scores) == len(features)
    assert {row["enrolment_id"] for row in scores} == {row["enrolment_id"] for row in features}
    forbidden = FORBIDDEN_COLUMNS | TOKEN_COLUMNS
    partitions = {row["partition"] for row in scores}
    assert PARTITION_TRAIN in partitions
    assert PARTITION_UNLABELED in partitions
    if any(row["source_system"] == SOURCE_BRAINLAB for row in features):
        assert PARTITION_BRAINLAB in partitions
    for row in scores:
        leaked = {key for key in row if key in forbidden or key.endswith("_token")}
        assert not leaked, sorted(leaked)
        assert 0.0 <= row["score_churn"] <= 1.0
    assert metrics["n_train"] > 0
    assert metrics["n_unlabeled"] == sum(
        1
        for row in features
        if row["is_churn"] is None and row["source_system"] == SOURCE_STEMSTAR
    )
    assert metrics["n_brainlab"] == sum(
        1 for row in features if row["source_system"] == SOURCE_BRAINLAB
    )
    if metrics["n_test"]:
        assert PARTITION_TEST in partitions
        assert metrics["precision_at_decile_model"] is not None
        assert 0.0 <= metrics["precision_at_decile_model"] <= 1.0
        if metrics["auc_model"] is not None:
            assert 0.0 <= metrics["auc_model"] <= 1.0
        if metrics.get("auc_logistic") is not None:
            assert 0.0 <= metrics["auc_logistic"] <= 1.0
        if metrics.get("auc_dummy") is not None:
            assert 0.0 <= metrics["auc_dummy"] <= 1.0
