"""Minimal observability (PoC): table profiles to gold.data_quality_metrics."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any

from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS

DATA_QUALITY_TABLE = "data_quality_metrics"
METRIC_COLUMNS = (
    "run_date",
    "layer",
    "table_name",
    "metric",
    "column",
    "value",
    "threshold",
    "over_threshold",
    "blocking",
    "detail",
)

METRIC_ROW_COUNT = "row_count"
METRIC_VOLUME_DELTA_PCT = "volume_delta_pct"
METRIC_FRESHNESS_HOURS = "freshness_hours"
METRIC_NULL_RATE = "null_rate"
METRIC_SCHEMA_DRIFT = "schema_drift"
METRIC_CONTRACT_REJECTIONS = "contract_rejections"
METRIC_REJECTION_PCT = "rejection_pct"
METRIC_TABLE_MISSING = "table_missing"

NULL_RATE_THRESHOLD = 0.01
VOLUME_DELTA_THRESHOLD = 0.01
FRESHNESS_HOURS_SLA = 24.0
SCHEMA_DRIFT_THRESHOLD = 0.0

LAYER_BRONZE = "bronze"
LAYER_SILVER = "silver"
LAYER_GOLD = "gold"
LAYER_CRM = "crm"

STUDENT_TOKEN = "student_token"
TOKEN_POLICY_NONE = "none"
TOKEN_POLICY_KEEP = "keep"
TOKEN_POLICY_STUDENT = "student"
INGESTION_DATE_COLUMN = "_ingestion_date"
SCORING_DATE_COLUMN = "scoring_date"

CONTRACTED_TABLES = (
    "brainlab_enrolments",
    "brainlab_attendance",
    "brainlab_platform_logs",
)


@dataclass(frozen=True)
class TableSpec:
    layer: str
    table_name: str
    expected_n: int | None
    required_columns: tuple[str, ...]
    key_columns: tuple[str, ...] = ()
    watermark_column: str | None = None
    token_policy: str = TOKEN_POLICY_NONE
    tracks_rejections: bool = False
    freshness_informational: bool = False

    @property
    def full_name(self) -> str:
        return f"{self.layer}.{self.table_name}"


@dataclass(frozen=True)
class TableProfile:
    layer: str
    table_name: str
    row_count: int
    columns: tuple[str, ...]
    null_rate: dict[str, float] = field(default_factory=dict)
    watermark: date | None = None
    present: bool = True
    n_rejections: int | None = None


OBSERVED_TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        LAYER_BRONZE,
        "stemstar_db_customers_enrolment",
        3469,
        required_columns=(),
        watermark_column=INGESTION_DATE_COLUMN,
        token_policy=TOKEN_POLICY_KEEP,
        freshness_informational=True,
    ),
    TableSpec(
        LAYER_BRONZE,
        "brainlab_enrolments",
        179,
        required_columns=(),
        watermark_column=INGESTION_DATE_COLUMN,
        token_policy=TOKEN_POLICY_KEEP,
        freshness_informational=True,
    ),
    TableSpec(
        LAYER_BRONZE,
        "brainlab_platform_logs",
        2278,
        required_columns=(),
        watermark_column=INGESTION_DATE_COLUMN,
        token_policy=TOKEN_POLICY_KEEP,
        freshness_informational=True,
    ),
    TableSpec(
        LAYER_SILVER,
        "stemstar_students",
        2142,
        ("student_id",),
        ("student_id",),
        token_policy=TOKEN_POLICY_KEEP,
    ),
    TableSpec(
        LAYER_SILVER,
        "stemstar_enrolments",
        3469,
        ("student_id", "enrolment_id"),
        ("student_id", "enrolment_id"),
        token_policy=TOKEN_POLICY_KEEP,
    ),
    TableSpec(
        LAYER_SILVER,
        "stemstar_absences",
        4785,
        ("student_id",),
        ("student_id",),
        token_policy=TOKEN_POLICY_KEEP,
    ),
    TableSpec(
        LAYER_SILVER,
        "brainlab_students",
        48,
        ("student_id",),
        ("student_id",),
        token_policy=TOKEN_POLICY_KEEP,
    ),
    TableSpec(
        LAYER_SILVER,
        "brainlab_enrolments",
        179,
        ("student_id", "enrolment_id"),
        ("student_id", "enrolment_id"),
        token_policy=TOKEN_POLICY_KEEP,
    ),
    TableSpec(
        LAYER_SILVER,
        "brainlab_attendance",
        1287,
        ("student_id",),
        ("student_id",),
        token_policy=TOKEN_POLICY_KEEP,
    ),
    TableSpec(
        LAYER_SILVER,
        "brainlab_platform_logs",
        2268,
        ("event_id",),
        ("event_id",),
        token_policy=TOKEN_POLICY_KEEP,
    ),
    TableSpec(
        LAYER_SILVER,
        "identity_map",
        2190,
        ("student_id", STUDENT_TOKEN, "source_system"),
        ("student_id", STUDENT_TOKEN),
        token_policy=TOKEN_POLICY_STUDENT,
    ),
    TableSpec(
        LAYER_SILVER,
        "kpi_reconciliation",
        44,
        ("academic_year", "course"),
        ("academic_year", "course"),
    ),
    TableSpec(
        LAYER_SILVER,
        "contract_violations",
        0,
        (),
        tracks_rejections=True,
    ),
    TableSpec(LAYER_GOLD, "dim_date", 1781, ("date_id", "date"), ("date_id",)),
    TableSpec(LAYER_GOLD, "dim_campus", 1, ("campus_id", "campus"), ("campus_id",)),
    TableSpec(
        LAYER_GOLD,
        "dim_student",
        2190,
        ("student_id", "source_system"),
        ("student_id",),
    ),
    TableSpec(
        LAYER_GOLD,
        "dim_program",
        8,
        ("program_id", "program_key"),
        ("program_id",),
    ),
    TableSpec(LAYER_GOLD, "dim_employee", 35, ("employee_id",), ("employee_id",)),
    TableSpec(LAYER_GOLD, "dim_room", 8, ("room_id",), ("room_id",)),
    TableSpec(
        LAYER_GOLD,
        "fact_enrolment",
        3648,
        ("enrolment_id", "student_id"),
        ("enrolment_id", "student_id"),
    ),
    TableSpec(
        LAYER_GOLD,
        "fact_attendance",
        93920,
        ("attendance_id", "student_id"),
        ("attendance_id", "student_id"),
    ),
    TableSpec(LAYER_GOLD, "fact_payment", 179, ("payment_id",), ("payment_id",)),
    TableSpec(LAYER_GOLD, "fact_occupancy", 370, ("occupancy_id",), ("occupancy_id",)),
    TableSpec(LAYER_GOLD, "fact_lead", 82, ("lead_id",), ("lead_id",)),
    TableSpec(
        LAYER_GOLD,
        "fact_renewal_kpi",
        44,
        ("academic_year", "course"),
        ("academic_year", "course"),
    ),
    TableSpec(
        LAYER_GOLD,
        "features_churn",
        3648,
        ("enrolment_id", "student_id", "is_churn"),
        ("enrolment_id", "student_id"),
    ),
    TableSpec(
        LAYER_GOLD,
        "scores_churn",
        3648,
        ("enrolment_id", "student_id", "score_churn"),
        ("enrolment_id", "student_id"),
    ),
    TableSpec(
        LAYER_CRM,
        "scores_churn",
        3648,
        ("enrolment_id", "student_id", STUDENT_TOKEN, "risk_band"),
        ("enrolment_id", "student_id", STUDENT_TOKEN),
        watermark_column=SCORING_DATE_COLUMN,
        token_policy=TOKEN_POLICY_STUDENT,
        freshness_informational=True,
    ),
)

_SPEC_BY_KEY = {(spec.layer, spec.table_name): spec for spec in OBSERVED_TABLES}


def spec_for(layer: str, table_name: str) -> TableSpec | None:
    return _SPEC_BY_KEY.get((layer, table_name))


def profile_from_rows(
    layer: str,
    table_name: str,
    rows: list[dict[str, Any]] | None,
    *,
    spec: TableSpec | None = None,
) -> TableProfile:
    """Build a profile from rows (pytest). The notebook uses Spark aggregates."""
    table_spec = spec or spec_for(layer, table_name)
    if rows is None:
        return TableProfile(
            layer=layer,
            table_name=table_name,
            row_count=0,
            columns=(),
            present=False,
            n_rejections=0 if table_spec is not None and table_spec.tracks_rejections else None,
        )
    columns = _columns_from_rows(rows)
    key_columns = table_spec.key_columns if table_spec is not None else ()
    watermark_column = table_spec.watermark_column if table_spec is not None else None
    row_count = len(rows)
    null_rate = {column: _null_rate(rows, column) for column in key_columns}
    watermark = _max_watermark(rows, watermark_column) if watermark_column else None
    n_rejections = row_count if table_spec is not None and table_spec.tracks_rejections else None
    return TableProfile(
        layer=layer,
        table_name=table_name,
        row_count=row_count,
        columns=columns,
        null_rate=null_rate,
        watermark=watermark,
        present=True,
        n_rejections=n_rejections,
    )


def build_data_quality_metrics(
    profiles: list[TableProfile],
    *,
    run_at: date | datetime | None = None,
    contracted_row_count: int | None = None,
    fill_missing_catalog: bool = False,
    expected_volumes: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Evaluate thresholds. Does not read Spark or rewrite business tables.

    `expected_volumes` ("layer.table" -> rows) replaces the built-in expected row counts, which are those of
    a seed-42 synthetic run. Tables left out of it get no volume check.
    """
    executed_on = _as_date(run_at) or date.today()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def resolve(spec: TableSpec | None) -> TableSpec | None:
        if spec is None or expected_volumes is None:
            return spec
        return replace(spec, expected_n=expected_volumes.get(spec.full_name))

    for profile in profiles:
        spec = resolve(spec_for(profile.layer, profile.table_name))
        rows.extend(_metrics_for_profile(profile, spec, executed_on))
        seen.add((profile.layer, profile.table_name))
    if fill_missing_catalog:
        for spec in map(resolve, OBSERVED_TABLES):
            if (spec.layer, spec.table_name) in seen:
                continue
            missing = TableProfile(
                layer=spec.layer,
                table_name=spec.table_name,
                row_count=0,
                columns=(),
                present=False,
                n_rejections=0 if spec.tracks_rejections else None,
            )
            rows.extend(_metrics_for_profile(missing, spec, executed_on))

    rejection_count = _rejection_count(profiles)
    contracted_n = (
        contracted_row_count
        if contracted_row_count is not None
        else _contracted_row_count(profiles)
    )
    rows.extend(_contract_rejection_metrics(executed_on, rejection_count, contracted_n))

    cleaned = [_strip_metric_row(row) for row in rows]
    summary = summarize_metrics(cleaned)
    return cleaned, summary


