-- STEMStar PoC: OLTP silos in one Postgres cluster (self-hosted Supabase)
-- Design: three schemas, no cross-silo FOREIGN KEYs. The lakehouse is what joins them.
-- Security: data is already pseudonymized (HMAC token, 16 hex characters). No clear-text PII.
-- Run as postgres / supabase_admin against the `postgres` database.

BEGIN;

CREATE SCHEMA IF NOT EXISTS db_customers;
CREATE SCHEMA IF NOT EXISTS db_employees;
CREATE SCHEMA IF NOT EXISTS db_kpi;

COMMENT ON SCHEMA db_customers IS
  'CRM / education operations silo. Students, enrolments, attendance, absences.';
COMMENT ON SCHEMA db_employees IS
  'HR silo. Campus staff. No link to groups or students.';
COMMENT ON SCHEMA db_kpi IS
  'Silo of indicators already aggregated by management. They are not computed here from customers.';

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- SILO 1: customers DB
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS db_customers.student (
  student_token     char(16)     PRIMARY KEY,
  campus            text         NOT NULL DEFAULT 'campus_03',
  created_at        timestamptz  NOT NULL DEFAULT now(),
  updated_at        timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT student_token_hex CHECK (student_token ~ '^[0-9a-f]{16}$')
);

COMMENT ON TABLE db_customers.student IS
  'Student entity. PK = HMAC token; names, phone, school and age are not part of the PoC (anonymization at source).';

CREATE TABLE IF NOT EXISTS db_customers.enrolment (
  enrolment_id      bigserial    PRIMARY KEY,
  student_token     char(16)     NOT NULL
                    REFERENCES db_customers.student (student_token),
  campus            text         NOT NULL DEFAULT 'campus_03',
  academic_year     text         NOT NULL,
  course            text         NOT NULL,
  program           text         NOT NULL,
  section           text,
  payment_tier      text         NOT NULL,
  time_slot         text,
  created_at        timestamptz  NOT NULL DEFAULT now(),
  updated_at        timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT enrolment_year_chk CHECK (academic_year ~ '^\d{2}-\d{2}$'),
  CONSTRAINT enrolment_program_chk CHECK (
    program IN ('spark', 'build', 'circuit', 'forge', 'pixel', 'brainlab')
  ),
  CONSTRAINT enrolment_payment_tier_chk CHECK (payment_tier ~ '^tier_[1-5]$'),
  CONSTRAINT enrolment_student_year_uk UNIQUE (student_token, academic_year)
);

COMMENT ON COLUMN db_customers.enrolment.course IS
  'Raw operational value: spark_01 in 22-26; pixel/brainlab without a section in 26-27 (schema drift).';
COMMENT ON COLUMN db_customers.enrolment.section IS
  'Section extracted from course (01, 02, ...). NULL when the source has no number.';
COMMENT ON TABLE db_customers.enrolment IS
  'One row per student and year. It stores neither the previous course nor a renewal flag: those are derived in the lakehouse.';

CREATE TABLE IF NOT EXISTS db_customers.attendance (
  attendance_id       bigserial    PRIMARY KEY,
  student_token       char(16)     NOT NULL
                      REFERENCES db_customers.student (student_token),
  campus              text         NOT NULL DEFAULT 'campus_03',
  academic_year       text         NOT NULL,
  class_name          text         NOT NULL,
  class_date          date         NOT NULL,
  time_slot           text         NOT NULL,
  attendance_status   text         NOT NULL,
  created_at          timestamptz  NOT NULL DEFAULT now(),
  updated_at          timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT attendance_year_chk CHECK (academic_year ~ '^\d{2}-\d{2}$'),
  CONSTRAINT attendance_status_chk CHECK (
    attendance_status IN (
      'present', 'absent', 'cancelled',
      'pending', 'class_cancelled', 'invalid'
    )
  )
);

COMMENT ON COLUMN db_customers.attendance.class_name IS
  'Group identifier exactly as the system emits it (forge01, forge, spark01). Not normalized here.';

