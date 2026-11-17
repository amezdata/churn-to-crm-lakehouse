"""Churn feature table: grain, label, zero PII."""

from transforms.features_churn import build_features_churn
from transforms.gold import build_gold_star
from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS

from test_transforms_gold import _silver_bundle

SOURCE_STEMSTAR = "stemstar_rdbms"
SOURCE_BRAINLAB = "brainlab_csv"


def _gold() -> dict:
    return build_gold_star(_silver_bundle())


def test_features_one_row_per_enrolment() -> None:
    gold = _gold()
    features = build_features_churn(gold)
    enrolment_ids = [row["enrolment_id"] for row in gold["fact_enrolment"]]
    feature_ids = [row["enrolment_id"] for row in features]
    assert feature_ids
    assert len(feature_ids) == len(set(feature_ids))
    assert set(feature_ids) == set(enrolment_ids)


def test_features_have_no_pii_or_tokens() -> None:
    features = build_features_churn(_gold())
    forbidden = FORBIDDEN_COLUMNS | TOKEN_COLUMNS
    for row in features:
        leaked = {key for key in row if key in forbidden or key.endswith("_token")}
        assert not leaked, sorted(leaked)


def test_stemstar_label_matches_kpi_rule() -> None:
    features = build_features_churn(_gold())
    by_enrolment = {row["enrolment_id"]: row for row in features}
    year_22 = by_enrolment[1]
    year_23 = by_enrolment[2]
    churned = by_enrolment[5]
    assert year_22["source_system"] == SOURCE_STEMSTAR
    assert year_22["academic_period"] == "22-23"
    assert year_22["renewed_next_period"] is True
    assert year_22["is_churn"] is False
    assert year_22["n_prior_renewals"] == 0
    assert year_22["is_renewal"] is False
    assert year_22["amount_paid"] is None
    assert year_22["n_payments"] is None
    assert year_22["n_absences"] == 0
    assert year_22["is_refund"] is False
    assert year_23["academic_period"] == "23-24"
    assert year_23["renewed_next_period"] is None
    assert year_23["is_churn"] is None
    assert year_23["n_prior_renewals"] == 1
    assert year_23["is_renewal"] is True
    assert churned["renewed_next_period"] is False
    assert churned["is_churn"] is True


def test_stemstar_attendance_excludes_cancelled() -> None:
    features = build_features_churn(_gold())
    row = next(item for item in features if item["enrolment_id"] == 1)
    assert row["n_present"] == 1
    assert row["n_attendance_denominator"] == 1
    assert row["attendance_rate"] == 1.0


def test_brainlab_label_requires_same_program_next_term() -> None:
    gold = _gold()
    features = build_features_churn(gold)
    brainlab = [row for row in features if row["source_system"] == SOURCE_BRAINLAB]
    autumn = [row for row in brainlab if row["academic_period"] == "2026-Autumn"]
    spring = [row for row in brainlab if row["academic_period"] == "2027-Spring"]
    assert autumn
    assert spring
    assert all(row["renewed_next_period"] is not None for row in autumn)
    assert all(row["is_churn"] is not None for row in autumn)
    assert all(row["renewed_next_period"] is None for row in spring)
    assert all(row["is_churn"] is None for row in spring)

    enrolment_by_id = {row["enrolment_id"]: row for row in gold["fact_enrolment"]}
    students_spring_by_program: dict[tuple[object, object], set[object]] = {}
    for row in gold["fact_enrolment"]:
        if row.get("source_system") != SOURCE_BRAINLAB:
            continue
        if row.get("academic_period") != "2027-Spring":
            continue
        students_spring_by_program.setdefault(
            (row.get("student_id"), row.get("program_id")), set()
        ).add(row["enrolment_id"])
    for row in autumn:
        enrolment = enrolment_by_id[row["enrolment_id"]]
        expected = (enrolment["student_id"], enrolment["program_id"]) in students_spring_by_program
        assert row["renewed_next_period"] is expected
        assert row["n_absences"] is None
        assert row["is_refund"] is None
        if row["amount_paid"] is not None:
            assert row["n_payments"] is not None
            assert row["n_payments"] >= 1


def test_stemstar_refund_is_feature_not_label() -> None:
    gold = _gold()
    churned = next(row for row in gold["fact_enrolment"] if row["enrolment_id"] == 5)
    gold["stemstar_absences"] = [
        {
            "student_id": churned["student_id"],
            "academic_year": "22-23",
            "program": "spark",
            "year_total": 8,
        }
    ]
    features = build_features_churn(gold)
    row = next(item for item in features if item["enrolment_id"] == 5)
    assert row["n_absences"] == 8
    assert row["is_refund"] is True
    assert row["is_churn"] is True
    assert row["renewed_next_period"] is False
    renewed = next(item for item in features if item["enrolment_id"] == 1)
    assert renewed["is_refund"] is False
    assert renewed["is_churn"] is False


def test_attendance_rate_bounds() -> None:
    for row in build_features_churn(_gold()):
        rate = row["attendance_rate"]
        if rate is None:
            assert row["n_attendance_denominator"] == 0
            continue
        assert 0.0 <= rate <= 1.0
        assert row["n_present"] <= row["n_attendance_denominator"]
