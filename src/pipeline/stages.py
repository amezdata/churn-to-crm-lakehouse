"""The pipeline stages, in run order. Each reads its inputs from storage, calls the tested business logic in
`transforms` / `contracts`, writes its outputs, and returns a small summary for the log.

A stage raises `StageFailed` when a gate blocks: a contract violation, a PII leak or a blocking
data-quality metric. The CLI and the Fabric notebooks call these same functions.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Callable

from pipeline.config import Settings
from pipeline.storage import Storage
from transforms.features_churn import FEATURES_CHURN_TABLE, GOLD_FACT_TABLES, build_features_churn
from transforms.gold import GOLD_TABLES, SILVER_LAKEHOUSE_TABLES, build_gold_star
from transforms.kpi import reconcile_renewal_kpi, recompute_renewal_kpi
from transforms.ml_churn import SCORES_CHURN_TABLE, train_and_score_churn
from transforms.observability import CONTRACTED_TABLES, DATA_QUALITY_TABLE, OBSERVED_TABLES, \
    build_data_quality_metrics, profile_from_rows
from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS
from transforms.reverse_etl import CRM_SCORES_TABLE, build_crm_scores_churn
from transforms.silver_brainlab import BRAINLAB_TABLES, build_silver_brainlab
from transforms.silver_brainlab import BRONZE_LAKEHOUSE_TABLES as BRAINLAB_BRONZE
from transforms.silver_stemstar import BRONZE_LAKEHOUSE_TABLES as STEMSTAR_BRONZE
from transforms.silver_stemstar import build_silver_stemstar, merge_identity_maps

Summary = dict[str, Any]

# Bronze table of each STEMStar silo table, and the surrogate id Postgres would have assigned.
STEMSTAR_SILOS = {
    "student": ("stemstar_students", None),
    "enrolment": ("stemstar_enrolments", "enrolment_id"),
    "attendance": ("stemstar_attendance", "attendance_id"),
    "absence": ("stemstar_absences", "absence_id"),
    "employee": ("stemstar_employees", None),
    "kpi": ("stemstar_kpi", "kpi_id"),
}
STEMSTAR_SILVER_TABLES = ("stemstar_students", "stemstar_enrolments", "stemstar_attendance",
                          "stemstar_absences", "stemstar_employees")
SOURCES = ("stemstar_rdbms", "brainlab_csv")
VIOLATION_COLUMNS = ("contract", "rule", "column", "row_index", "message", "blocking")


class StageFailed(RuntimeError):
    """A gate blocked the run."""


def check_no_pii(table: str, rows: list[dict], allowed_tokens: tuple[str, ...] = ()) -> None:
    """Gold and CRM tables must not carry personal columns or pseudonymous tokens (the CRM may keep student_token)."""
    leaked = {key for row in rows for key in row
              if key in FORBIDDEN_COLUMNS or ((key in TOKEN_COLUMNS or key.endswith("_token"))
                                              and key not in allowed_tokens)}
    if leaked:
        raise StageFailed(f"{table} exposes {sorted(leaked)}")


def count_by(rows: list[dict], column: str, values: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(row.get(column) for row in rows)
    return {value: counts.get(value, 0) for value in values}


# ---- Stages ------------------------------------------------------------------------------------

def bronze(settings: Settings, storage: Storage) -> Summary:
    """Land the raw sources as Bronze, untouched, with ingestion metadata (local runs only).

    In Fabric, Data Factory copy jobs do this: STEMStar silos from Postgres, BrainLab files from OneLake.
    """
    from pipeline.stemstar_extracts import collect_all
    from transforms.io import load_brainlab_synth

    if settings.storage != "local":
        raise StageFailed("the bronze stage runs locally; in Fabric, Bronze is loaded by Data Factory")
    source = settings.stemstar_source
    if settings.generate_stemstar and not any(source.glob("*.csv")):
        from stemstar_synth import generate
        generate(source, seed=settings.seed)
    stamp = {"_ingestion_date": date.today().isoformat()}
    written = {}
    for silo, rows in collect_all(source).items():
        key, id_column = STEMSTAR_SILOS[silo]
        for i, row in enumerate(rows, start=1):
            if id_column:
                row[id_column] = i
            row.update(stamp, _source="stemstar_rdbms")
        written[key] = storage.write(STEMSTAR_BRONZE[key], rows, keep_metadata=True)
    for key, rows in load_brainlab_synth(settings.brainlab_source).items():
        for row in rows:
            row.update(stamp, _source="brainlab_csv")
        written[key] = storage.write(BRAINLAB_BRONZE[key], rows, keep_metadata=True)
    return {"tables": len(written), "rows": sum(written.values())}


def silver(settings: Settings, storage: Storage) -> Summary:
    """Type, deduplicate, key and pseudonymise both sources; BrainLab passes its data contracts first."""
    stemstar_bronze = {key: storage.read(table, latest_ingestion=True) for key, table in STEMSTAR_BRONZE.items()}
    stemstar = build_silver_stemstar(stemstar_bronze)
    for table in STEMSTAR_SILVER_TABLES:
        storage.write(f"silver.{table}", stemstar[table])
    storage.write("silver.identity_map_stemstar", stemstar["identity_map"])

    brainlab_bronze = {key: storage.read(table, latest_ingestion=True) for key, table in BRAINLAB_BRONZE.items()}
    brainlab, violations = build_silver_brainlab(brainlab_bronze, settings.contracts_dir)
    for table in BRAINLAB_TABLES:
        storage.write(f"silver.brainlab_{table}", brainlab[table])
    storage.write("silver.identity_map_brainlab", brainlab["identity_map"])
    storage.write("silver.contract_violations", brainlab["contract_violations"], empty_columns=VIOLATION_COLUMNS)
    storage.write("silver.identity_map", merge_identity_maps(stemstar["identity_map"], brainlab["identity_map"]))

    blocking = [v for v in violations if v.blocking]
    if blocking:
        raise StageFailed(f"data contract failed: {blocking[0].message}")
    return {"stemstar_enrolments": len(stemstar["stemstar_enrolments"]),
            "brainlab_enrolments": len(brainlab["enrolments"]), "contract_violations": len(violations)}


def kpi(settings: Settings, storage: Storage) -> Summary:
    """Recompute the renewal KPI from Silver and reconcile it with the legacy KPI table."""
    lakehouse = recompute_renewal_kpi(storage.read("silver.stemstar_enrolments"),
                                      storage.read("silver.stemstar_absences"))
    legacy = storage.read(STEMSTAR_BRONZE["stemstar_kpi"], latest_ingestion=True)
    report = reconcile_renewal_kpi(lakehouse, legacy, threshold_pct=settings.kpi_tolerance_pct)
    storage.write("silver.kpi_reconciliation", report)
    off = [f"{r['academic_year']} {r['course']}" for r in report if not r["within_threshold"]]
    return {"rows": len(report), "within_tolerance": len(report) - len(off), "off": off}


def gold(settings: Settings, storage: Storage) -> Summary:
    """Star schema: dimensions and facts for the dashboard and the model."""
    tables = build_gold_star({key: storage.read(table) for key, table in SILVER_LAKEHOUSE_TABLES.items()})
    for table in GOLD_TABLES:
        storage.write(f"gold.{table}", tables[table])
    return {"tables": len(GOLD_TABLES), "fact_enrolment": len(tables["fact_enrolment"])}


def features(settings: Settings, storage: Storage) -> Summary:
    """One feature row per enrolment, labelled with whether the student renewed the next period."""
    inputs = {table: storage.read(f"gold.{table}") for table in GOLD_FACT_TABLES}
    inputs["stemstar_absences"] = storage.read("silver.stemstar_absences")
    rows = build_features_churn(inputs)
    storage.write(f"gold.{FEATURES_CHURN_TABLE}", rows)
    return {"rows": len(rows), "labeled": sum(r.get("renewed_next_period") is not None for r in rows),
            **count_by(rows, "source_system", SOURCES)}


def train(settings: Settings, storage: Storage) -> Summary:
    """Train the churn model on labelled STEMStar rows, compare it with two baselines, score every enrolment."""
    rows = storage.read(f"gold.{FEATURES_CHURN_TABLE}")
    if not rows:
        raise StageFailed(f"gold.{FEATURES_CHURN_TABLE} is empty")
    scores, metrics = train_and_score_churn(rows)
    check_no_pii(f"gold.{SCORES_CHURN_TABLE}", scores)
    storage.write(f"gold.{SCORES_CHURN_TABLE}", scores)
    storage.write("gold.model_metrics", [{"metric": k, "value": str(v)} for k, v in metrics.items()])
    keep = ("auc_model", "auc_logistic", "precision_at_decile_model", "precision_at_decile_dummy", "beats_baselines")
    return {key: metrics.get(key) for key in keep}


def reverse_etl(settings: Settings, storage: Storage) -> Summary:
    """Send each enrolment's churn score and risk band to the CRM, re-identified through the vault."""
    scores = storage.read(f"gold.{SCORES_CHURN_TABLE}")
    vault = storage.read("silver.identity_map")
    if not scores or not vault:
        raise StageFailed("scores or identity map are empty")
    rows, metrics = build_crm_scores_churn(scores, vault)
    check_no_pii(f"crm.{CRM_SCORES_TABLE}", rows, allowed_tokens=("student_token",))
    if not all(row.get("student_token") for row in rows):
        raise StageFailed("a CRM row has no student_token")
    storage.write(f"crm.{CRM_SCORES_TABLE}", rows)
    return {"rows": len(rows), **count_by(rows, "risk_band", ("high", "medium", "low")),
            "missing_from_vault": metrics.get("n_missing_from_vault")}


