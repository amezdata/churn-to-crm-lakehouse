"""Entry point for the Fabric notebooks: run stages against the attached lakehouse with the `fabric` settings."""

from __future__ import annotations

from pipeline.cli import run
from pipeline.config import load_settings
from pipeline.storage import SparkStorage


def run_in_fabric(spark, *stages: str) -> None:
    settings = load_settings("fabric")
    if not run(settings, list(stages), storage=SparkStorage(spark)):
        raise SystemExit(f"stage failed: {', '.join(stages)}")


def log_model_to_mlflow(spark, experiment: str = "churn_model") -> None:
    """Log the metrics the train stage wrote to gold.model_metrics. Skipped when MLflow is unavailable."""
    try:
        import mlflow
    except ImportError:
        print("mlflow_skip: not installed")
        return
    rows = SparkStorage(spark).read("gold.model_metrics")
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name="hgb_vs_logistic_dummy"):
        mlflow.log_param("estimator", "HistGradientBoostingClassifier")
        mlflow.log_param("baselines", "LogisticRegression, DummyClassifier(most_frequent)")
        for row in rows:
            try:
                mlflow.log_metric(row["metric"], float(row["value"]))
            except (TypeError, ValueError):
                mlflow.log_param(row["metric"], row["value"])
