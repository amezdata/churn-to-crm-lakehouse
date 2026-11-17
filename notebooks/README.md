# Fabric notebook

[`nb_run_stages.py`](nb_run_stages.py) runs the pipeline in Microsoft Fabric. It holds no logic: it makes the
packages importable and calls the same stage functions as `python -m pipeline run` locally, with the
settings in [`config/fabric.yaml`](../config/fabric.yaml) and Delta tables instead of Parquet files.

## Setup

1. Upload `src/pipeline`, `src/transforms`, `src/contracts`, `src/synthgen`, `src/stemstar_synth`, `config/` and
   `contracts/` (as `contracts_yaml/`) to `Files/libs/` in the lakehouse.
2. Load Bronze with Data Factory copy jobs: the STEMStar Postgres silos (`supabase/01_silos.sql`, filled by
   `scripts/load_supabase.py`) to `bronze.stemstar_db_*`, and the BrainLab files to `bronze.brainlab_*`.
3. Attach the lakehouse to the notebook and run it, or call it from a Data Pipeline with the `stages` parameter
   (one activity per stage gives a retry point per layer).

## What each stage writes

| Stage | Reads | Writes |
|---|---|---|
| `silver` | `bronze.stemstar_db_*`, `bronze.brainlab_*` | `silver.stemstar_*`, `silver.brainlab_*`, `silver.identity_map*`, `silver.contract_violations` |
| `kpi` | `silver.stemstar_enrolments`, `silver.stemstar_absences`, legacy KPI in Bronze | `silver.kpi_reconciliation` |
| `gold` | Silver | `gold.dim_*`, `gold.fact_*` |
| `features` | Gold facts, `silver.stemstar_absences` | `gold.features_churn` |
| `train` | `gold.features_churn` | `gold.scores_churn`, `gold.model_metrics` (and an MLflow run) |
| `reverse-etl` | `gold.scores_churn`, `silver.identity_map` | `crm.scores_churn` |
| `observability` | every observed table | `gold.data_quality_metrics` |

A stage stops the run when a gate blocks: a failed data contract, a PII column in Gold or the CRM, or a
blocking data-quality metric.
