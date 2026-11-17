"""Load the STEMStar extracts into the three Postgres silos (the system of record).

Parsing is shared with the local pipeline (`pipeline.stemstar_extracts`); this script only writes to Postgres.
Order: student -> employee / kpi -> enrolment -> attendance -> absence. Extracts can be .xlsx or .csv and must
use the English headers and category values allowed by `supabase/01_silos.sql`.

Usage:
    python scripts/load_supabase.py --source-dir data/synthetic/stemstar
    python scripts/load_supabase.py --docker-container supabase-db
    python scripts/load_supabase.py --dsn postgresql://postgres:<password>@127.0.0.1:5432/postgres
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pipeline.stemstar_extracts import as_tuples, collect_all as collect_rows  # noqa: E402

DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_DOCKER_CONTAINER = "supabase-db"
INSERT_PAGE_SIZE = 2000
TRUNCATE_SQL = """
TRUNCATE TABLE
    db_customers.absence,
    db_customers.attendance,
    db_customers.enrolment,
    db_customers.student,
    db_employees.employee,
    db_kpi.kpi_course_renewal
RESTART IDENTITY
"""


def insert_rows(cursor, sql: str, rows: list[tuple], label: str) -> None:
    from psycopg2.extras import execute_values

    if not rows:
        raise ValueError(f"No rows collected for {label}")
    execute_values(cursor, sql, rows, page_size=INSERT_PAGE_SIZE)
    print(f"{label}: {len(rows)} rows")


def truncate_silos(cursor) -> None:
    cursor.execute(TRUNCATE_SQL)


def collect_all(source_directory: Path) -> dict[str, list[tuple]]:
    print(f"Reading extracts from {source_directory}")
    return {table: as_tuples(table, rows) for table, rows in collect_rows(source_directory).items()}


def load_via_dsn(dsn: str, batches: dict[str, list[tuple]]) -> None:
    import psycopg2

    connection = psycopg2.connect(dsn)
    try:
        with connection:
            with connection.cursor() as cursor:
                truncate_silos(cursor)
                insert_rows(
                    cursor,
                    """
                    INSERT INTO db_customers.student (student_token, campus)
                    VALUES %s
                    """,
                    batches["student"],
                    "db_customers.student",
                )
                insert_rows(
                    cursor,
                    """
                    INSERT INTO db_employees.employee (
                        employee_token, campus, role, specialty, gender,
                        start_date, end_date, is_active
                    )
                    VALUES %s
                    """,
                    batches["employee"],
                    "db_employees.employee",
                )
                insert_rows(
                    cursor,
                    """
                    INSERT INTO db_kpi.kpi_course_renewal (
                        academic_year, course, enrolled_students, renewals,
                        renewal_rate_pct, total_absences, refunds
                    )
                    VALUES %s
                    """,
                    batches["kpi"],
                    "db_kpi.kpi_course_renewal",
                )
                insert_rows(
                    cursor,
                    """
                    INSERT INTO db_customers.enrolment (
                        student_token, campus, academic_year, course, program,
                        section, payment_tier, time_slot
                    )
                    VALUES %s
                    """,
                    batches["enrolment"],
                    "db_customers.enrolment",
                )
                insert_rows(
                    cursor,
                    """
                    INSERT INTO db_customers.attendance (
                        student_token, campus, academic_year, class_name,
                        class_date, time_slot, attendance_status
                    )
                    VALUES %s
                    """,
                    batches["attendance"],
                    "db_customers.attendance",
                )
                insert_rows(
                    cursor,
                    """
                    INSERT INTO db_customers.absence (
                        student_token, academic_year, program, week,
                        is_absent, year_total
                    )
                    VALUES %s
                    """,
                    batches["absence"],
                    "db_customers.absence",
                )
    finally:
        connection.close()


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "t" if value else "f"
    return str(value)


def _rows_to_csv(rows: list[tuple]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in rows:
        writer.writerow([_csv_cell(value) for value in row])
    return buffer.getvalue()


def _docker_psql(container: str, sql: str, stdin_text: str | None = None) -> None:
    command = [
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "supabase_admin",
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    result = subprocess.run(
        command,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"docker psql failed ({result.returncode}): {detail}")


def load_via_docker(container: str, batches: dict[str, list[tuple]]) -> None:
    copy_jobs = (
        (
            "db_customers.student",
            "student_token, campus",
            batches["student"],
        ),
        (
            "db_employees.employee",
            "employee_token, campus, role, specialty, gender, start_date, end_date, is_active",
            batches["employee"],
        ),
        (
            "db_kpi.kpi_course_renewal",
            "academic_year, course, enrolled_students, renewals, renewal_rate_pct, total_absences, refunds",
            batches["kpi"],
        ),
        (
            "db_customers.enrolment",
            "student_token, campus, academic_year, course, program, section, payment_tier, time_slot",
            batches["enrolment"],
        ),
        (
            "db_customers.attendance",
            "student_token, campus, academic_year, class_name, class_date, time_slot, attendance_status",
            batches["attendance"],
        ),
        (
            "db_customers.absence",
            "student_token, academic_year, program, week, is_absent, year_total",
            batches["absence"],
        ),
    )
    _docker_psql(container, TRUNCATE_SQL)
    for table_name, column_list, rows in copy_jobs:
        if not rows:
            raise ValueError(f"No rows collected for {table_name}")
        copy_sql = (
            f"COPY {table_name} ({column_list}) FROM STDIN "
            "WITH (FORMAT csv, NULL '')"
        )
        _docker_psql(container, copy_sql, _rows_to_csv(rows))
        print(f"{table_name}: {len(rows)} rows")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load the STEMStar extracts into the three Postgres silos.",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("SUPABASE_DB_URL"),
        help="Postgres URI (or set SUPABASE_DB_URL). Optional when using Docker.",
    )
    parser.add_argument(
        "--docker-container",
        default=None,
        help=(
            "Load via docker exec into this Postgres container "
            f"(default {DEFAULT_DOCKER_CONTAINER} if SUPABASE_DB_URL is unset)"
        ),
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory with the extracts (.xlsx or .csv)",
    )
    return parser.parse_args()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    arguments = parse_arguments()
    docker_container = arguments.docker_container
    if not arguments.dsn and not docker_container:
        docker_container = DEFAULT_DOCKER_CONTAINER
    batches = collect_all(arguments.source_dir.resolve())
    if arguments.dsn:
        load_via_dsn(arguments.dsn, batches)
    else:
        load_via_docker(docker_container, batches)
    print("Load complete")


if __name__ == "__main__":
    main()