CREATE TABLE IF NOT EXISTS db_customers.absence (
  absence_id        bigserial    PRIMARY KEY,
  student_token     char(16)     NOT NULL
                    REFERENCES db_customers.student (student_token),
  academic_year     text         NOT NULL,
  program           text         NOT NULL,
  week              smallint     NOT NULL,
  is_absent         boolean      NOT NULL DEFAULT true,
  year_total        integer,
  created_at        timestamptz  NOT NULL DEFAULT now(),
  updated_at        timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT absence_year_chk CHECK (academic_year ~ '^\d{2}-\d{2}$'),
  CONSTRAINT absence_week_chk CHECK (week BETWEEN 1 AND 40),
  CONSTRAINT absence_program_chk CHECK (
    program IN ('spark', 'build', 'circuit', 'forge', 'pixel', 'brainlab')
  ),
  CONSTRAINT absence_student_week_uk UNIQUE (student_token, academic_year, program, week)
);

COMMENT ON TABLE db_customers.absence IS
  'Only students with at least one absence. Source: wide week_N files; stored in long format.';

CREATE INDEX IF NOT EXISTS enrolment_year_course_idx
  ON db_customers.enrolment (academic_year, course);
CREATE INDEX IF NOT EXISTS enrolment_updated_at_idx
  ON db_customers.enrolment (updated_at);
CREATE INDEX IF NOT EXISTS attendance_year_date_idx
  ON db_customers.attendance (academic_year, class_date);
CREATE INDEX IF NOT EXISTS attendance_student_idx
  ON db_customers.attendance (student_token);
CREATE INDEX IF NOT EXISTS attendance_updated_at_idx
  ON db_customers.attendance (updated_at);
CREATE INDEX IF NOT EXISTS absence_year_program_idx
  ON db_customers.absence (academic_year, program);
CREATE INDEX IF NOT EXISTS absence_updated_at_idx
  ON db_customers.absence (updated_at);

DROP TRIGGER IF EXISTS student_set_updated_at ON db_customers.student;
CREATE TRIGGER student_set_updated_at
  BEFORE UPDATE ON db_customers.student
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS enrolment_set_updated_at ON db_customers.enrolment;
CREATE TRIGGER enrolment_set_updated_at
  BEFORE UPDATE ON db_customers.enrolment
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS attendance_set_updated_at ON db_customers.attendance;
CREATE TRIGGER attendance_set_updated_at
  BEFORE UPDATE ON db_customers.attendance
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

DROP TRIGGER IF EXISTS absence_set_updated_at ON db_customers.absence;
CREATE TRIGGER absence_set_updated_at
  BEFORE UPDATE ON db_customers.absence
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- SILO 2: employees DB
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS db_employees.employee (
  employee_token    char(16)     PRIMARY KEY,
  campus            text         NOT NULL DEFAULT 'campus_03',
  role              text         NOT NULL,
  specialty         text,
  gender            text         NOT NULL,
  start_date        date         NOT NULL,
  end_date          date,
  is_active         boolean      NOT NULL,
  created_at        timestamptz  NOT NULL DEFAULT now(),
  updated_at        timestamptz  NOT NULL DEFAULT now(),
  CONSTRAINT employee_token_hex CHECK (employee_token ~ '^[0-9a-f]{16}$'),
  CONSTRAINT employee_role_chk CHECK (role IN ('educator', 'coordinator', 'reception')),
  CONSTRAINT employee_gender_chk CHECK (gender IN ('male', 'female')),
  CONSTRAINT employee_specialty_chk CHECK (
    specialty IS NULL
    OR specialty IN ('spark', 'build', 'circuit', 'forge', 'pixel', 'brainlab')
  ),
  CONSTRAINT employee_dates_chk CHECK (
    end_date IS NULL OR end_date >= start_date
  )
);

COMMENT ON TABLE db_employees.employee IS
  'Campus staff. specialty does not reference db_customers: matching educators to groups is the lakehouse''s job.';

CREATE INDEX IF NOT EXISTS employee_updated_at_idx
  ON db_employees.employee (updated_at);

