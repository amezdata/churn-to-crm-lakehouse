"""Quality gates: messy Bronze fails; conformed Silver passes."""

from pathlib import Path

from contracts.gate import evaluate_contracts
from contracts.loader import default_contracts_dir
from transforms.conform import conform_rows
from transforms.io import load_brainlab_synth
from transforms.silver_brainlab import build_silver_brainlab

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTH_DIR = REPO_ROOT / "data" / "synthetic" / "brainlab"
CONTRACTS_DIR = default_contracts_dir()


def test_messy_attendance_fails_allowed_values() -> None:
    bronze = load_brainlab_synth(SYNTH_DIR)
    violations = evaluate_contracts(
        {
            "enrolments": bronze["enrolments"],
            "attendance": bronze["attendance"],
            "sessions": bronze["sessions"],
            "platform_logs": bronze["platform_logs"],
        },
        CONTRACTS_DIR,
    )
    attendance_values = [
        item for item in violations if item.rule == "allowed_values" and item.column == "attendance_status"
    ]
    assert attendance_values


def test_conformed_attendance_passes_allowed_values() -> None:
    bronze = load_brainlab_synth(SYNTH_DIR)
    attendance = conform_rows("attendance", bronze["attendance"])
    violations = evaluate_contracts(
        {
            "enrolments": bronze["enrolments"],
            "attendance": attendance,
            "sessions": bronze["sessions"],
            "platform_logs": bronze["platform_logs"],
        },
        CONTRACTS_DIR,
    )
    attendance_values = [
        item for item in violations if item.rule == "allowed_values" and item.column == "attendance_status"
    ]
    assert attendance_values == []


def test_silver_brainlab_synth_passes_contracts() -> None:
    bronze = load_brainlab_synth(SYNTH_DIR)
    _silver, violations = build_silver_brainlab(bronze, CONTRACTS_DIR)
    blocking = [item for item in violations if item.blocking]
    assert blocking == [], "; ".join(item.message for item in blocking[:8])
