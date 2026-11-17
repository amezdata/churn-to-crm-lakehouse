"""Static BrainLab catalog: rooms, programs, projects, coaches and calendar."""

from __future__ import annotations

import math
from calendar import monthrange
from datetime import date, time, timedelta
from typing import Any

from synthgen.constants import (
    BRANCH_TYPE,
    CAMPUS_CODE,
    COACH_COUNT,
    GRADE_MAX,
    GRADE_MIN,
    L1_BLOCK_HOURS,
    L1_DEDICATED_SEATS,
    L2_FIXED_WINDOW,
    L2_ROUND_CAPACITY,
    L2_ROUNDS,
    L2_SKILLS_RESERVED_SEATS,
    LAUNCH_YEAR_END,
    LAUNCH_YEAR_START,
    OPEN_WEEKDAYS,
    PROJECT_HOURS_MAX,
    PROJECT_HOURS_MIN,
    SKILLS_COURSE_CAPACITY,
    SKILLS_LAUNCH_MONTHS,
    SKILLS_WEEKDAY_WINDOW,
    SKILLS_WEEKEND_WINDOW,
    SOURCE_SYSTEM,
    TERM_AUTUMN,
    TERM_SPRING,
    TERM_WINDOWS,
    WEEKDAY_TEACHING,
    WEEKEND_L1_TURNS,
)
from synthgen.tokens import make_token


def programs() -> list[dict[str, Any]]:
    return [
        {
            "program_natural_key": "prg_level_1",
            "program_name": "Level 1 projects",
            "program_family": "brainlab",
            "domain": "ai",
            "target_grade_min": GRADE_MIN,
            "target_grade_max": GRADE_MAX,
            "has_phase_model": True,
            "default_session_count": 3,
            "unit_sold": "open_project_session",
            "is_active": True,
        },
        {
            "program_natural_key": "prg_level_2",
            "program_name": "Level 2 programs",
            "program_family": "brainlab",
            "domain": "ai",
            "target_grade_min": GRADE_MIN,
            "target_grade_max": GRADE_MAX,
            "has_phase_model": True,
            "default_session_count": 12,
            "unit_sold": "monthly_round",
            "is_active": True,
        },
        {
            "program_natural_key": "prg_skills",
            "program_name": "Skills courses",
            "program_family": "brainlab",
            "domain": "ai",
            "target_grade_min": GRADE_MIN,
            "target_grade_max": GRADE_MAX,
            "has_phase_model": False,
            "default_session_count": 6,
            "unit_sold": "course",
            "is_active": True,
        },
    ]


def rooms() -> list[dict[str, Any]]:
    return [
        {
            "room_natural_key": "room_platform_hall",
            "campus": CAMPUS_CODE,
            "room_name": "Platform hall",
            "room_type": "open_space",
            "capacity": L1_DEDICATED_SEATS,
            "equipment": "workstations",
            "is_bookable": True,
        },
        {
            "room_natural_key": "room_studio_1",
            "campus": CAMPUS_CODE,
            "room_name": "Studio 1",
            "room_type": "classroom",
            "capacity": SKILLS_COURSE_CAPACITY,
            "equipment": "workstations",
            "is_bookable": True,
        },
        {
            "room_natural_key": "room_studio_2",
            "campus": CAMPUS_CODE,
            "room_name": "Studio 2",
            "room_type": "classroom",
            "capacity": L2_SKILLS_RESERVED_SEATS,
            "equipment": "workstations",
            "is_bookable": True,
        },
        {
            "room_natural_key": "room_studio_3",
            "campus": CAMPUS_CODE,
            "room_name": "Studio 3",
            "room_type": "classroom",
            "capacity": L2_SKILLS_RESERVED_SEATS,
            "equipment": "",
            "is_bookable": True,
        },
        {
            "room_natural_key": "room_demo_stage",
            "campus": CAMPUS_CODE,
            "room_name": "Demo stage",
            "room_type": "stage",
            "capacity": 40,
            "equipment": "projector",
            "is_bookable": True,
        },
        {
            "room_natural_key": "room_machinery",
            "campus": CAMPUS_CODE,
            "room_name": "Machinery room",
            "room_type": "maker_room",
            "capacity": 8,
            "equipment": "laser_cutter,cnc",
            "is_bookable": True,
        },
        {
            "room_natural_key": "room_workshop",
            "campus": CAMPUS_CODE,
            "room_name": "Workshop",
            "room_type": "maker_room",
            "capacity": 16,
            "equipment": "assembly_benches",
            "is_bookable": True,
        },
        {
            "room_natural_key": "room_office",
            "campus": CAMPUS_CODE,
            "room_name": "Office",
            "room_type": "classroom",
            "capacity": 4,
            "equipment": "",
            "is_bookable": False,
        },
    ]


