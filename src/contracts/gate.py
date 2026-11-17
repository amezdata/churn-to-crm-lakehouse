"""Evaluates the quality rules of the data contracts against Silver tables."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from contracts.loader import load_contracts

CONTRACT_TABLE_KEYS = {
    "brainlab_enrolment": "enrolments",
    "brainlab_attendance": "attendance",
    "brainlab_platform_logs": "platform_logs",
}
REFERENTIAL_TABLE_KEYS = {
    "brainlab_sessions": "sessions",
    "brainlab_enrolments": "enrolments",
    "brainlab_students": "students",
}


@dataclass(frozen=True)
class ContractViolation:
    contract: str
    rule: str
    column: str | None
    row_index: int | None
    message: str
    blocking: bool = True


def evaluate_contracts(
    tables: dict[str, list[dict[str, Any]]],
    contracts_dir: Any | None = None,
) -> list[ContractViolation]:
    """Returns violations. `tables` uses the logical table keys (enrolments, attendance, ...)."""
    violations: list[ContractViolation] = []
    for spec in load_contracts(contracts_dir):
        table_key = CONTRACT_TABLE_KEYS.get(spec["name"])
        if table_key is None:
            violations.append(
                ContractViolation(
                    contract=spec["name"],
                    rule="unknown_contract",
                    column=None,
                    row_index=None,
                    message=f"contract has no mapped table: {spec['name']}",
                )
            )
            continue
        rows = tables.get(table_key, [])
        violations.extend(_evaluate_spec(spec, table_key, rows, tables))
    return violations


def assert_contracts(
    tables: dict[str, list[dict[str, Any]]],
    contracts_dir: Any | None = None,
) -> None:
    blocking = [item for item in evaluate_contracts(tables, contracts_dir) if item.blocking]
    if blocking:
        preview = "; ".join(item.message for item in blocking[:12])
        raise AssertionError(f"quality gate failed ({len(blocking)} violations): {preview}")


def _evaluate_spec(
    spec: dict[str, Any],
    table_key: str,
    rows: list[dict[str, Any]],
    catalog: dict[str, list[dict[str, Any]]],
) -> list[ContractViolation]:
    name = spec["name"]
    violations: list[ContractViolation] = []
    schema_by_column = {field["name"]: field for field in spec.get("schema", [])}
    for rule in spec.get("quality", []):
        rule_name = rule["rule"]
        if rule_name == "not_null":
            violations.extend(_rule_not_null(name, rows, rule.get("columns", [])))
        elif rule_name == "allowed_values":
            violations.extend(
                _rule_allowed_values(name, rows, rule["column"], rule.get("values", []))
            )
        elif rule_name == "regex":
            violations.extend(
                _rule_regex(
                    name,
                    rows,
                    rule["column"],
                    rule["pattern"],
                    when=rule.get("when"),
                )
            )
        elif rule_name == "no_pii_columns":
            violations.extend(_rule_forbidden_columns(name, rows, rule.get("forbidden", [])))
        elif rule_name == "no_pedagogical_payload":
            violations.extend(
                _rule_forbidden_columns(name, rows, rule.get("forbidden_fields", []))
            )
        elif rule_name == "referential":
            violations.extend(
                _rule_referential(
                    name,
                    rows,
                    rule["column"],
                    rule["references"],
                    catalog,
                    schema_by_column.get(rule["column"], {}),
                )
            )
        else:
            violations.append(
                ContractViolation(
                    contract=name,
                    rule=rule_name,
                    column=None,
                    row_index=None,
                    message=f"rule not implemented: {rule_name}",
                )
            )
    return violations


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _rule_not_null(
    contract: str, rows: list[dict[str, Any]], columns: list[str]
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    for index, row in enumerate(rows):
        for column in columns:
            if _is_empty(row.get(column)):
                violations.append(
                    ContractViolation(
                        contract=contract,
                        rule="not_null",
                        column=column,
                        row_index=index,
                        message=f"{column} is null in row {index}",
                    )
                )
    return violations


def _rule_allowed_values(
    contract: str, rows: list[dict[str, Any]], column: str, allowed: list[Any]
) -> list[ContractViolation]:
    allowed_set = set(allowed)
    violations: list[ContractViolation] = []
    for index, row in enumerate(rows):
        value = row.get(column)
        if _is_empty(value):
            continue
        if value not in allowed_set:
            violations.append(
                ContractViolation(
                    contract=contract,
                    rule="allowed_values",
                    column=column,
                    row_index=index,
                    message=f"{column}={value!r} is not in {sorted(allowed_set)}",
                )
            )
    return violations


def _rule_regex(
    contract: str,
    rows: list[dict[str, Any]],
    column: str,
    pattern: str,
    when: str | None,
) -> list[ContractViolation]:
    compiled = re.compile(pattern)
    violations: list[ContractViolation] = []
    for index, row in enumerate(rows):
        value = row.get(column)
        if when and "not empty" in when and _is_empty(value):
            continue
        if _is_empty(value):
            continue
        text = str(value)
        if compiled.fullmatch(text) is None:
            violations.append(
                ContractViolation(
                    contract=contract,
                    rule="regex",
                    column=column,
                    row_index=index,
                    message=f"{column}={text!r} does not match {pattern}",
                )
            )
    return violations


def _rule_forbidden_columns(
    contract: str, rows: list[dict[str, Any]], forbidden: list[str]
) -> list[ContractViolation]:
    present = set()
    for row in rows:
        present.update(row)
    hits = sorted(set(forbidden).intersection(present))
    if not hits:
        return []
    return [
        ContractViolation(
            contract=contract,
            rule="forbidden_columns",
            column=column,
            row_index=None,
            message=f"forbidden column present: {column}",
        )
        for column in hits
    ]


def _rule_referential(
    contract: str,
    rows: list[dict[str, Any]],
    column: str,
    references: str,
    catalog: dict[str, list[dict[str, Any]]],
    field_schema: dict[str, Any],
) -> list[ContractViolation]:
    if "." not in references:
        return [
            ContractViolation(
                contract=contract,
                rule="referential",
                column=column,
                row_index=None,
                message=f"malformed reference: {references}",
            )
        ]
    table_alias, target_column = references.split(".", 1)
    table_key = REFERENTIAL_TABLE_KEYS.get(table_alias, table_alias)
    parent_rows = catalog.get(table_key, [])
    parent_keys = {row.get(target_column) for row in parent_rows}
    nullable = bool(field_schema.get("nullable"))
    violations: list[ContractViolation] = []
    for index, row in enumerate(rows):
        value = row.get(column)
        if _is_empty(value):
            if nullable:
                continue
            violations.append(
                ContractViolation(
                    contract=contract,
                    rule="referential",
                    column=column,
                    row_index=index,
                    message=f"{column} is null and the reference {references} is not nullable",
                )
            )
            continue
        if value not in parent_keys:
            violations.append(
                ContractViolation(
                    contract=contract,
                    rule="referential",
                    column=column,
                    row_index=index,
                    message=f"{column}={value!r} does not exist in {table_key}.{target_column}",
                )
            )
    return violations