def summarize_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    blocking = [row for row in rows if row["over_threshold"] and row["blocking"]]
    informative = [row for row in rows if row["over_threshold"] and not row["blocking"]]
    return {
        "n_metrics": len(rows),
        "n_over_threshold": sum(1 for row in rows if row["over_threshold"]),
        "n_blocking": len(blocking),
        "n_informational": len(informative),
        "passes_gates": len(blocking) == 0,
    }


def _metrics_for_profile(
    profile: TableProfile,
    spec: TableSpec | None,
    executed_on: date,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    layer = profile.layer
    table_name = profile.table_name
    if not profile.present:
        rows.append(
            _metric_row(
                executed_on,
                layer,
                table_name,
                METRIC_TABLE_MISSING,
                1.0,
                SCHEMA_DRIFT_THRESHOLD,
                blocking=True,
                detail="table missing",
            )
        )
        expected_n = spec.expected_n if spec is not None else None
        if expected_n is not None and expected_n > 0:
            rows.append(
                _metric_row(
                    executed_on,
                    layer,
                    table_name,
                    METRIC_VOLUME_DELTA_PCT,
                    1.0,
                    VOLUME_DELTA_THRESHOLD,
                    blocking=True,
                    detail=f"expected={expected_n}; actual=0",
                )
            )
        return rows

    rows.append(
        _metric_row(
            executed_on,
            layer,
            table_name,
            METRIC_ROW_COUNT,
            float(profile.row_count),
            threshold=None,
            blocking=False,
        )
    )
    if spec is not None and spec.expected_n is not None:
        delta = _volume_delta_pct(profile.row_count, spec.expected_n)
        rows.append(
            _metric_row(
                executed_on,
                layer,
                table_name,
                METRIC_VOLUME_DELTA_PCT,
                delta,
                VOLUME_DELTA_THRESHOLD,
                blocking=True,
                detail=f"expected={spec.expected_n}; actual={profile.row_count}",
            )
        )
    if spec is not None:
        drift_value, drift_detail = _schema_drift(profile, spec)
        rows.append(
            _metric_row(
                executed_on,
                layer,
                table_name,
                METRIC_SCHEMA_DRIFT,
                float(drift_value),
                SCHEMA_DRIFT_THRESHOLD,
                blocking=True,
                detail=drift_detail,
            )
        )
        watermark_column = spec.watermark_column
        if watermark_column:
            hours = _freshness_hours(profile.watermark, executed_on)
            if hours is not None:
                rows.append(
                    _metric_row(
                        executed_on,
                        layer,
                        table_name,
                        METRIC_FRESHNESS_HOURS,
                        hours,
                        FRESHNESS_HOURS_SLA,
                        blocking=not spec.freshness_informational,
                        detail=f"watermark={profile.watermark.isoformat() if profile.watermark else 'null'}",
                    )
                )
        for column in spec.key_columns:
            rate = profile.null_rate.get(column)
            if rate is None:
                rate = 1.0 if column not in profile.columns else 0.0
            rows.append(
                _metric_row(
                    executed_on,
                    layer,
                    table_name,
                    METRIC_NULL_RATE,
                    rate,
                    NULL_RATE_THRESHOLD,
                    blocking=True,
                    column=column,
                )
            )
        if spec.tracks_rejections:
            n_rejections = profile.n_rejections if profile.n_rejections is not None else profile.row_count
            rows.append(
                _metric_row(
                    executed_on,
                    layer,
                    table_name,
                    METRIC_CONTRACT_REJECTIONS,
                    float(n_rejections),
                    0.0,
                    blocking=True,
                )
            )
    return rows


def _contract_rejection_metrics(
    executed_on: date,
    rejection_count: int,
    contracted_n: int,
) -> list[dict[str, Any]]:
    pct = 0.0 if contracted_n <= 0 else rejection_count / contracted_n
    return [
        _metric_row(
            executed_on,
            LAYER_SILVER,
            "contract_violations",
            METRIC_REJECTION_PCT,
            pct,
            0.0,
            blocking=True,
            detail=f"rejections={rejection_count}; contracted_rows={contracted_n}",
        )
    ]


def _schema_drift(profile: TableProfile, spec: TableSpec) -> tuple[int, str | None]:
    present = set(profile.columns)
    missing = [column for column in spec.required_columns if column not in present]
    forbidden = sorted(name for name in present if name in FORBIDDEN_COLUMNS)
    leaked_tokens = _leaked_token_columns(present, spec.token_policy)
    n_issues = len(missing) + len(forbidden) + len(leaked_tokens)
    if n_issues == 0:
        return 0, None
    parts: list[str] = []
    if missing:
        parts.append("missing=" + ",".join(missing))
    if forbidden:
        parts.append("pii=" + ",".join(forbidden))
    if leaked_tokens:
        parts.append("token=" + ",".join(leaked_tokens))
    return n_issues, "; ".join(parts)


def _leaked_token_columns(present: set[str], token_policy: str) -> list[str]:
    found = sorted(
        name for name in present if name in TOKEN_COLUMNS or name.endswith("_token")
    )
    if token_policy == TOKEN_POLICY_KEEP:
        return []
    if token_policy == TOKEN_POLICY_STUDENT:
        return [name for name in found if name != STUDENT_TOKEN]
    return found


def _volume_delta_pct(actual: int, expected: int) -> float:
    if expected == 0:
        return 0.0 if actual == 0 else 1.0
    return abs(actual - expected) / expected


def _freshness_hours(watermark: date | None, executed_on: date) -> float | None:
    if watermark is None:
        return None
    delta: timedelta = datetime.combine(executed_on, datetime.min.time()) - datetime.combine(
        watermark, datetime.min.time()
    )
    hours = delta.total_seconds() / 3600.0
    return max(hours, 0.0)


def _null_rate(rows: list[dict[str, Any]], column: str) -> float:
    if not rows:
        return 1.0
    missing = sum(1 for row in rows if _is_empty(row.get(column)))
    return missing / len(rows)


def _max_watermark(rows: list[dict[str, Any]], column: str | None) -> date | None:
    if not column:
        return None
    latest: date | None = None
    for row in rows:
        parsed = _as_date(row.get(column))
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest


def _columns_from_rows(rows: list[dict[str, Any]]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return tuple(ordered)


def _rejection_count(profiles: list[TableProfile]) -> int:
    for profile in profiles:
        spec = spec_for(profile.layer, profile.table_name)
        if spec is not None and spec.tracks_rejections:
            if profile.n_rejections is not None:
                return profile.n_rejections
            return profile.row_count if profile.present else 0
    return 0


def _contracted_row_count(profiles: list[TableProfile]) -> int:
    total = 0
    for profile in profiles:
        if profile.layer == LAYER_SILVER and profile.table_name in CONTRACTED_TABLES and profile.present:
            total += profile.row_count
    return total


def _metric_row(
    executed_on: date,
    layer: str,
    table_name: str,
    metric: str,
    value: float,
    threshold: float | None,
    *,
    blocking: bool,
    column: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    over = False if threshold is None else value > threshold
    return {
        "run_date": executed_on,
        "layer": layer,
        "table_name": table_name,
        "metric": metric,
        "column": column,
        "value": round(float(value), 6),
        "threshold": None if threshold is None else round(float(threshold), 6),
        "over_threshold": over,
        "blocking": bool(blocking),
        "detail": detail,
    }


def _strip_metric_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key in METRIC_COLUMNS:
        value = row.get(key)
        if key in FORBIDDEN_COLUMNS or key in TOKEN_COLUMNS or str(key).endswith("_token"):
            continue
        cleaned[key] = value
    leaked = [key for key in row if key in FORBIDDEN_COLUMNS or key in TOKEN_COLUMNS]
    assert not leaked, leaked
    return cleaned


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "T" in text:
        return datetime.fromisoformat(text).date()
    return date.fromisoformat(text[:10])
