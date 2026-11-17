"""Ingestion metadata: Copy/Hive can leave spaces or a `_source=csv` spec."""

from datetime import date
from decimal import Decimal

from transforms.io import drop_ingestion_metadata, records_for_spark


def test_ingestion_metadata_with_trailing_space_is_dropped() -> None:
    rows = drop_ingestion_metadata(
        [
            {
                "program_key": "prg_level_1",
                "_source ": "csv",
                " _ingestion_date": "2026-09-08",
                "_ingestion_ts": "2026-09-08T12:00:00Z",
            }
        ]
    )
    assert rows == [{"program_key": "prg_level_1"}]


def test_hive_partition_spec_column_is_dropped() -> None:
    rows = drop_ingestion_metadata(
        [{"student_token": "aa", "_source=csv": "csv", "_ingestion_date=2026-09-08": "2026-09-08"}]
    )
    assert rows == [{"student_token": "aa"}]


def test_records_for_spark_strips_names_and_flattens_nested() -> None:
    payload = records_for_spark(
        [
            {
                " program_key ": "prg_level_1",
                "_source ": "csv",
                "price": Decimal("12.50"),
                "date": date(2026, 9, 8),
                "extra": {"round_number": 1},
            }
        ]
    )
    assert payload == [
        {
            "program_key": "prg_level_1",
            "price": 12.5,
            "date": "2026-09-08",
            "extra": '{"round_number": 1}',
        }
    ]
