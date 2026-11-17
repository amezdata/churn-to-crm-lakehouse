"""Write the generated tables as CSV (structured) and JSON Lines (platform logs)."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from synthgen.bronze_columns import CSV_FILES, LOGS_FILE, to_bronze_rows

CSV_TABLES = tuple(CSV_FILES.keys())


def write_dataset(tables: dict[str, list[dict[str, Any]]], output_dir: Path) -> dict[str, str]:
    """Persist the dataset and a manifest.json with row counts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for table_name in CSV_TABLES:
        path = output_dir / CSV_FILES[table_name]
        _write_csv(path, to_bronze_rows(table_name, tables[table_name]))
        written[table_name] = str(path)

    logs_path = output_dir / LOGS_FILE
    with logs_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in to_bronze_rows("platform_logs", tables["platform_logs"]):
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    written["platform_logs"] = str(logs_path)

    manifest = {
        "generated_on": date.today().isoformat(),
        "source_system": "brainlab_csv",
        "files": {name: Path(path).name for name, path in written.items()},
        "row_counts": {name: len(rows) for name, rows in tables.items()},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    written["manifest"] = str(manifest_path)
    return written


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty table: {path.name}")
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
