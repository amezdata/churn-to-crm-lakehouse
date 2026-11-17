"""Observability: thresholds, PII, tokens and the observed-table catalog."""

from datetime import date

from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS
from transforms.observability import (
    LAYER_CRM,
    LAYER_GOLD,
    LAYER_SILVER,
    DATA_QUALITY_TABLE,
    METRIC_COLUMNS,
    METRIC_FRESHNESS_HOURS,
    METRIC_CONTRACT_REJECTIONS,
    METRIC_NULL_RATE,
    METRIC_REJECTION_PCT,
    METRIC_SCHEMA_DRIFT,
    METRIC_TABLE_MISSING,
    METRIC_VOLUME_DELTA_PCT,
    OBSERVED_TABLES,
    STUDENT_TOKEN,
    TableProfile,
    build_data_quality_metrics,
    profile_from_rows,
    spec_for,
)


def _by_metric(rows: list[dict], metric: str, *, table_name: str | None = None) -> list[dict]:
    selected = [row for row in rows if row["metric"] == metric]
    if table_name is not None:
        selected = [row for row in selected if row["table_name"] == table_name]
    return selected


def test_catalog_covers_core_without_direct_lake_extras() -> None:
    keys = {(spec.layer, spec.table_name) for spec in OBSERVED_TABLES}
    assert (LAYER_GOLD, "fact_enrolment") in keys
    assert (LAYER_GOLD, "features_churn") in keys
    assert (LAYER_CRM, "scores_churn") in keys
    assert (LAYER_SILVER, "identity_map") in keys
    assert DATA_QUALITY_TABLE not in {spec.table_name for spec in OBSERVED_TABLES if spec.layer == LAYER_GOLD}


def test_healthy_gold_fact_stays_within_thresholds() -> None:
    spec = spec_for(LAYER_GOLD, "fact_enrolment")
    assert spec is not None
    rows = [
        {"enrolment_id": index, "student_id": index, "source_system": "stemstar_rdbms"}
        for index in range(spec.expected_n or 0)
    ]
    profile = profile_from_rows(LAYER_GOLD, "fact_enrolment", rows)
    metrics, summary = build_data_quality_metrics(profiles=[profile], run_at=date(2026, 9, 13))
    assert summary["passes_gates"] is True
    assert summary["n_blocking"] == 0
    delta = _by_metric(metrics, METRIC_VOLUME_DELTA_PCT, table_name="fact_enrolment")
    assert len(delta) == 1
    assert delta[0]["value"] == 0.0
    assert delta[0]["over_threshold"] is False
    drift = _by_metric(metrics, METRIC_SCHEMA_DRIFT, table_name="fact_enrolment")
    assert drift[0]["value"] == 0.0
    for row in metrics:
        assert set(row) == set(METRIC_COLUMNS)
        leaked = {
            key
            for key in row
            if key in FORBIDDEN_COLUMNS or key in TOKEN_COLUMNS or str(key).endswith("_token")
        }
        assert not leaked


def test_volume_drift_is_blocking() -> None:
    rows = [{"student_id": 1, "enrolment_id": 1} for _ in range(10)]
    profile = profile_from_rows(LAYER_GOLD, "fact_enrolment", rows)
    metrics, summary = build_data_quality_metrics(profiles=[profile], run_at=date(2026, 9, 13))
    delta = _by_metric(metrics, METRIC_VOLUME_DELTA_PCT, table_name="fact_enrolment")[0]
    assert delta["over_threshold"] is True
    assert delta["blocking"] is True
    assert summary["passes_gates"] is False


def test_null_rate_on_key_is_blocking() -> None:
    at_threshold = [
        {"student_id": None if index == 0 else index, "source_system": "brainlab_csv"}
        for index in range(100)
    ]
    metrics, _summary = build_data_quality_metrics(
        profiles=[profile_from_rows(LAYER_GOLD, "dim_student", at_threshold)],
        run_at=date(2026, 9, 13),
    )
    nulls = [
        row
        for row in _by_metric(metrics, METRIC_NULL_RATE, table_name="dim_student")
        if row["column"] == "student_id"
    ]
    assert len(nulls) == 1
    assert nulls[0]["value"] == 0.01
    assert nulls[0]["over_threshold"] is False

    over_threshold = at_threshold + [{"student_id": None, "source_system": "brainlab_csv"}]
    metrics, summary = build_data_quality_metrics(
        profiles=[profile_from_rows(LAYER_GOLD, "dim_student", over_threshold)],
        run_at=date(2026, 9, 13),
    )
    nulls = [
        row
        for row in _by_metric(metrics, METRIC_NULL_RATE, table_name="dim_student")
        if row["column"] == "student_id"
    ]
    assert nulls[0]["value"] > 0.01
    assert nulls[0]["over_threshold"] is True
    assert nulls[0]["blocking"] is True
    assert summary["passes_gates"] is False


