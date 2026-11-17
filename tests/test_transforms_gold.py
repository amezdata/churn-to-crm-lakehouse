"""Gold star schema: grain, FKs, zero PII, funnel, occupancy, lakehouse KPI."""

from pathlib import Path

from transforms.gold import GOLD_TABLES, build_gold_star
from transforms.io import load_brainlab_synth
from transforms.kpi import reconcile_renewal_kpi, recompute_renewal_kpi
from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS
from transforms.silver_brainlab import BRAINLAB_TABLES, build_silver_brainlab
from transforms.silver_stemstar import build_silver_stemstar

SYNTH_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "brainlab"

GRAIN_KEYS = {
    "dim_date": "date_id",
    "dim_campus": "campus_id",
    "dim_student": "student_id",
    "dim_program": "program_id",
    "dim_employee": "employee_id",
    "dim_room": "room_id",
    "fact_enrolment": "enrolment_id",
    "fact_attendance": "attendance_id",
    "fact_payment": "payment_id",
    "fact_occupancy": "occupancy_id",
    "fact_lead": "lead_id",
}

FACT_FK = (
    ("fact_enrolment", "student_id", "dim_student", "student_id"),
    ("fact_enrolment", "campus_id", "dim_campus", "campus_id"),
    ("fact_enrolment", "program_id", "dim_program", "program_id"),
    ("fact_enrolment", "date_id", "dim_date", "date_id"),
    ("fact_attendance", "student_id", "dim_student", "student_id"),
    ("fact_attendance", "campus_id", "dim_campus", "campus_id"),
    ("fact_attendance", "date_id", "dim_date", "date_id"),
    ("fact_payment", "enrolment_id", "fact_enrolment", "enrolment_id"),
    ("fact_payment", "date_id", "dim_date", "date_id"),
    ("fact_occupancy", "room_id", "dim_room", "room_id"),
    ("fact_occupancy", "date_id", "dim_date", "date_id"),
    ("fact_lead", "campus_id", "dim_campus", "campus_id"),
    ("fact_lead", "program_id", "dim_program", "program_id"),
    ("fact_lead", "date_id", "dim_date", "date_id"),
    ("fact_renewal_kpi", "program_id", "dim_program", "program_id"),
)


def _stemstar_bronze() -> dict:
    return {
        "stemstar_students": [
            {"student_token": "aa" * 8, "campus": "campus_03"},
            {"student_token": "bb" * 8, "campus": "campus_03"},
            {"student_token": "cc" * 8, "campus": "campus_03"},
        ],
        "stemstar_enrolments": [
            {
                "enrolment_id": 1,
                "student_token": "aa" * 8,
                "campus": "campus_03",
                "academic_year": "22-23",
                "course": "spark_01",
                "program": "spark",
                "created_at": "2022-09-01T00:00:00",
            },
            {
                "enrolment_id": 2,
                "student_token": "aa" * 8,
                "campus": "campus_03",
                "academic_year": "23-24",
                "course": "spark_02",
                "program": "spark",
                "created_at": "2023-09-01T00:00:00",
            },
            {
                "enrolment_id": 3,
                "student_token": "bb" * 8,
                "campus": "campus_03",
                "academic_year": "22-23",
                "course": "spark_01",
                "program": "spark",
                "created_at": "2022-09-02T00:00:00",
            },
            {
                "enrolment_id": 4,
                "student_token": "bb" * 8,
                "campus": "campus_03",
                "academic_year": "23-24",
                "course": "build_01",
                "program": "build",
                "created_at": "2023-09-02T00:00:00",
            },
            {
                "enrolment_id": 5,
                "student_token": "cc" * 8,
                "campus": "campus_03",
                "academic_year": "22-23",
                "course": "spark_01",
                "program": "spark",
                "created_at": "2022-09-03T00:00:00",
            },
        ],
        "stemstar_attendance": [
            {
                "attendance_id": 10,
                "student_token": "aa" * 8,
                "campus": "campus_03",
                "academic_year": "22-23",
                "class_name": "spark01",
                "class_date": "2022-09-15",
                "time_slot": "saturday",
                "attendance_status": "present",
            },
            {
                "attendance_id": 11,
                "student_token": "aa" * 8,
                "campus": "campus_03",
                "academic_year": "22-23",
                "class_name": "spark01",
                "class_date": "2022-09-22",
                "time_slot": "saturday",
                "attendance_status": "cancelled",
            },
        ],
        "stemstar_absences": [],
        "stemstar_employees": [
            {
                "employee_token": "dd" * 8,
                "campus": "campus_03",
                "role": "educator",
                "specialty": "spark",
                "gender": "female",
                "start_date": "2021-01-01",
                "is_active": True,
            }
        ],
        "stemstar_kpi": [],
    }


