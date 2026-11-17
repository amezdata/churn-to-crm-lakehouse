"""Churn training: HGB vs logistic regression and dummy. No tokens; does not touch the star schema."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from transforms.features_churn import SOURCE_BRAINLAB, SOURCE_STEMSTAR
from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS

SCORES_CHURN_TABLE = "scores_churn"
RANDOM_STATE = 42
TEST_SIZE = 0.3
NUMERIC_MEDIAN = (
    "tenure_days",
    "attendance_rate",
    "n_prior_renewals",
    "n_absences",
)
BOOLEAN_FEATURES = ("is_renewal", "is_refund")
FEATURE_COLUMNS = NUMERIC_MEDIAN + BOOLEAN_FEATURES
PARTITION_TRAIN = "train"
PARTITION_TEST = "test"
PARTITION_UNLABELED = "unlabeled"
PARTITION_BRAINLAB = "brainlab"


def train_and_score_churn(
    features: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Train on labeled STEMStar only and score every row (BrainLab rows are scored only)."""
    train_rows, test_rows, unlabeled_rows, brainlab_rows = split_churn_rows(features)
    if not train_rows:
        raise ValueError("No training rows (all unlabeled or empty split).")

    train_frame = _feature_matrix(train_rows)
    y_train = _labels(train_rows)
    median_cols = _columns_with_variance(train_frame, NUMERIC_MEDIAN)
    flag_cols = _columns_with_variance(train_frame, BOOLEAN_FEATURES)
    model = _make_pipeline(_gradient_boosting(), median_cols, flag_cols)
    logistic = _make_pipeline(LogisticRegression(max_iter=1000, solver="lbfgs"), median_cols, flag_cols)
    dummy = _make_pipeline(DummyClassifier(strategy="most_frequent", random_state=RANDOM_STATE), median_cols, flag_cols)
    model.fit(train_frame, y_train)
    logistic.fit(train_frame, y_train)
    dummy.fit(train_frame, y_train)

    metrics: dict[str, Any] = {
        "n_train": len(train_rows),
        "n_test": len(test_rows),
        "n_unlabeled": len(unlabeled_rows),
        "n_brainlab": len(brainlab_rows),
        "churn_rate_train": round(float(np.mean(y_train)), 4) if len(y_train) else None,
        "churn_rate_test": None,
        "auc_model": None,
        "auc_logistic": None,
        "auc_dummy": None,
        "precision_at_decile_model": None,
        "precision_at_decile_logistic": None,
        "precision_at_decile_dummy": None,
        "beats_baselines": False,
    }
    if test_rows:
        test_frame = _feature_matrix(test_rows)
        y_test = _labels(test_rows)
        proba_model = _positive_proba(model, test_frame)
        proba_logistic = _positive_proba(logistic, test_frame)
        proba_dummy = _positive_proba(dummy, test_frame)
        metrics["churn_rate_test"] = round(float(np.mean(y_test)), 4)
        metrics["auc_model"] = _auc(y_test, proba_model)
        metrics["auc_logistic"] = _auc(y_test, proba_logistic)
        metrics["auc_dummy"] = _auc(y_test, proba_dummy)
        metrics["precision_at_decile_model"] = _precision_at_decile(y_test, proba_model)
        metrics["precision_at_decile_logistic"] = _precision_at_decile(y_test, proba_logistic)
        metrics["precision_at_decile_dummy"] = _precision_at_decile(y_test, proba_dummy)
        metrics["beats_baselines"] = _beats_baselines(metrics)

    train_ids = {row["enrolment_id"] for row in train_rows}
    test_ids = {row["enrolment_id"] for row in test_rows}
    brainlab_ids = {row["enrolment_id"] for row in brainlab_rows}
    scores: list[dict[str, Any]] = []
    all_frame = _feature_matrix(features)
    all_proba = _positive_proba(model, all_frame)
    for row, score in zip(features, all_proba, strict=True):
        enrolment_id = row.get("enrolment_id")
        if enrolment_id in train_ids:
            partition = PARTITION_TRAIN
        elif enrolment_id in test_ids:
            partition = PARTITION_TEST
        elif enrolment_id in brainlab_ids:
            partition = PARTITION_BRAINLAB
        else:
            partition = PARTITION_UNLABELED
        scores.append(
            _strip_score_row(
                {
                    "student_id": row.get("student_id"),
                    "enrolment_id": enrolment_id,
                    "source_system": row.get("source_system"),
                    "academic_period": row.get("academic_period"),
                    "score_churn": round(float(score), 6),
                    "partition": partition,
                    "is_churn": _as_bool_or_none(row.get("is_churn")),
                }
            )
        )
    return scores, metrics