def test_schema_drift_on_missing_and_forbidden_columns() -> None:
    rows = [{"student_id": 1, "name": "x"}]
    profile = profile_from_rows(LAYER_GOLD, "dim_student", rows)
    metrics, _summary = build_data_quality_metrics(profiles=[profile], run_at=date(2026, 9, 13))
    drift = _by_metric(metrics, METRIC_SCHEMA_DRIFT, table_name="dim_student")[0]
    assert drift["over_threshold"] is True
    assert drift["blocking"] is True
    assert drift["detail"] is not None
    assert "source_system" in drift["detail"]
    assert "name" in drift["detail"]


def test_token_in_gold_is_schema_drift_token_in_vault_is_not() -> None:
    gold_rows = [
        {
            "student_id": 1,
            "enrolment_id": 1,
            "is_churn": False,
            STUDENT_TOKEN: "aa" * 8,
        }
    ]
    gold_profile = profile_from_rows(LAYER_GOLD, "features_churn", gold_rows)
    metrics, _summary = build_data_quality_metrics(profiles=[gold_profile], run_at=date(2026, 9, 13))
    gold_drift = _by_metric(metrics, METRIC_SCHEMA_DRIFT, table_name="features_churn")[0]
    assert gold_drift["over_threshold"] is True
    assert gold_drift["detail"] is not None
    assert STUDENT_TOKEN in gold_drift["detail"]

    vault_rows = [
        {"student_id": 1, STUDENT_TOKEN: "aa" * 8, "source_system": "stemstar_rdbms"}
        for _ in range(2190)
    ]
    vault_profile = profile_from_rows(LAYER_SILVER, "identity_map", vault_rows)
    metrics, summary = build_data_quality_metrics(profiles=[vault_profile], run_at=date(2026, 9, 13))
    vault_drift = _by_metric(metrics, METRIC_SCHEMA_DRIFT, table_name="identity_map")[0]
    assert vault_drift["value"] == 0.0
    assert vault_drift["over_threshold"] is False
    assert summary["n_blocking"] == 0


def test_keep_policy_allows_tokens_in_bronze_and_silver() -> None:
    silver_rows = [
        {"student_id": index, STUDENT_TOKEN: "aa" * 8} for index in range(2142)
    ]
    metrics, summary = build_data_quality_metrics(
        profiles=[profile_from_rows(LAYER_SILVER, "stemstar_students", silver_rows)],
        run_at=date(2026, 9, 13),
    )
    drift = _by_metric(metrics, METRIC_SCHEMA_DRIFT, table_name="stemstar_students")[0]
    assert drift["value"] == 0.0
    assert drift["over_threshold"] is False
    assert summary["n_blocking"] == 0

    bronze_rows = [
        {
            STUDENT_TOKEN: "aa" * 8,
            "guardian_token": "bb" * 8,
            "_ingestion_date": date(2026, 9, 8),
        }
        for _ in range(179)
    ]
    metrics, summary = build_data_quality_metrics(
        profiles=[profile_from_rows("bronze", "brainlab_enrolments", bronze_rows)],
        run_at=date(2026, 9, 13),
    )
    drift = _by_metric(metrics, METRIC_SCHEMA_DRIFT, table_name="brainlab_enrolments")[0]
    assert drift["value"] == 0.0
    assert summary["n_blocking"] == 0
    assert summary["n_informational"] >= 1


def test_kpi_tokens_remain_schema_drift() -> None:
    rows = [
        {"academic_year": "22-23", "course": "spark_01", STUDENT_TOKEN: "aa" * 8}
        for _ in range(42)
    ]
    metrics, summary = build_data_quality_metrics(
        profiles=[profile_from_rows(LAYER_SILVER, "kpi_reconciliation", rows)],
        run_at=date(2026, 9, 13),
    )
    drift = _by_metric(metrics, METRIC_SCHEMA_DRIFT, table_name="kpi_reconciliation")[0]
    assert drift["over_threshold"] is True
    assert drift["detail"] is not None
    assert STUDENT_TOKEN in drift["detail"]
    assert summary["passes_gates"] is False