def projects() -> list[dict[str, Any]]:
    """Minimal project catalog. No questions, answers or difficulty scores."""
    assert PROJECT_HOURS_MIN <= 5 <= PROJECT_HOURS_MAX
    assert PROJECT_HOURS_MIN <= 8 <= PROJECT_HOURS_MAX
    return [
        {
            "project_id": "rgb_led",
            "project_name": "RGB LED light",
            "program_natural_key": "prg_level_1",
            "duration_hours": 5,
            "step_count": 12,
            "sessions_needed": 2,
            "topics": "breadboard,wires,color_theory,potentiometer,rgb_led,ide_intro",
        },
        {
            "project_id": "self_driving_car",
            "project_name": "Self-driving car",
            "program_natural_key": "prg_level_1",
            "duration_hours": 8,
            "step_count": 20,
            "sessions_needed": 4,
            "topics": "microcontroller,ultrasonic_sensor,led,motion,servo,motor_driver",
        },
        {
            "project_id": "weather_station",
            "project_name": "Weather station",
            "program_natural_key": "prg_level_1",
            "duration_hours": 8,
            "step_count": 24,
            "sessions_needed": 4,
            "topics": "microcontroller,lcd,sensors,temperature,light_level,gyroscope",
        },
        {
            "project_id": "l2_project_1",
            "project_name": "Level 2 project 1",
            "program_natural_key": "prg_level_2",
            "duration_hours": 8,
            "step_count": 28,
            "sessions_needed": 12,
            "topics": "closed_build,guided_variation",
        },
        {
            "project_id": "l2_project_2",
            "project_name": "Level 2 project 2",
            "program_natural_key": "prg_level_2",
            "duration_hours": 8,
            "step_count": 28,
            "sessions_needed": 12,
            "topics": "closed_build,guided_variation",
        },
        {
            "project_id": "skill_python_foundations",
            "project_name": "Python foundations",
            "program_natural_key": "prg_skills",
            "duration_hours": 6,
            "step_count": 10,
            "sessions_needed": 6,
            "topics": "syntax,control_flow,functions",
        },
        {
            "project_id": "skill_electronics_lab",
            "project_name": "Electronics lab",
            "program_natural_key": "prg_skills",
            "duration_hours": 6,
            "step_count": 10,
            "sessions_needed": 6,
            "topics": "circuits,components,measurement",
        },
        {
            "project_id": "skill_data_sensing",
            "project_name": "Data sensing",
            "program_natural_key": "prg_skills",
            "duration_hours": 6,
            "step_count": 10,
            "sessions_needed": 6,
            "topics": "sensors,logging,charts",
        },
        {
            "project_id": "skill_embedded_logic",
            "project_name": "Embedded logic",
            "program_natural_key": "prg_skills",
            "duration_hours": 6,
            "step_count": 10,
            "sessions_needed": 6,
            "topics": "gpio,timing,state_machines",
        },
        {
            "project_id": "skill_model_basics",
            "project_name": "Model basics",
            "program_natural_key": "prg_skills",
            "duration_hours": 6,
            "step_count": 10,
            "sessions_needed": 6,
            "topics": "features,training,overfitting",
        },
        {
            "project_id": "skill_build_showcase",
            "project_name": "Prototype showcase",
            "program_natural_key": "prg_skills",
            "duration_hours": 6,
            "step_count": 10,
            "sessions_needed": 6,
            "topics": "integration,demo,documentation",
        },
    ]