DROP TRIGGER IF EXISTS employee_set_updated_at ON db_employees.employee;
CREATE TRIGGER employee_set_updated_at
  BEFORE UPDATE ON db_employees.employee
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- SILO 3: KPI tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS db_kpi.kpi_course_renewal (
  kpi_id                  bigserial     PRIMARY KEY,
  academic_year           text          NOT NULL,
  course                  text          NOT NULL,
  enrolled_students       integer       NOT NULL,
  renewals                integer       NOT NULL,
  renewal_rate_pct        numeric(6,2)  NOT NULL,
  total_absences          integer       NOT NULL DEFAULT 0,
  refunds                 integer       NOT NULL DEFAULT 0,
  computed_at             date,
  created_at              timestamptz   NOT NULL DEFAULT now(),
  updated_at              timestamptz   NOT NULL DEFAULT now(),
  CONSTRAINT kpi_year_chk CHECK (academic_year ~ '^\d{2}-\d{2}$'),
  CONSTRAINT kpi_counts_chk CHECK (
    enrolled_students >= 0
    AND renewals >= 0
    AND renewals <= enrolled_students
    AND total_absences >= 0
    AND refunds >= 0
  ),
  CONSTRAINT kpi_year_course_uk UNIQUE (academic_year, course)
);

COMMENT ON TABLE db_kpi.kpi_course_renewal IS
  'KPIs frozen in the operational system. No FK to enrolment. Gold reconciles the recompute against these figures.';
COMMENT ON COLUMN db_kpi.kpi_course_renewal.academic_year IS
  'Cohort year (kpi_22-23 = students enrolled in 22-23 and their renewal in 23-24).';

CREATE INDEX IF NOT EXISTS kpi_updated_at_idx
  ON db_kpi.kpi_course_renewal (updated_at);

DROP TRIGGER IF EXISTS kpi_set_updated_at ON db_kpi.kpi_course_renewal;
CREATE TRIGGER kpi_set_updated_at
  BEFORE UPDATE ON db_kpi.kpi_course_renewal
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Application roles (silos) + ingestion account (reads all three)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_customers') THEN
    CREATE ROLE app_customers NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_hr') THEN
    CREATE ROLE app_hr NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_management') THEN
    CREATE ROLE app_management NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fabric_ingest') THEN
    CREATE ROLE fabric_ingest NOINHERIT;
  END IF;
END
$$;

REVOKE ALL ON SCHEMA db_customers, db_employees, db_kpi FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA db_customers, db_employees, db_kpi FROM PUBLIC;

-- PostgREST must not expose these schemas by default
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON SCHEMA db_customers, db_employees, db_kpi FROM anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    REVOKE ALL ON SCHEMA db_customers, db_employees, db_kpi FROM authenticated;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA db_customers TO app_customers, fabric_ingest;
GRANT USAGE ON SCHEMA db_employees TO app_hr, fabric_ingest;
GRANT USAGE ON SCHEMA db_kpi TO app_management, fabric_ingest;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA db_customers TO app_customers;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA db_employees TO app_hr;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA db_kpi TO app_management;

GRANT SELECT ON ALL TABLES IN SCHEMA db_customers TO fabric_ingest;
GRANT SELECT ON ALL TABLES IN SCHEMA db_employees TO fabric_ingest;
GRANT SELECT ON ALL TABLES IN SCHEMA db_kpi TO fabric_ingest;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA db_customers TO app_customers;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA db_employees TO app_hr;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA db_kpi TO app_management;

ALTER DEFAULT PRIVILEGES IN SCHEMA db_customers
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_customers;
ALTER DEFAULT PRIVILEGES IN SCHEMA db_customers
  GRANT SELECT ON TABLES TO fabric_ingest;

ALTER DEFAULT PRIVILEGES IN SCHEMA db_employees
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_hr;
ALTER DEFAULT PRIVILEGES IN SCHEMA db_employees
  GRANT SELECT ON TABLES TO fabric_ingest;

ALTER DEFAULT PRIVILEGES IN SCHEMA db_kpi
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_management;
ALTER DEFAULT PRIVILEGES IN SCHEMA db_kpi
  GRANT SELECT ON TABLES TO fabric_ingest;

COMMIT;
