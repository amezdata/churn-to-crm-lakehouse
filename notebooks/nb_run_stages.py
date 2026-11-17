"""Fabric notebook: run pipeline stages against the attached lakehouse.

All logic lives in the `pipeline` package; this notebook only makes it importable and calls it.
A Fabric Data Pipeline runs it once per stage (or once for all), passing `stages` as a parameter.
"""

# Parameters cell (Fabric "Toggle parameter cell"): overridden by the Data Pipeline activity.
stages = "silver,kpi,gold,features,train,reverse-etl,observability"
log_to_mlflow = True

# OneLake does not put Files/ on sys.path: copy the versioned packages (uploaded to Files/libs) locally.
import sys

from notebookutils import mssparkutils

LIBS = "/tmp/pipeline_libs"
for name in ("pipeline", "transforms", "contracts", "synthgen", "stemstar_synth", "config", "contracts_yaml"):
    mssparkutils.fs.cp(f"Files/libs/{name}", f"file:{LIBS}/{name}", True)
sys.path.insert(0, LIBS)

from pipeline.fabric import log_model_to_mlflow, run_in_fabric

selected = [name.strip() for name in stages.split(",") if name.strip()]
run_in_fabric(spark, *selected)  # noqa: F821  (`spark` is provided by the Fabric runtime)
if log_to_mlflow and "train" in selected:
    log_model_to_mlflow(spark)  # noqa: F821
