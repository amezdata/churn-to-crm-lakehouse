"""Stable surrogate keys; source tokens left intact."""

from transforms.keys import add_surrogate_keys, attach_student_id, surrogate_id


def test_same_token_yields_same_student_id() -> None:
    token = "fba82d8123596da3"
    first = attach_student_id([{"student_token": token, "campus": "campus_03"}])
    second = attach_student_id([{"student_token": token, "source_system": "stemstar_rdbms"}])
    assert first[0]["student_id"] == second[0]["student_id"]
    assert first[0]["student_token"] == token
    assert first[0]["student_id"] == surrogate_id("student_token", token)


def test_employee_gets_surrogate_id_without_touching_token() -> None:
    token = "73f60a08a1cca04b"
    rows = add_surrogate_keys("employees", [{"employee_token": token, "role": "educator"}])
    assert rows[0]["employee_token"] == token
    assert rows[0]["employee_id"] == surrogate_id("employee_token", token)
    assert isinstance(rows[0]["employee_id"], int)
    assert rows[0]["employee_id"] > 0


def test_existing_oltp_enrolment_id_is_kept() -> None:
    rows = add_surrogate_keys(
        "stemstar_enrolments",
        [{"enrolment_id": 42, "student_token": "aaaaaaaaaaaaaaaa"}],
    )
    assert rows[0]["enrolment_id"] == 42