def split_churn_rows(
    features: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Train/test = labeled STEMStar (temporal holdout). BrainLab rows never enter the fit. Unlabeled = STEMStar rows without a label."""
    stemstar = [row for row in features if row.get("source_system") == SOURCE_STEMSTAR]
    brainlab = [row for row in features if row.get("source_system") == SOURCE_BRAINLAB]
    labeled = [row for row in stemstar if _as_bool_or_none(row.get("is_churn")) is not None]
    unlabeled = [row for row in stemstar if _as_bool_or_none(row.get("is_churn")) is None]
    train, test = _split_stemstar(labeled)
    return train, test, unlabeled, brainlab


def _split_stemstar(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    periods = sorted({str(row["academic_period"]) for row in rows if row.get("academic_period")})
    if len(periods) >= 2:
        holdout = periods[-1]
        train = [row for row in rows if str(row.get("academic_period")) != holdout]
        test = [row for row in rows if str(row.get("academic_period")) == holdout]
        if train and test:
            return train, test
    return _split_stratified(rows)


def _split_stratified(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(rows) < 2:
        return list(rows), []
    labels = _labels(rows)
    stratify = labels if len(set(labels)) > 1 else None
    try:
        train, test = train_test_split(
            rows,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=stratify,
        )
    except ValueError:
        train, test = train_test_split(
            rows,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
            stratify=None,
        )
    return list(train), list(test)


def _gradient_boosting() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_depth=4,
        learning_rate=0.08,
        max_iter=80,
        min_samples_leaf=20,
        random_state=RANDOM_STATE,
    )


def _beats_baselines(metrics: dict[str, Any]) -> bool:
    model_auc = metrics.get("auc_model")
    logistic_auc = metrics.get("auc_logistic")
    dummy_auc = metrics.get("auc_dummy")
    if model_auc is None or logistic_auc is None or dummy_auc is None:
        return False
    return model_auc > logistic_auc and model_auc > dummy_auc


def _columns_with_variance(frame: pd.DataFrame, names: tuple[str, ...]) -> list[str]:
    kept: list[str] = []
    for name in names:
        if name not in frame.columns:
            continue
        if int(frame[name].nunique(dropna=True)) >= 2:
            kept.append(name)
    return kept


def _make_pipeline(estimator: Any, median_cols: list[str], flag_cols: list[str]) -> Pipeline:
    transformers: list[tuple[str, Any, list[str]]] = []
    if median_cols:
        transformers.append(("median", SimpleImputer(strategy="median"), median_cols))
    if flag_cols:
        transformers.append(("flag", SimpleImputer(strategy="most_frequent"), flag_cols))
    if not transformers:
        return Pipeline(
            [
                ("prep", "passthrough"),
                ("clf", DummyClassifier(strategy="most_frequent", random_state=RANDOM_STATE)),
            ]
        )
    transformer = ColumnTransformer(transformers, remainder="drop")
    return Pipeline([("prep", transformer), ("clf", estimator)])


def _feature_matrix(rows: list[dict[str, Any]]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        records.append(
            {
                "tenure_days": _as_float(row.get("tenure_days")),
                "attendance_rate": _as_float(row.get("attendance_rate")),
                "n_prior_renewals": _as_float(row.get("n_prior_renewals")),
                "n_absences": _as_float(row.get("n_absences")),
                "is_renewal": _as_bool_int(row.get("is_renewal")),
                "is_refund": _as_bool_int(row.get("is_refund")),
            }
        )
    return pd.DataFrame(records, columns=list(FEATURE_COLUMNS))


def _labels(rows: list[dict[str, Any]]) -> list[int]:
    return [int(_as_bool_or_none(row.get("is_churn")) or False) for row in rows]


def _positive_proba(pipeline: Pipeline, frame: pd.DataFrame) -> np.ndarray:
    classifier = pipeline.named_steps["clf"]
    proba = pipeline.predict_proba(frame)
    classes = list(classifier.classes_)
    if 1 in classes:
        return proba[:, classes.index(1)]
    return np.zeros(len(frame), dtype=float)


def _auc(y_true: list[int], scores: np.ndarray) -> float | None:
    if len(set(y_true)) < 2:
        return None
    return round(float(roc_auc_score(y_true, scores)), 4)


def _precision_at_decile(y_true: list[int], scores: np.ndarray) -> float:
    count = len(y_true)
    assert count > 0
    top_k = max(1, count // 10)
    order = np.argsort(-np.asarray(scores, dtype=float))
    picked = np.asarray(y_true, dtype=int)[order[:top_k]]
    return round(float(np.mean(picked)), 4)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _as_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    return None


def _as_bool_int(value: Any) -> int | None:
    flag = _as_bool_or_none(value)
    if flag is None:
        return None
    return int(flag)


def _strip_score_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key in FORBIDDEN_COLUMNS or key in TOKEN_COLUMNS:
            continue
        if key.endswith("_token"):
            continue
        cleaned[key] = value
    return cleaned
