"""Loads the data contract YAML files versioned in Git."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONTRACT_FILES = (
    "brainlab_enrolment.yaml",
    "brainlab_attendance.yaml",
    "brainlab_platform_logs.yaml",
)


def default_contracts_dir() -> Path:
    """YAML directory: the repo, Files/libs in Fabric, or the local copy /tmp/pipeline_libs."""
    here = Path(__file__).resolve()
    candidates = (
        here.parents[2] / "contracts",
        here.parents[1] / "contracts_yaml",
        Path("/tmp/pipeline_libs/contracts_yaml"),
        Path("/lakehouse/default/Files/libs/contracts_yaml"),
        Path("/lakehouse/default/Files/contracts"),
        Path.cwd() / "contracts",
    )
    for path in candidates:
        if (path / "brainlab_enrolment.yaml").is_file():
            return path
    raise FileNotFoundError(
        "Contract YAML files not found in contracts/ or in Files/libs/contracts_yaml."
    )


def load_contract(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "contract" not in raw:
        raise ValueError(f"YAML has no contract key: {path}")
    spec = raw["contract"]
    if not isinstance(spec, dict) or "name" not in spec:
        raise ValueError(f"Contract has no name: {path}")
    return spec


def load_contracts(contracts_dir: Path | None = None) -> list[dict[str, Any]]:
    directory = contracts_dir or default_contracts_dir()
    specs: list[dict[str, Any]] = []
    for filename in CONTRACT_FILES:
        path = directory / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing contract {path}")
        specs.append(load_contract(path))
    return specs
