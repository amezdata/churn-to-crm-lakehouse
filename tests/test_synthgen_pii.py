"""Data minimization tests: the generator emits no clear-text PII."""

from synthgen.generate import generate_dataset
from synthgen.tokens import TOKEN_PATTERN
from synthgen.validate import collect_pii_errors


def test_clean_and_messy_outputs_have_no_direct_pii() -> None:
    clean = generate_dataset(seed=42, scale="small", apply_mess=False)
    messy = generate_dataset(seed=42, scale="small", apply_mess=True)
    assert collect_pii_errors(clean) == []
    assert collect_pii_errors(messy) == []


def test_identity_fields_are_tokens_not_names() -> None:
    tables = generate_dataset(seed=99, scale="small", apply_mess=False)
    for row in tables["students"]:
        assert TOKEN_PATTERN.fullmatch(row["student_natural_key"])
        assert TOKEN_PATTERN.fullmatch(row["guardian_natural_key"])
    for row in tables["employees"]:
        assert TOKEN_PATTERN.fullmatch(row["employee_natural_key"])
    for row in tables["guardians"]:
        assert TOKEN_PATTERN.fullmatch(row["contact_token"])
        assert "@" not in row["contact_token"]


def test_leads_do_not_carry_contact_channels_in_clear() -> None:
    tables = generate_dataset(seed=42, scale="small", apply_mess=False)
    for row in tables["leads"]:
        assert "contact_name" not in row
        assert "contact_email" not in row
        assert "contact_phone" not in row
