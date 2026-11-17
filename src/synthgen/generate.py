"""Orchestrate a BrainLab synthetic dataset to land in Bronze."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from synthgen.catalog import assert_catalog_invariants, programs, projects, rooms
from synthgen.constants import SCALE_PRESETS
from synthgen.logs import build_platform_logs
from synthgen.mess import apply_bronze_mess
from synthgen.operations import build_operations
from synthgen.people import build_people, load_overlap_tokens
from synthgen.validate import assert_dataset


def generate_dataset(
    *,
    seed: int = 42,
    scale: str = "small",
    apply_mess: bool = False,
    overlap_tokens_file: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Generate the synthetic tables. With apply_mess=False it validates integrity and absence of PII."""
    if scale not in SCALE_PRESETS:
        raise ValueError(
            f"Unknown scale {scale!r}. Expected one of {sorted(SCALE_PRESETS)}"
        )
    assert_catalog_invariants()
    preset = SCALE_PRESETS[scale]
    rng = random.Random(seed)
    overlap_tokens = load_overlap_tokens(overlap_tokens_file)
    people = build_people(rng, preset["n_students"], overlap_tokens)
    operations = build_operations(
        rng,
        people,
        l2_per_round=preset["l2_per_round"],
        skills_per_course=preset["skills_per_course"],
        l1_sessions_per_week=preset["l1_sessions_per_week"],
    )
    logs = build_platform_logs(
        rng,
        operations["attendance"],
        operations["sessions"],
        operations["enrolments"],
    )
    tables: dict[str, list[dict[str, Any]]] = {
        "programs": programs(),
        "projects": projects(),
        "rooms": rooms(),
        **people,
        **operations,
        "platform_logs": logs,
    }
    if apply_mess:
        tables = apply_bronze_mess(rng, tables)
    else:
        assert_dataset(tables)
    return tables
