"""Orchestrate STEMStar Bronze -> Silver. Never queries the OLTP."""

from __future__ import annotations

from typing import Any

from transforms.conform import conform_rows
from transforms.dedup import deduplicate_rows
from transforms.io import drop_ingestion_metadata
from transforms.keys import add_surrogate_keys, attach_student_id
from transforms.pii import drop_forbidden_columns, identity_rows

BRONZE_LAKEHOUSE_TABLES = {
    "stemstar_students": "bronze.stemstar_db_customers_student",
    "stemstar_enrolments": "bronze.stemstar_db_customers_enrolment",
    "stemstar_attendance": "bronze.stemstar_db_customers_attendance",
    "stemstar_absences": "bronze.stemstar_db_customers_absence",
    "stemstar_employees": "bronze.stemstar_db_employees_employee",
    "stemstar_kpi": "bronze.stemstar_db_kpi_kpi_course_renewal",
}
STEMSTAR_TABLES = {
    "stemstar_students": "students",
    "stemstar_enrolments": "enrolments",
    "stemstar_attendance": "attendance",
    "stemstar_absences": "absences",
    "stemstar_employees": "employees",
    "stemstar_kpi": "kpi",
}
CONFORM_AS = {
    "stemstar_students": "students",
    "stemstar_enrolments": "enrolments",
    "stemstar_attendance": "stemstar_attendance",
    "stemstar_absences": "absences",
    "stemstar_employees": "employees",
    "stemstar_kpi": "kpi",
}
STUDENT_TABLES = {
    "stemstar_students",
    "stemstar_enrolments",
    "stemstar_attendance",
    "stemstar_absences",
}
SOURCE_SYSTEM = "stemstar_rdbms"


def build_silver_stemstar(
    bronze: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """`bronze` is indexed by the keys of STEMSTAR_TABLES (already remapped)."""
    silver: dict[str, list[dict[str, Any]]] = {}
    for table_name in STEMSTAR_TABLES:
        rows = drop_ingestion_metadata(bronze.get(table_name, []))
        rows = conform_rows(CONFORM_AS[table_name], rows)
        rows = deduplicate_rows(table_name, rows)
        rows = drop_forbidden_columns(rows)
        if table_name in STUDENT_TABLES:
            rows = attach_student_id(rows)
        rows = add_surrogate_keys(table_name, rows)
        for row in rows:
            row.setdefault("source_system", SOURCE_SYSTEM)
        silver[table_name] = rows
    silver["identity_map"] = identity_rows(
        silver.get("stemstar_students", []),
        source_system=SOURCE_SYSTEM,
    )
    return silver


def merge_identity_maps(*vaults: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge the STEMStar and BrainLab vaults. The same token shares one student_id."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[object, object, object]] = set()
    for vault in vaults:
        for row in vault:
            key = (row.get("student_id"), row.get("student_token"), row.get("source_system"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(row))
    return merged
