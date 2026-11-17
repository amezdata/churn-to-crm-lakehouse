"""Command line: `pipeline run`, `pipeline list-stages`, `pipeline report`."""

from __future__ import annotations

import argparse
import sys
import time

from pipeline.config import load_settings
from pipeline.stages import STAGES, StageFailed
from pipeline.storage import open_storage


def select_stages(names: str | None = None, start: str | None = None, stop: str | None = None) -> list[str]:
    """`names` is a comma-separated list; `start`/`stop` slice the run order. Default: every stage."""
    order = list(STAGES)
    if names:
        chosen = [name.strip() for name in names.split(",") if name.strip()]
        unknown = [name for name in chosen if name not in STAGES]
        if unknown:
            raise SystemExit(f"unknown stage(s) {unknown}; choose from {order}")
        return [name for name in order if name in chosen]
    for name in (start, stop):
        if name and name not in STAGES:
            raise SystemExit(f"unknown stage {name!r}; choose from {order}")
    first = order.index(start) if start else 0
    last = order.index(stop) if stop else len(order) - 1
    return order[first:last + 1]


def run(settings, stages: list[str], storage=None) -> bool:
    storage = storage or open_storage(settings)
    print(f"env={settings.env} storage={settings.storage} stages={','.join(stages)}")
    for name in stages:
        started = time.perf_counter()
        try:
            summary = STAGES[name](settings, storage)
        except StageFailed as error:
            print(f"  {name:<14} FAILED  {error}")
            return False
        details = " ".join(f"{key}={value}" for key, value in summary.items())
        print(f"  {name:<14} {time.perf_counter() - started:5.1f}s  {details}")
    return True


def report(settings) -> None:
    """Headline results, queried with DuckDB straight from the local Parquet lakehouse."""
    import duckdb

    root = settings.lakehouse_dir

    def query(sql: str):
        return duckdb.sql(sql.replace("@", str(root).replace("\\", "/") + "/")).fetchall()

    total, within = query("select count(*), count(*) filter (where within_threshold) "
                          "from '@silver/kpi_reconciliation.parquet'")[0]
    print(f"KPI reconciliation: {within} of {total} course-years within {settings.kpi_tolerance_pct}%")
    for year, course, lake, legacy in query(
            "select academic_year, course, renewals_lakehouse, renewals_rdbms "
            "from '@silver/kpi_reconciliation.parquet' where not within_threshold order by 1, 2"):
        print(f"  off: {year} {course}: lakehouse {lake:.0f} renewals, legacy table {legacy:.0f}")
    metrics = dict(query("select metric, value from '@gold/model_metrics.parquet'"))
    print("Churn model (test set):")
    for name in ("auc_model", "auc_logistic", "auc_dummy", "precision_at_decile_model",
                 "precision_at_decile_logistic", "precision_at_decile_dummy", "beats_baselines"):
        print(f"  {name:<30} {metrics.get(name)}")
    bands = query("select risk_band, count(*) from '@crm/scores_churn.parquet' group by 1 order by 2")
    print("CRM risk bands: " + ", ".join(f"{band} {n}" for band, n in bands))
    flagged = query("select count(*) filter (where over_threshold), count(*) filter (where over_threshold and blocking), "
                    "count(*) from '@gold/data_quality_metrics.parquet'")[0]
    print(f"Data quality: {flagged[2]} metrics, {flagged[0]} over threshold, {flagged[1]} blocking")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pipeline", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="run the stages in order")
    run_parser.add_argument("--stages", help="comma-separated subset, e.g. gold,features,train")
    run_parser.add_argument("--from", dest="start", help="first stage to run")
    run_parser.add_argument("--to", dest="stop", help="last stage to run")
    run_parser.add_argument("--seed", type=int, help="seed for the synthetic STEMStar extracts")
    commands.add_parser("list-stages", help="print the stages in run order")
    commands.add_parser("report", help="print the headline results of the last local run")
    for sub in commands.choices.values():
        sub.add_argument("--env", help="config/<env>.yaml to use (default: PIPELINE_ENV or local)")
    args = parser.parse_args(argv)

    if args.command == "list-stages":
        for name, stage in STAGES.items():
            print(f"{name:<14} {stage.__doc__.splitlines()[0]}")
        return
    overrides = {"seed": args.seed} if getattr(args, "seed", None) is not None else {}
    settings = load_settings(args.env, overrides)
    if args.command == "report":
        report(settings)
        return
    if not run(settings, select_stages(args.stages, args.start, args.stop)):
        sys.exit(1)


if __name__ == "__main__":
    main()