def employees() -> list[dict[str, Any]]:
    coaches: list[dict[str, Any]] = []
    for index in range(1, COACH_COUNT + 1):
        token = make_token("employee", BRANCH_TYPE, index)
        coaches.append(
            {
                "employee_natural_key": token,
                "campus": CAMPUS_CODE,
                "role": "educator",
                "is_educator": True,
                "specialty": "ai",
                "hire_date": date(2026, 6, 1).isoformat(),
                "employment_status": "active",
                "source_system": SOURCE_SYSTEM,
            }
        )
    return coaches


def l1_projects() -> list[dict[str, Any]]:
    return [row for row in projects() if row["program_natural_key"] == "prg_level_1"]


def skills_projects() -> list[dict[str, Any]]:
    return [row for row in projects() if row["program_natural_key"] == "prg_skills"]


def term_for_date(value: date) -> str:
    for term_name, (start, end) in TERM_WINDOWS.items():
        if start <= value <= end:
            return term_name
    raise ValueError(f"The date {value.isoformat()} falls outside the launch year")


def iter_open_dates(start: date, end: date) -> list[date]:
    assert start <= end
    cursor = start
    open_dates: list[date] = []
    while cursor <= end:
        if cursor.weekday() in OPEN_WEEKDAYS:
            open_dates.append(cursor)
        cursor += timedelta(days=1)
    return open_dates


def month_end(value: date) -> date:
    return date(value.year, value.month, monthrange(value.year, value.month)[1])


def format_clock(value: time) -> str:
    return value.strftime("%H:%M")


DAY_NAMES = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}

SLOT_INDEX: dict[tuple[int, str], int] = {
    (2, "17:00"): 1,
    (3, "17:00"): 1,
    (4, "16:30"): 1,
    (5, "09:00"): 1,
    (5, "12:30"): 2,
    (5, "13:00"): 3,
    (6, "09:00"): 1,
    (6, "12:30"): 2,
    (6, "13:00"): 3,
}


def time_slot_label(session_date: date, start_clock: str) -> str:
    """Time slot label in the STEMStar style: "thursday slot_1"."""
    weekday = session_date.weekday()
    slot_index = SLOT_INDEX.get((weekday, start_clock), 1)
    return f"{DAY_NAMES[weekday]} slot_{slot_index}"


def l1_teaching_slots(session_date: date) -> list[tuple[str, str]]:
    weekday = session_date.weekday()
    if weekday in WEEKDAY_TEACHING:
        start, end = WEEKDAY_TEACHING[weekday]
        return [(format_clock(start), format_clock(end))]
    if weekday in (5, 6):
        return [(format_clock(start), format_clock(end)) for start, end in WEEKEND_L1_TURNS]
    return []


def l2_teaching_slot(session_date: date) -> tuple[str, str] | None:
    if session_date.weekday() in (5, 6):
        start, end = L2_FIXED_WINDOW
        return format_clock(start), format_clock(end)
    return None


def skills_teaching_slot(session_date: date) -> tuple[str, str] | None:
    weekday = session_date.weekday()
    if weekday in (5, 6):
        start, end = SKILLS_WEEKEND_WINDOW
        return format_clock(start), format_clock(end)
    if weekday in (2, 3, 4):
        start, end = SKILLS_WEEKDAY_WINDOW
        return format_clock(start), format_clock(end)
    return None


def assert_catalog_invariants() -> None:
    for project in projects():
        hours = float(project["duration_hours"])
        assert PROJECT_HOURS_MIN <= hours <= PROJECT_HOURS_MAX, project
        expected_sessions = max(1, math.ceil(hours / L1_BLOCK_HOURS))
        if project["program_natural_key"] == "prg_level_1":
            assert project["sessions_needed"] == expected_sessions, project
    assert len(employees()) == COACH_COUNT
    assert all(LAUNCH_YEAR_START <= launch <= LAUNCH_YEAR_END for launch, _, _ in L2_ROUNDS)
    assert len(SKILLS_LAUNCH_MONTHS) == len(skills_projects())
    assert L2_ROUND_CAPACITY >= L2_SKILLS_RESERVED_SEATS
    assert TERM_AUTUMN in TERM_WINDOWS and TERM_SPRING in TERM_WINDOWS
