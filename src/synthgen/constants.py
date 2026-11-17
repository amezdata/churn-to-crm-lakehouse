"""Constants of the BrainLab synthetic generator.

Operating magnitudes follow the launch-year operating envelope
(grades 6-12, Wednesday to Sunday, 3 coaches, 24 + 12 seats).
No real geography or company names are emitted.
"""

from __future__ import annotations

from datetime import date, time

CAMPUS_CODE = "campus_03"
BRANCH_TYPE = "brainlab"
SOURCE_SYSTEM = "brainlab_csv"
CURRENCY_CODE = "LOC"
TOKEN_HEX_LENGTH = 16

LAUNCH_YEAR_START = date(2026, 8, 1)
LAUNCH_YEAR_END = date(2027, 7, 31)

GRADE_MIN = 6
GRADE_MAX = 12

# weekday: Monday=0 ... Sunday=6. Closed Monday and Tuesday (rest and machinery).
OPEN_WEEKDAYS = (2, 3, 4, 5, 6)

COACH_COUNT = 3
L1_DEDICATED_SEATS = 24
L2_SKILLS_RESERVED_SEATS = 12
CONCURRENT_SEAT_CEILING = 36
L2_ROUND_CAPACITY = 62
SKILLS_COURSE_CAPACITY = 12

L1_BLOCK_HOURS = 2.5
PROJECT_HOURS_MIN = 4
PROJECT_HOURS_MAX = 10

TERM_AUTUMN = "2026-Autumn"
TERM_SPRING = "2027-Spring"
TERM_WINDOWS: dict[str, tuple[date, date]] = {
    TERM_AUTUMN: (date(2026, 8, 1), date(2026, 12, 31)),
    TERM_SPRING: (date(2027, 1, 1), date(2027, 7, 31)),
}

# Level 2 monthly rounds: launch month -> (project_id, delivery end).
L2_ROUNDS: tuple[tuple[date, str, date], ...] = (
    (date(2026, 10, 1), "l2_project_1", date(2026, 12, 31)),
    (date(2026, 11, 1), "l2_project_1", date(2027, 1, 31)),
    (date(2026, 12, 1), "l2_project_1", date(2027, 2, 28)),
    (date(2027, 2, 1), "l2_project_2", date(2027, 4, 30)),
    (date(2027, 3, 1), "l2_project_2", date(2027, 5, 31)),
    (date(2027, 4, 1), "l2_project_2", date(2027, 6, 30)),
)

SKILLS_LAUNCH_MONTHS: tuple[date, ...] = (
    date(2026, 10, 1),
    date(2026, 11, 1),
    date(2026, 12, 1),
    date(2027, 2, 1),
    date(2027, 3, 1),
    date(2027, 4, 1),
)

# Teaching windows (local clock, no time zone label).
WEEKDAY_TEACHING: dict[int, tuple[time, time]] = {
    2: (time(17, 0), time(19, 0)),
    3: (time(17, 0), time(19, 0)),
    4: (time(16, 30), time(18, 30)),
}
WEEKEND_L1_TURNS: tuple[tuple[time, time], ...] = (
    (time(9, 0), time(11, 30)),
    (time(12, 30), time(15, 0)),
)
L2_FIXED_WINDOW = (time(9, 0), time(11, 30))
SKILLS_WEEKEND_WINDOW = (time(13, 0), time(15, 30))
SKILLS_WEEKDAY_WINDOW = (time(17, 0), time(19, 0))

SCHOOL_TYPES = ("public", "private")
SCHOOL_TYPE_WEIGHTS = (0.62, 0.38)
GENDERS = ("female", "male")
RELATIONSHIPS = ("mother", "father", "other")
RELATIONSHIP_WEIGHTS = (0.48, 0.42, 0.10)
LEAD_CHANNELS = ("referral", "web", "event", "visit", "messaging")
LEAD_CHANNEL_WEIGHTS = (0.28, 0.24, 0.18, 0.16, 0.14)
LEAD_STATUS_CONVERTED = "converted"
LEAD_STATUSES_OPEN = ("new", "contacted", "qualified", "lost")
LOST_REASONS = ("price", "schedule", "distance", "competitor", "no_response")
PAYMENT_METHODS = ("mobile_payment", "card", "cash", "bank_transfer", "online")
PAYMENT_METHOD_WEIGHTS = (0.40, 0.22, 0.12, 0.10, 0.16)

ENROLMENT_STATUS_ACTIVE = "active"
ENROLMENT_STATUS_COMPLETED = "completed"
ENROLMENT_STATUS_WITHDRAWN = "withdrawn"
ENROLMENT_STATUSES = ("active", "completed", "cancelled", "withdrawn")
SESSION_STATUS_SCHEDULED = "scheduled"
SESSION_STATUS_HELD = "held"
SESSION_STATUS_CANCELLED = "cancelled"
SESSION_STATUSES = ("scheduled", "held", "cancelled")
ATTENDANCE_PRESENT = "present"
ATTENDANCE_LATE = "late"
ATTENDANCE_STATUSES = ("present", "absent", "late", "excused")
ATTENDANCE_WEIGHTS = (0.78, 0.12, 0.06, 0.04)
PAYMENT_STATUS_PAID = "paid"
PAYMENT_STATUS_PENDING = "pending"
PAYMENT_STATUS_REFUNDED = "refunded"
PAYMENT_STATUS_PARTIAL = "partial"
PAYMENT_STATUSES = ("paid", "pending", "refunded", "partial")

ORIGIN_OVERLAP = "stemstar_overlap"
ORIGIN_NEW = "brainlab_new"

PLATFORM_EVENT_TYPES = (
    "session_started",
    "session_paused",
    "session_resumed",
    "session_completed",
    "session_abandoned",
)
EVENT_STARTED = "session_started"
EVENT_PAUSED = "session_paused"
EVENT_RESUMED = "session_resumed"
EVENT_COMPLETED = "session_completed"
EVENT_ABANDONED = "session_abandoned"

LIST_PRICE_L1 = 280.00
LIST_PRICE_L2 = 3600.00
LIST_PRICE_SKILLS = 1800.00

OVERLAP_RATIO = 0.35
L2_RENEWAL_RATE = 0.55
WITHDRAWN_RATE = 0.08
PLATFORM_PAUSE_RATE = 0.30
PLATFORM_ABANDON_RATE = 0.12
LEAD_MULTIPLIER = 1.7

MESS_MISSING_TOKEN_RATE = 0.02
MESS_DUPLICATE_EVENT_RATE = 0.01
MESS_TYPO_EVENT_RATE = 0.01
MESS_MIXED_ATTENDANCE_RATE = 0.08
MESS_MISSING_CHECKIN_RATE = 0.15

SCALE_PRESETS: dict[str, dict[str, int]] = {
    "small": {
        "n_students": 48,
        "l2_per_round": 12,
        "skills_per_course": 8,
        "l1_sessions_per_week": 4,
    },
    "medium": {
        "n_students": 90,
        "l2_per_round": 22,
        "skills_per_course": 10,
        "l1_sessions_per_week": 6,
    },
}
