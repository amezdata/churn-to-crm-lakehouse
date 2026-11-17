"""Local read of the synthetic BrainLab dataset as Bronze (no Fabric)."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from synthgen.bronze_columns import CSV_FILES, LOGS_FILE

SILVER_TABLE_FROM_SYNTH = {
    "programs": "programs",
    "projects": "projects",
    "rooms": "rooms",
    "employees": "employees",
    "students": "students",
    "guardians": "guardians",
    "leads": "leads",
    "offerings": "offerings",
    "enrolments": "enrolments",
    "payments": "payments",
    "sessions": "sessions",
    "attendance": "attendance",
    "occupancy": "occupancy",
}


def load_brainlab_synth(output_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Load the Bronze CSV + JSONL files (equivalent to bronze.brainlab_*)."""
    tables: dict[str, list[dict[str, Any]]] = {}
    for synth_name, filename in CSV_FILES.items():
        path = output_dir / filename
        tables[SILVER_TABLE_FROM_SYNTH[synth_name]] = _read_csv(path)
    logs_path = output_dir / LOGS_FILE
    tables["platform_logs"] = _read_jsonl(logs_path)
    return tables


INGESTION_METADATA_COLUMNS = frozenset({"_source", "_ingestion_date", "_ingestion_ts"})


def drop_ingestion_metadata(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop ingestion metadata. Copy/Hive sometimes leaves `_source ` or `_source=csv`."""
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            name = _normalize_column_name(key)
            if _is_ingestion_metadata(name):
                continue
            item[name] = value
        cleaned.append(item)
    return cleaned


def records_for_spark(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Serialize date/Decimal and nested dicts; column names safe for Delta."""
    payload: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {}
        for key, value in row.items():
            name = _normalize_column_name(key)
            if _is_ingestion_metadata(name):
                continue
            item[name] = _spark_value(value)
        payload.append(item)
    return payload


def _normalize_column_name(name: object) -> str:
    return str(name).strip().strip("`")


def _is_ingestion_metadata(name: str) -> bool:
    stem = name.split("=", 1)[0]
    return stem in INGESTION_METADATA_COLUMNS


def _spark_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), ensure_ascii=False, default=str)
    return value


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows
