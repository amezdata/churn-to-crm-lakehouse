"""Where tables live. Stages only call `read`, `write` and `exists`, so the same stage code runs locally
(Parquet files, queried with DuckDB) and in Fabric (Delta tables through Spark).

Table names are always `layer.table`, e.g. `silver.stemstar_enrolments`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from transforms.io import records_for_spark

INGESTION_METADATA = {"_source", "_ingestion_date", "_ingestion_ts"}
Rows = list[dict[str, Any]]


class Storage(Protocol):
    def read(self, table: str, *, latest_ingestion: bool = False) -> Rows: ...
    def write(self, table: str, rows: Rows, *, keep_metadata: bool = False,
              empty_columns: tuple[str, ...] = ()) -> int: ...
    def exists(self, table: str) -> bool: ...


class LocalStorage:
    """One Parquet file per table under `root/<layer>/<table>.parquet`."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def file(self, table: str) -> Path:
        layer, name = table.split(".", 1)
        return self.root / layer / f"{name}.parquet"

    def exists(self, table: str) -> bool:
        return self.file(table).is_file()

    def read(self, table: str, *, latest_ingestion: bool = False) -> Rows:
        import pyarrow.parquet as pq

        if not self.exists(table):
            return []
        rows = pq.read_table(self.file(table)).to_pylist()
        if latest_ingestion and rows and "_ingestion_date" in rows[0]:
            latest = max(row["_ingestion_date"] for row in rows)
            rows = [row for row in rows if row["_ingestion_date"] == latest]
        return rows

    def write(self, table: str, rows: Rows, *, keep_metadata: bool = False,
              empty_columns: tuple[str, ...] = ()) -> int:
        """Overwrite the table. Bronze keeps its ingestion metadata; later layers drop it.

        With no rows the table is removed, unless `empty_columns` is given: then an empty table with
        those columns is kept, so checks can tell "nothing to report" from "never written".
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = self.file(table)
        payload = [_serializable(row) for row in rows] if keep_metadata else records_for_spark(rows)
        if not payload and not empty_columns:
            path.unlink(missing_ok=True)
            return 0
        if payload:
            columns = list(dict.fromkeys(key for row in payload for key in row))
            data = pa.table({c: _array(pa, [row.get(c) for row in payload]) for c in columns})
        else:
            data = pa.table({c: pa.array([], type=pa.string()) for c in empty_columns})
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(data, path)
        return len(payload)


def _serializable(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {k: v for k, v in row.items() if k in INGESTION_METADATA}
    return {**records_for_spark([row])[0], **metadata}


def _array(pa, values: list[Any]):
    """Let Arrow infer the type; a column with mixed types (dirty Bronze data) is stored as text."""
    try:
        return pa.array(values)
    except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError):
        return pa.array([None if v is None else str(v) for v in values], type=pa.string())


class SparkStorage:
    """Delta tables in the Fabric lakehouse attached to the notebook."""

    def __init__(self, spark) -> None:
        self.spark = spark

    def exists(self, table: str) -> bool:
        return self.spark.catalog.tableExists(table)

    def read(self, table: str, *, latest_ingestion: bool = False) -> Rows:
        from pyspark.sql import functions as F

        if not self.exists(table):
            print("table_missing", table)
            return []
        frame = _normalize_spark_columns(self.spark.table(table))
        if latest_ingestion and "_ingestion_date" in frame.columns:
            latest = frame.agg(F.max("_ingestion_date")).collect()[0][0]
            frame = frame.filter(F.col("_ingestion_date") == latest)
        return [row.asDict(recursive=True) for row in frame.collect()]

    def write(self, table: str, rows: Rows, *, keep_metadata: bool = False,
              empty_columns: tuple[str, ...] = ()) -> int:
        """Overwrite the Delta table. Bronze is written by Data Factory, so metadata is always dropped here."""
        self.spark.sql(f"CREATE SCHEMA IF NOT EXISTS {table.split('.', 1)[0]}")
        payload = records_for_spark(rows)
        if not payload and not empty_columns:
            self.spark.sql(f"DROP TABLE IF EXISTS {table}")
            return 0
        if payload:
            frame = self.spark.createDataFrame(payload)
        else:
            frame = self.spark.createDataFrame([], ", ".join(f"`{c}` string" for c in empty_columns))
        frame = _normalize_spark_columns(frame)
        frame = frame.drop(*[c for c in frame.columns if c in INGESTION_METADATA])
        frame.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)
        return len(payload)


def _normalize_spark_columns(frame):
    """Copy jobs sometimes leave `_source ` (trailing space) or `_source=csv`; Delta rejects those names."""
    for original in list(frame.columns):
        stripped = original.strip().strip("`")
        stem = stripped.split("=", 1)[0]
        canonical = stem if stem in INGESTION_METADATA else stripped
        if canonical == original:
            continue
        frame = frame.drop(original) if canonical in frame.columns else frame.withColumnRenamed(original, canonical)
    return frame


def open_storage(settings, spark=None) -> Storage:
    if settings.storage == "local":
        return LocalStorage(settings.lakehouse_dir)
    if settings.storage == "spark":
        if spark is None:
            raise ValueError("storage 'spark' needs an active SparkSession")
        return SparkStorage(spark)
    raise ValueError(f"unknown storage {settings.storage!r}")