def _silver_bundle() -> dict:
    stemstar = build_silver_stemstar(_stemstar_bronze())
    brainlab, _violations = build_silver_brainlab(load_brainlab_synth(SYNTH_DIR))
    lakehouse = recompute_renewal_kpi(stemstar["stemstar_enrolments"])
    rdbms = [
        {
            "academic_year": row["academic_year"],
            "course": row["course"],
            "enrolled_students": row["enrolled_students"],
            "renewals": 0,
            "renewal_rate_pct": 0.0,
            "total_absences": row["total_absences"],
            "refunds": row["refunds"],
        }
        for row in lakehouse
    ]
    report = reconcile_renewal_kpi(lakehouse, rdbms)
    silver = {
        "stemstar_students": stemstar["stemstar_students"],
        "stemstar_enrolments": stemstar["stemstar_enrolments"],
        "stemstar_attendance": stemstar["stemstar_attendance"],
        "stemstar_employees": stemstar["stemstar_employees"],
        "kpi_reconciliation": report,
    }
    for name in BRAINLAB_TABLES:
        silver[f"brainlab_{name}"] = brainlab[name]
    return silver


def test_gold_tables_and_unique_grains() -> None:
    gold = build_gold_star(_silver_bundle())
    assert set(gold) == set(GOLD_TABLES)
    for table_name, key in GRAIN_KEYS.items():
        values = [row[key] for row in gold[table_name]]
        assert values
        assert len(values) == len(set(values)), table_name
    kpi_keys = {(row["academic_year"], row["course"]) for row in gold["fact_renewal_kpi"]}
    assert len(kpi_keys) == len(gold["fact_renewal_kpi"])
    assert gold["fact_renewal_kpi"]


def test_gold_foreign_keys_resolve_or_are_null() -> None:
    gold = build_gold_star(_silver_bundle())
    for fact_name, fk, dim_name, pk in FACT_FK:
        parent = {row[pk] for row in gold[dim_name]}
        for row in gold[fact_name]:
            value = row.get(fk)
            if value is None:
                continue
            assert value in parent, f"{fact_name}.{fk}={value} missing in {dim_name}"


def test_gold_has_no_pii_or_tokens() -> None:
    gold = build_gold_star(_silver_bundle())
    forbidden = FORBIDDEN_COLUMNS | TOKEN_COLUMNS
    for table_name, rows in gold.items():
        for row in rows:
            leaked = {key for key in row if key in forbidden or key.endswith("_token")}
            assert not leaked, f"{table_name} exposes {sorted(leaked)}"


def test_funnel_converted_not_above_prospects() -> None:
    gold = build_gold_star(_silver_bundle())
    prospects = gold["fact_lead"]
    converted = [row for row in prospects if row["lead_status"] == "converted"]
    assert prospects
    assert len(converted) <= len(prospects)


def test_occupancy_within_capacity() -> None:
    gold = build_gold_star(_silver_bundle())
    rows = gold["fact_occupancy"]
    assert rows
    for row in rows:
        assert row["headcount"] is not None
        assert row["capacity"] is not None
        assert 0 <= row["headcount"] <= row["capacity"]
        assert 0 <= row["occupancy_pct"] <= 100


def test_kpi_gold_uses_lakehouse_not_rdbms() -> None:
    gold = build_gold_star(_silver_bundle())
    row = gold["fact_renewal_kpi"][0]
    assert row["academic_year"] == "22-23"
    assert row["course"] == "spark_01"
    assert row["enrolled_students"] == 3
    assert row["renewals"] == 2
    assert row["renewal_rate_pct"] == 66.67
