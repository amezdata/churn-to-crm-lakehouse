"""Offerings, enrolments, payments, class sessions, attendance and occupancy."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any

from synthgen.catalog import (
    time_slot_label,
    iter_open_dates,
    l1_projects,
    l1_teaching_slots,
    l2_teaching_slot,
    month_end,
    skills_projects,
    skills_teaching_slot,
    term_for_date,
)
from synthgen.constants import (
    ATTENDANCE_LATE,
    ATTENDANCE_PRESENT,
    ATTENDANCE_STATUSES,
    ATTENDANCE_WEIGHTS,
    CAMPUS_CODE,
    CURRENCY_CODE,
    L2_RENEWAL_RATE,
    L2_ROUND_CAPACITY,
    L2_ROUNDS,
    ENROLMENT_STATUS_ACTIVE,
    ENROLMENT_STATUS_COMPLETED,
    ENROLMENT_STATUS_WITHDRAWN,
    LIST_PRICE_L1,
    LIST_PRICE_L2,
    LIST_PRICE_SKILLS,
    PAYMENT_METHOD_WEIGHTS,
    PAYMENT_METHODS,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PARTIAL,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_REFUNDED,
    SESSION_STATUS_CANCELLED,
    SESSION_STATUS_HELD,
    SESSION_STATUS_SCHEDULED,
    SESSION_STATUSES,
    SKILLS_COURSE_CAPACITY,
    SKILLS_LAUNCH_MONTHS,
    SOURCE_SYSTEM,
    TERM_AUTUMN,
    TERM_WINDOWS,
    WITHDRAWN_RATE,
)
from synthgen.tokens import make_token


def build_operations(
    rng: random.Random,
    people: dict[str, list[dict[str, Any]]],
    *,
    l2_per_round: int,
    skills_per_course: int,
    l1_sessions_per_week: int,
) -> dict[str, list[dict[str, Any]]]:
    """Build the operating core from the catalog and the people."""
    assert 1 <= l2_per_round <= L2_ROUND_CAPACITY, "l2_per_round exceeds the round capacity"
    assert 1 <= skills_per_course <= SKILLS_COURSE_CAPACITY, "skills_per_course exceeds the course capacity"
    employees = people["employees"]
    students = people["students"]
    offerings = _build_offerings(employees)
    enrolments = _build_enrolments(
        rng, students, offerings, l2_per_round, skills_per_course
    )
    payments = _build_payments(rng, enrolments)
    sessions = _build_sessions(rng, offerings, employees, l1_sessions_per_week)
    attendance = _build_attendance(rng, enrolments, sessions)
    occupancy = _build_occupancy(sessions, attendance)
    return {
        "offerings": offerings,
        "enrolments": enrolments,
        "payments": payments,
        "sessions": sessions,
        "attendance": attendance,
        "occupancy": occupancy,
    }


def _build_offerings(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    offerings: list[dict[str, Any]] = []
    coach_keys = [row["employee_natural_key"] for row in employees]

    for project in l1_projects():
        for term_name, (start, end) in TERM_WINDOWS.items():
            offerings.append(
                _offering(
                    program_key="prg_level_1",
                    project_id=project["project_id"],
                    term_name=term_name,
                    start=start,
                    end=end,
                    price=LIST_PRICE_L1 * project["sessions_needed"],
                    capacity=24,
                    room_key="room_platform_hall",
                    educator_key=coach_keys[0],
                    schedule="open_wednesday_to_sunday",
                )
            )

    for index, (launch, project_id, delivery_end) in enumerate(L2_ROUNDS):
        offerings.append(
            _offering(
                program_key="prg_level_2",
                project_id=project_id,
                term_name=term_for_date(launch),
                start=launch,
                end=delivery_end,
                price=LIST_PRICE_L2,
                capacity=L2_ROUND_CAPACITY,
                room_key="room_studio_2",
                educator_key=coach_keys[index % len(coach_keys)],
                schedule="fixed_weekend_morning",
                extra={"round_index": index + 1, "launch_month": launch.isoformat()},
            )
        )

    for index, (launch, project) in enumerate(zip(SKILLS_LAUNCH_MONTHS, skills_projects())):
        offerings.append(
            _offering(
                program_key="prg_skills",
                project_id=project["project_id"],
                term_name=term_for_date(launch),
                start=launch,
                end=month_end(launch),
                price=LIST_PRICE_SKILLS,
                capacity=SKILLS_COURSE_CAPACITY,
                room_key="room_studio_1",
                educator_key=coach_keys[(index + 1) % len(coach_keys)],
                schedule="weekend_afternoon_or_weekday",
            )
        )
    return offerings


def _offering(
    *,
    program_key: str,
    project_id: str,
    term_name: str,
    start: date,
    end: date,
    price: float,
    capacity: int,
    room_key: str,
    educator_key: str,
    schedule: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    natural_key = f"off_{program_key}_{project_id}_{start.isoformat()}"
    row = {
        "offering_natural_key": natural_key,
        "program_natural_key": program_key,
        "project_id": project_id,
        "campus": CAMPUS_CODE,
        "term": term_name,
        "term_start_date": start.isoformat(),
        "term_end_date": end.isoformat(),
        "schedule": schedule,
        "list_price": f"{price:.2f}",
        "currency": CURRENCY_CODE,
        "capacity": capacity,
        "lead_educator_natural_key": educator_key,
        "default_room_natural_key": room_key,
        "offering_status": "in_progress",
        "source_system": SOURCE_SYSTEM,
    }
    if extra:
        row.update(extra)
    return row


def _build_enrolments(
    rng: random.Random,
    students: list[dict[str, Any]],
    offerings: list[dict[str, Any]],
    l2_per_round: int,
    skills_per_course: int,
) -> list[dict[str, Any]]:
    by_program: dict[str, list[dict[str, Any]]] = {"prg_level_1": [], "prg_level_2": [], "prg_skills": []}
    for offering in offerings:
        by_program[offering["program_natural_key"]].append(offering)

    pool = list(students)
    rng.shuffle(pool)
    enrolments: list[dict[str, Any]] = []

    l1_targets = by_program["prg_level_1"]
    autumn_l1 = [row for row in l1_targets if row["term"] == TERM_AUTUMN]
    later_l1 = [row for row in l1_targets if row["term"] != TERM_AUTUMN]
    for index, student in enumerate(pool):
        first_offering = autumn_l1[index % len(autumn_l1)]
        first = _enrolment(rng, student, first_offering, is_renewal=False, previous_key="")
        enrolments.append(first)
        if rng.random() < 0.28 and later_l1:
            second_offering = later_l1[index % len(later_l1)]
            enrolments.append(
                _enrolment(
                    rng,
                    student,
                    second_offering,
                    is_renewal=True,
                    previous_key=first["enrolment_natural_key"],
                )
            )

    l2_offerings = by_program["prg_level_2"]
    p1 = [row for row in l2_offerings if row["project_id"] == "l2_project_1"]
    p2 = [row for row in l2_offerings if row["project_id"] == "l2_project_2"]
    assigned_p1: dict[str, list[dict[str, Any]]] = {row["offering_natural_key"]: [] for row in p1}
    for offering in p1:
        chosen = rng.sample(pool, k=min(l2_per_round, len(pool)))
        assigned_p1[offering["offering_natural_key"]] = chosen
        for student in chosen:
            enrolments.append(_enrolment(rng, student, offering, is_renewal=False, previous_key=""))

    p1_by_student: dict[str, str] = {}
    for offering in p1:
        for student in assigned_p1[offering["offering_natural_key"]]:
            match = [
                row
                for row in enrolments
                if row["student_natural_key"] == student["student_natural_key"]
                and row["offering_natural_key"] == offering["offering_natural_key"]
            ]
            if match:
                p1_by_student[student["student_natural_key"]] = match[0]["enrolment_natural_key"]

    p1_students = [student for chosen in assigned_p1.values() for student in chosen]
    rng.shuffle(p1_students)
    renew_count = int(round(len(p1_students) * L2_RENEWAL_RATE))
    for offering in p2:
        renewals = [student for student in p1_students[:renew_count] if student in p1_students]
        newcomers_pool = [student for student in pool if student not in renewals]
        need = min(l2_per_round, len(renewals) + len(newcomers_pool))
        selected = renewals[: max(0, need // 2)]
        selected += rng.sample(newcomers_pool, k=min(need - len(selected), len(newcomers_pool)))
        selected = selected[:l2_per_round]
        for student in selected:
            previous = p1_by_student.get(student["student_natural_key"], "")
            enrolments.append(
                _enrolment(
                    rng,
                    student,
                    offering,
                    is_renewal=bool(previous),
                    previous_key=previous,
                )
            )

    for offering in by_program["prg_skills"]:
        chosen = rng.sample(pool, k=min(skills_per_course, len(pool)))
        for student in chosen:
            enrolments.append(_enrolment(rng, student, offering, is_renewal=False, previous_key=""))

    unique: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for row in enrolments:
        pair = (row["student_natural_key"], row["offering_natural_key"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        unique.append(row)
    return unique


def _enrolment(
    rng: random.Random,
    student: dict[str, Any],
    offering: dict[str, Any],
    *,
    is_renewal: bool,
    previous_key: str,
) -> dict[str, Any]:
    start = date.fromisoformat(offering["term_start_date"])
    enrolment_date = start - timedelta(days=rng.randint(1, 14))
    withdrawn = rng.random() < WITHDRAWN_RATE
    status = (
        ENROLMENT_STATUS_WITHDRAWN
        if withdrawn
        else (
            ENROLMENT_STATUS_COMPLETED
            if offering["term"] == TERM_AUTUMN
            else ENROLMENT_STATUS_ACTIVE
        )
    )
    discount = 0.0 if rng.random() > 0.18 else round(float(offering["list_price"]) * 0.10, 2)
    price_paid = max(0.0, float(offering["list_price"]) - discount)
    return {
        "enrolment_natural_key": make_token(
            "enrolment", student["student_natural_key"], offering["offering_natural_key"]
        ),
        "student_natural_key": student["student_natural_key"],
        "guardian_natural_key": student["guardian_natural_key"],
        "offering_natural_key": offering["offering_natural_key"],
        "program_natural_key": offering["program_natural_key"],
        "project_id": offering["project_id"],
        "campus": CAMPUS_CODE,
        "enrolment_date": enrolment_date.isoformat(),
        "term": offering["term"],
        "price_paid": f"{price_paid:.2f}",
        "discount": f"{discount:.2f}",
        "currency": CURRENCY_CODE,
        "enrolment_status": status,
        "is_renewal": is_renewal,
        "previous_enrolment_natural_key": previous_key,
        "start_date": offering["term_start_date"],
        "end_date": offering["term_end_date"],
        "source_system": SOURCE_SYSTEM,
    }


def _build_payments(
    rng: random.Random, enrolments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    payments: list[dict[str, Any]] = []
    for enrolment in enrolments:
        if enrolment["enrolment_status"] == ENROLMENT_STATUS_WITHDRAWN and rng.random() < 0.45:
            status = PAYMENT_STATUS_REFUNDED
        elif rng.random() < 0.06:
            status = PAYMENT_STATUS_PENDING
        elif rng.random() < 0.05:
            status = PAYMENT_STATUS_PARTIAL
        else:
            status = PAYMENT_STATUS_PAID
        pay_date = date.fromisoformat(enrolment["enrolment_date"]) + timedelta(days=rng.randint(0, 10))
        payments.append(
            {
                "payment_natural_key": make_token("payment", enrolment["enrolment_natural_key"]),
                "enrolment_natural_key": enrolment["enrolment_natural_key"],
                "guardian_natural_key": enrolment["guardian_natural_key"],
                "amount": enrolment["price_paid"],
                "currency": CURRENCY_CODE,
                "payment_date": pay_date.isoformat(),
                "payment_method": rng.choices(
                    PAYMENT_METHODS, weights=PAYMENT_METHOD_WEIGHTS, k=1
                )[0],
                "payment_status": status,
                "invoice_token": make_token("invoice", enrolment["enrolment_natural_key"]),
                "installment_no": 1 if status != PAYMENT_STATUS_PARTIAL else 1,
                "source_system": SOURCE_SYSTEM,
            }
        )
    return payments


def _build_sessions(
    rng: random.Random,
    offerings: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    l1_sessions_per_week: int,
) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    coaches = [row["employee_natural_key"] for row in employees]
    l1_by_term: dict[str, list[dict[str, Any]]] = {}
    for offering in offerings:
        if offering["program_natural_key"] == "prg_level_1":
            l1_by_term.setdefault(offering["term"], []).append(offering)
    for term_offerings in l1_by_term.values():
        start = date.fromisoformat(term_offerings[0]["term_start_date"])
        end = date.fromisoformat(term_offerings[0]["term_end_date"])
        picked = _thin_l1_dates(iter_open_dates(start, end), l1_sessions_per_week)
        rotate_index = 0
        for session_date in picked:
            for turn_index, (start_clock, end_clock) in enumerate(l1_teaching_slots(session_date)):
                offering = term_offerings[rotate_index % len(term_offerings)]
                rotate_index += 1
                sessions.append(
                    _session(
                        offering,
                        session_date,
                        start_clock,
                        end_clock,
                        offering["default_room_natural_key"],
                        coaches[turn_index % len(coaches)],
                        phase=1,
                    )
                )

    for offering in offerings:
        start = date.fromisoformat(offering["term_start_date"])
        end = date.fromisoformat(offering["term_end_date"])
        open_dates = iter_open_dates(start, end)
        program = offering["program_natural_key"]
        if program == "prg_level_1":
            continue
        if program == "prg_level_2":
            weekend_dates = [value for value in open_dates if value.weekday() == 5]
            for session_date in weekend_dates:
                slot = l2_teaching_slot(session_date)
                if slot is None:
                    continue
                sessions.append(
                    _session(
                        offering,
                        session_date,
                        slot[0],
                        slot[1],
                        offering["default_room_natural_key"],
                        offering["lead_educator_natural_key"],
                        phase=1,
                    )
                )
        else:
            candidate_dates = [
                value for value in open_dates if skills_teaching_slot(value) is not None
            ]
            picked = candidate_dates[:6]
            for session_date in picked:
                slot = skills_teaching_slot(session_date)
                assert slot is not None
                sessions.append(
                    _session(
                        offering,
                        session_date,
                        slot[0],
                        slot[1],
                        offering["default_room_natural_key"],
                        offering["lead_educator_natural_key"],
                        phase=None,
                    )
                )
    assert sessions
    _ = rng  # reserved for future jitter of cancelled sessions
    cancelled = 0
    for row in sessions:
        if cancelled < max(1, len(sessions) // 40) and row["program_natural_key"] == "prg_level_1":
            row["session_status"] = SESSION_STATUS_CANCELLED
            cancelled += 1
        else:
            row["session_status"] = (
                SESSION_STATUS_HELD
                if date.fromisoformat(row["session_date"]) < date(2026, 12, 1)
                else SESSION_STATUS_SCHEDULED
            )
    assert set(row["session_status"] for row in sessions) <= set(SESSION_STATUSES)
    return sessions


def _thin_l1_dates(open_dates: list[date], sessions_per_week: int) -> list[date]:
    by_week: dict[tuple[int, int], list[date]] = {}
    for value in open_dates:
        iso = value.isocalendar()
        by_week.setdefault((iso.year, iso.week), []).append(value)
    picked: list[date] = []
    for week_dates in by_week.values():
        take = min(sessions_per_week, len(week_dates))
        picked.extend(week_dates[:take])
    return picked


def _session(
    offering: dict[str, Any],
    session_date: date,
    start_clock: str,
    end_clock: str,
    room_key: str,
    educator_key: str,
    phase: int | None,
) -> dict[str, Any]:
    natural_key = make_token(
        "session", offering["offering_natural_key"], session_date.isoformat(), start_clock
    )
    return {
        "session_natural_key": natural_key,
        "offering_natural_key": offering["offering_natural_key"],
        "program_natural_key": offering["program_natural_key"],
        "project_id": offering["project_id"],
        "campus": CAMPUS_CODE,
        "session_date": session_date.isoformat(),
        "start_time": start_clock,
        "end_time": end_clock,
        "time_slot": time_slot_label(session_date, start_clock),
        "room_natural_key": room_key,
        "educator_natural_key": educator_key,
        "session_status": SESSION_STATUS_SCHEDULED,
        "topic": offering["project_id"],
        "phase": phase if phase is not None else "",
        "source_system": SOURCE_SYSTEM,
    }


def _build_attendance(
    rng: random.Random,
    enrolments: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sessions_by_offering: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        if session["session_status"] == SESSION_STATUS_CANCELLED:
            continue
        sessions_by_offering.setdefault(session["offering_natural_key"], []).append(session)

    project_visits = {row["project_id"]: row["sessions_needed"] for row in l1_projects()}
    attendance: list[dict[str, Any]] = []
    for enrolment in enrolments:
        if enrolment["enrolment_status"] == ENROLMENT_STATUS_WITHDRAWN:
            continue
        offering_sessions = sessions_by_offering.get(enrolment["offering_natural_key"], [])
        if not offering_sessions:
            continue
        if enrolment["program_natural_key"] == "prg_level_1":
            visits = project_visits.get(enrolment["project_id"], 2)
            chosen = offering_sessions[:visits]
        else:
            chosen = offering_sessions
        for session in chosen:
            status = rng.choices(ATTENDANCE_STATUSES, weights=ATTENDANCE_WEIGHTS, k=1)[0]
            check_in = ""
            if status in {ATTENDANCE_PRESENT, ATTENDANCE_LATE}:
                start = datetime.fromisoformat(
                    f"{session['session_date']}T{session['start_time']}:00"
                )
                delay = 0 if status == ATTENDANCE_PRESENT else rng.randint(6, 18)
                check_in = (start + timedelta(minutes=delay)).isoformat(timespec="seconds")
            attendance.append(
                {
                    "attendance_natural_key": make_token(
                        "attendance",
                        enrolment["enrolment_natural_key"],
                        session["session_natural_key"],
                    ),
                    "session_natural_key": session["session_natural_key"],
                    "student_natural_key": enrolment["student_natural_key"],
                    "enrolment_natural_key": enrolment["enrolment_natural_key"],
                    "status": status,
                    "time_slot": session["time_slot"],
                    "check_in_time": check_in,
                    "recorded_by_natural_key": session["educator_natural_key"],
                    "source_system": SOURCE_SYSTEM,
                }
            )
    return attendance


def _build_occupancy(
    sessions: list[dict[str, Any]],
    attendance: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    present_by_session: dict[str, int] = {}
    for row in attendance:
        if row["status"] in {ATTENDANCE_PRESENT, ATTENDANCE_LATE}:
            present_by_session[row["session_natural_key"]] = (
                present_by_session.get(row["session_natural_key"], 0) + 1
            )
    room_capacity = {
        "room_platform_hall": 24,
        "room_studio_1": 12,
        "room_studio_2": 12,
        "room_studio_3": 12,
        "room_demo_stage": 40,
        "room_machinery": 8,
        "room_workshop": 16,
        "room_office": 4,
    }
    occupancy: list[dict[str, Any]] = []
    for session in sessions:
        if session["session_status"] == SESSION_STATUS_CANCELLED:
            continue
        headcount = present_by_session.get(session["session_natural_key"], 0)
        capacity = room_capacity[session["room_natural_key"]]
        occupancy.append(
            {
                "occupancy_natural_key": make_token("occupancy", session["session_natural_key"]),
                "room_natural_key": session["room_natural_key"],
                "campus": CAMPUS_CODE,
                "occupancy_date": session["session_date"],
                "start_time": session["start_time"],
                "end_time": session["end_time"],
                "time_slot": session["time_slot"],
                "occupancy_source": "session",
                "session_natural_key": session["session_natural_key"],
                "headcount": headcount,
                "capacity": capacity,
                "source_system": SOURCE_SYSTEM,
            }
        )
    return occupancy