def test_freshness_over_sla_is_informative_on_bronze() -> None:
    rows = [{"_ingestion_date": date(2026, 9, 8)} for _ in range(179)]
    profile = profile_from_rows("bronze", "brainlab_enrolments", rows)
    metrics, summary = build_data_quality_metrics(profiles=[profile], run_at=date(2026, 9, 13))
    freshness = _by_metric(metrics, METRIC_FRESHNESS_HOURS, table_name="brainlab_enrolments")[0]
    assert freshness["value"] == 120.0
    assert freshness["over_threshold"] is True
    assert freshness["blocking"] is False
    assert summary["n_informational"] >= 1
    assert summary["n_blocking"] == 0
    assert summary["passes_gates"] is True


def test_contract_violations_zero_keeps_pct_at_zero() -> None:
    violations = profile_from_rows(LAYER_SILVER, "contract_violations", [])
    enrolments = profile_from_rows(
        LAYER_SILVER,
        "brainlab_enrolments",
        [{"student_id": 1, "enrolment_id": 1} for _ in range(179)],
    )
    attendance = profile_from_rows(
        LAYER_SILVER,
        "brainlab_attendance",
        [{"student_id": 1} for _ in range(1287)],
    )
    logs = profile_from_rows(
        LAYER_SILVER,
        "brainlab_platform_logs",
        [{"event_id": index} for index in range(2268)],
    )
    metrics, summary = build_data_quality_metrics(
        profiles=[violations, enrolments, attendance, logs],
        run_at=date(2026, 9, 13),
    )
    n_rejections = _by_metric(metrics, METRIC_CONTRACT_REJECTIONS, table_name="contract_violations")[0]
    pct = _by_metric(metrics, METRIC_REJECTION_PCT, table_name="contract_violations")[0]
    assert n_rejections["value"] == 0.0
    assert pct["value"] == 0.0
    assert summary["n_blocking"] == 0

    dirty = profile_from_rows(
        LAYER_SILVER,
        "contract_violations",
        [{"contract": "brainlab_enrolment", "rule": "not_null"}],
    )
    metrics, summary = build_data_quality_metrics(
        profiles=[dirty, enrolments, attendance, logs],
        run_at=date(2026, 9, 13),
    )
    assert _by_metric(metrics, METRIC_CONTRACT_REJECTIONS)[0]["over_threshold"] is True
    assert _by_metric(metrics, METRIC_REJECTION_PCT)[0]["over_threshold"] is True
    assert summary["passes_gates"] is False


def test_missing_catalog_table_is_blocking_when_filled() -> None:
    metrics, summary = build_data_quality_metrics(
        profiles=[],
        run_at=date(2026, 9, 13),
        fill_missing_catalog=True,
    )
    absent = _by_metric(metrics, METRIC_TABLE_MISSING)
    assert len(absent) == len(OBSERVED_TABLES)
    assert all(row["blocking"] for row in absent)
    assert summary["passes_gates"] is False


def test_does_not_mutate_source_profile_rows() -> None:
    source = [{"student_id": 1, "source_system": "brainlab_csv"}]
    snapshot = dict(source[0])
    profile = profile_from_rows(LAYER_GOLD, "dim_student", source)
    build_data_quality_metrics(profiles=[profile], run_at=date(2026, 9, 13))
    assert source[0] == snapshot


def test_crm_allows_student_token_only() -> None:
    rows = [
        {
            "enrolment_id": 1,
            "student_id": 1,
            STUDENT_TOKEN: "bb" * 8,
            "risk_band": "high",
            "scoring_date": date(2026, 9, 13),
            "guardian_token": "no",
        }
    ]
    profile = profile_from_rows(LAYER_CRM, "scores_churn", rows)
    metrics, _summary = build_data_quality_metrics(profiles=[profile], run_at=date(2026, 9, 13))
    drift = _by_metric(metrics, METRIC_SCHEMA_DRIFT, table_name="scores_churn")[0]
    assert drift["over_threshold"] is True
    assert drift["detail"] is not None
    assert "guardian_token" in drift["detail"]
    assert STUDENT_TOKEN not in (drift["detail"] or "")
