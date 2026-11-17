"""Settings per environment: `config/<env>.yaml`, overridable with PIPELINE_* environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = "local"


def config_dir() -> Path:
    """`config/` in the repo, or next to the packages when they are copied to Fabric (`Files/libs/config`)."""
    for candidate in (PROJECT_ROOT / "config", Path(__file__).resolve().parents[1] / "config"):
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("config/ directory not found")


@dataclass(frozen=True)
class Settings:
    env: str
    storage: str                       # "local" (Parquet files) or "spark" (Delta tables in Fabric)
    lakehouse_dir: Path                # local storage root; unused on Spark
    brainlab_source: Path              # synthetic BrainLab CSV/JSONL (local Bronze)
    stemstar_source: Path              # STEMStar extracts, .csv or .xlsx (local Bronze)
    generate_stemstar: bool            # create synthetic STEMStar extracts when the folder is empty
    contracts_dir: Path
    seed: int = 42
    kpi_tolerance_pct: float = 1.0     # max deviation between lakehouse and legacy KPI
    expected_volumes: dict[str, int] = field(default_factory=dict)  # "layer.table" -> rows; drives volume gates


def load_settings(env: str | None = None, overrides: dict[str, Any] | None = None) -> Settings:
    """Read `config/<env>.yaml`, then apply PIPELINE_<FIELD> environment variables, then `overrides`."""
    env = env or os.environ.get("PIPELINE_ENV", DEFAULT_ENV)
    path = config_dir() / f"{env}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no config for environment {env!r}: {path}")
    values: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    values["env"] = env
    for item in fields(Settings):
        variable = f"PIPELINE_{item.name.upper()}"
        if variable in os.environ and item.name not in {"env", "expected_volumes"}:
            values[item.name] = os.environ[variable]
    values.update(overrides or {})
    return _typed(values)


def _typed(values: dict[str, Any]) -> Settings:
    def path(key: str) -> Path:
        candidate = Path(str(values[key]))
        return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate

    generate = values.get("generate_stemstar", False)
    return Settings(
        env=str(values["env"]),
        storage=str(values["storage"]),
        lakehouse_dir=path("lakehouse_dir"),
        brainlab_source=path("brainlab_source"),
        stemstar_source=path("stemstar_source"),
        generate_stemstar=generate if isinstance(generate, bool) else str(generate).lower() == "true",
        contracts_dir=path("contracts_dir"),
        seed=int(values.get("seed", 42)),
        kpi_tolerance_pct=float(values.get("kpi_tolerance_pct", 1.0)),
        expected_volumes={str(k): int(v) for k, v in (values.get("expected_volumes") or {}).items()},
    )
