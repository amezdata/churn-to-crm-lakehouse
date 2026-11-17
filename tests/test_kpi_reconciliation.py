"""KPI reconciliation: threshold under 1 % and cohort N vs year N+1."""

from transforms.kpi import next_academic_year, reconcile_renewal_kpi, recompute_renewal_kpi


def test_next_academic_year_rolls_suffix() -> None:
    assert next_academic_year("22-23") == "23-24"
    assert next_academic_year("25-26") == "26-27"


def _cohort_fixture() -> list[dict]:
    return [
        {"student_token": "aa" * 8, "academic_year": "22-23", "course": "spark_01"},
        {"student_token": "bb" * 8, "academic_year": "22-23", "course": "spark_01"},
        {"student_token": "cc" * 8, "academic_year": "22-23", "course": "spark_01"},
        {"student_token": "aa" * 8, "academic_year": "23-24", "course": "spark_02"},
        {"student_token": "bb" * 8, "academic_year": "23-24", "course": "build_01"},
    ]


def test_recompute_counts_renewal_in_any_next_year_course() -> None:
    kpi = recompute_renewal_kpi(_cohort_fixture())
    assert len(kpi) == 1
    row = kpi[0]
    assert row["academic_year"] == "22-23"
    assert row["course"] == "spark_01"
    assert row["enrolled_students"] == 3
    assert row["renewals"] == 2
    assert row["renewal_rate_pct"] == 66.67


def test_reconcile_within_threshold() -> None:
    lakehouse = recompute_renewal_kpi(_cohort_fixture())
    rdbms = [
        {
            "academic_year": "22-23",
            "course": "spark_01",
            "enrolled_students": 3,
            "renewals": 2,
            "renewal_rate_pct": 66.67,
            "total_absences": 0,
            "refunds": 0,
        }
    ]
    report = reconcile_renewal_kpi(lakehouse, rdbms)
    assert len(report) == 1
    assert report[0]["within_threshold"] is True
    assert report[0]["renewal_rate_pct_deviation_pct"] <= 1.0


def test_reconcile_flags_deviation_above_threshold() -> None:
    lakehouse = recompute_renewal_kpi(_cohort_fixture())
    rdbms = [
        {
            "academic_year": "22-23",
            "course": "spark_01",
            "enrolled_students": 3,
            "renewals": 1,
            "renewal_rate_pct": 33.33,
            "total_absences": 0,
            "refunds": 0,
        }
    ]
    report = reconcile_renewal_kpi(lakehouse, rdbms)
    assert report[0]["within_threshold"] is False
    assert report[0]["renewals_deviation_pct"] > 1.0