def observability(settings: Settings, storage: Storage) -> Summary:
    """Volume, freshness, null-rate, schema-drift and contract-rejection metrics for every observed table."""
    profiles = []
    for spec in OBSERVED_TABLES:
        rows = storage.read(spec.full_name) if storage.exists(spec.full_name) else None
        profiles.append(profile_from_rows(spec.layer, spec.table_name, rows, spec=spec))
    contracted = sum(p.row_count for p in profiles
                     if p.layer == "silver" and p.table_name in CONTRACTED_TABLES and p.present)
    metrics, summary = build_data_quality_metrics(profiles, contracted_row_count=contracted,
                                                  fill_missing_catalog=True,
                                                  expected_volumes=settings.expected_volumes)
    check_no_pii(f"gold.{DATA_QUALITY_TABLE}", metrics)
    storage.write(f"gold.{DATA_QUALITY_TABLE}", metrics)
    blocking = [m for m in metrics if m["over_threshold"] and m["blocking"]]
    if blocking:
        preview = "; ".join(f"{m['layer']}.{m['table_name']}:{m['metric']}={m['value']}" for m in blocking[:5])
        raise StageFailed(f"{len(blocking)} blocking data-quality metrics ({preview})")
    return {"metrics": summary["n_metrics"], "informational_breaches": summary["n_informational"]}


STAGES: dict[str, Callable[[Settings, Storage], Summary]] = {
    "bronze": bronze,
    "silver": silver,
    "kpi": kpi,
    "gold": gold,
    "features": features,
    "train": train,
    "reverse-etl": reverse_etl,
    "observability": observability,
}
