"""Orchestrate BrainLab Bronze -> Silver and evaluate the 3 data contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contracts.gate import ContractViolation, evaluate_contracts
from contracts.loader import default_contracts_dir
from transforms.conform import conform_rows
from transforms.dedup import deduplicate_rows
from transforms.io import drop_ingestion_metadata
from transforms.keys import add_surrogate_keys, attach_student_id
from transforms.pii import drop_forbidden_columns, identity_rows

BRONZE_LAKEHOUSE_TABLES = {
    "programs": "bronze.brainlab_programs",
    "projects": "bronze.brainlab_projects",
    "rooms": "bronze.brainlab_rooms",
    "employees": "bronze.brainlab_employees",
    "students": "bronze.brainlab_students",
    "guardians": "bronze.brainlab_guardians",
    "leads": "bronze.brainlab_leads",
    "offerings": "bronze.brainlab_offerings",
    "enrolments": "bronze.brainlab_enrolments",
    "payments": "bronze.brainlab_payments",
    "sessions": "bronze.brainlab_sessions",
    "attendance": "bronze.brainlab_attendance",
    "occupancy": "bronze.brainlab_occupancy",
    "platform_logs": "bronze.brainlab_platform_logs",
}
BRAINLAB_TABLES = (
    "programs",
    "projects",
    "rooms",
    "employees",
    "students",
    "guardians",
    "leads",
    "offerings",
    "enrolments",
    "payments",
    "sessions",
    "attendance",
    "occupancy",
    "platform_logs",
)
STUDENT_ID_TABLES = (
    "students",
    "guardians",
    "enrolments",
    "payments",
    "attendance",
    "platform_logs",
    "leads",
)


def build_silver_brainlab(
    bronze: dict[str, list[dict[str, Any]]],
    contracts_dir: Path | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[ContractViolation]]:
    """Return the Silver tables and the quality-gate violations."""
    silver: dict[str, list[dict[str, Any]]] = {}
    for table_name in BRAINLAB_TABLES:
        rows = drop_ingestion_metadata(bronze.get(table_name, []))
        rows = conform_rows(table_name, rows)
        rows = deduplicate_rows(table_name, rows)
        rows = drop_forbidden_columns(rows)
        if table_name in STUDENT_ID_TABLES:
            token_column = "converted_student_token" if table_name == "leads" else "student_token"
            if table_name == "leads":
                rows = _attach_optional_student_id(rows, token_column)
            else:
                rows = attach_student_id(rows, token_column)
        rows = add_surrogate_keys(table_name, rows)
        silver[table_name] = rows

    silver["identity_map"] = identity_rows(silver["students"], source_system="brainlab_csv")
    violations = evaluate_contracts(silver, contracts_dir or default_contracts_dir())
    silver["contract_violations"] = [_violation_as_row(item) for item in violations]
    return silver, violations


def _attach_optional_student_id(
    rows: list[dict[str, Any]], token_column: str
) -> list[dict[str, Any]]:
    from transforms.keys import surrogate_id

    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        token = item.get(token_column)
        if token:
            item["student_id"] = surrogate_id("student_token", token)
        enriched.append(item)
    return enriched


def _violation_as_row(item: ContractViolation) -> dict[str, Any]:
    return {
        "contract": item.contract,
        "rule": item.rule,
        "column": item.column,
        "row_index": item.row_index,
        "message": item.message,
        "blocking": item.blocking,
    }
