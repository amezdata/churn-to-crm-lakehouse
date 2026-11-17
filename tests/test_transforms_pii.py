"""PII: forbidden columns are DROPped; HMAC tokens are not re-hashed."""

from pathlib import Path

from transforms.io import load_brainlab_synth
from transforms.pii import drop_forbidden_columns, identity_rows, tokens_unchanged
from transforms.silver_brainlab import build_silver_brainlab
from transforms.keys import attach_student_id

SYNTH_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "brainlab"


def test_forbidden_columns_are_dropped() -> None:
    rows = drop_forbidden_columns(
        [
            {
                "student_token": "aaaaaaaaaaaaaaaa",
                "name": "must not leak",
                "email": "x@y.z",
                "campus": "campus_03",
            }
        ]
    )
    assert "name" not in rows[0]
    assert "email" not in rows[0]
    assert rows[0]["student_token"] == "aaaaaaaaaaaaaaaa"
    assert rows[0]["campus"] == "campus_03"


def test_identity_vault_has_no_clear_pii() -> None:
    students = attach_student_id(
        [{"student_token": "aaaaaaaaaaaaaaaa", "source_system": "brainlab_csv"}]
    )
    vault = identity_rows(students, source_system="brainlab_csv")
    assert vault[0]["student_token"] == "aaaaaaaaaaaaaaaa"
    assert "name" not in vault[0]


def test_silver_does_not_rehash_student_tokens() -> None:
    bronze = load_brainlab_synth(SYNTH_DIR)
    silver, _violations = build_silver_brainlab(bronze)
    bronze_tokens = [row["student_token"] for row in bronze["students"]]
    silver_tokens = [row["student_token"] for row in silver["students"]]
    assert bronze_tokens == silver_tokens
    assert tokens_unchanged(bronze["students"], silver["students"])
