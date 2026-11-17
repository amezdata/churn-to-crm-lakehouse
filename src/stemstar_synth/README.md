# stemstar_synth

Synthetic stand-ins for the STEMStar operational extracts: four academic years (22-23 to 25-26) of
enrolment lists, attendance, absence sheets and legacy KPIs, plus the staff list. Every row is invented:
STEMStar is a fictional company. This generator lets anyone run the STEMStar half of the pipeline.

```bash
python -m stemstar_synth --output data/synthetic/stemstar --seed 42
```

About 97,000 rows in 29 CSV files, in under a second. The output is not committed: the same seed always
writes the same files.

## What it generates

| File | One row per | Columns |
|---|---|---|
| `enrolled_students_<year>.csv` | student enrolled that year | `name` (token), `campus`, `course`, `payment_tier`, `first_time_slot`, `previous_course` (not in 22-23) |
| `new_enrolments.csv` | student on the early 26-27 list | same, but `course` holds only the program |
| `attendance_<year>.csv` | booked session | `campus`, `class_name`, `class_date`, `time_slot`, `attendance_status`, `name` |
| `absences_<program>_<year>.csv` | student with at least one missed session (23-24 on) | `name`, `week_1` … `week_30`, `total` |
| `kpi_<year>.csv` | course | `course`, `enrolled_students`, `renewals`, `renewal_rate_pct`, `total_absences`, `refunds` |
| `employees.csv` | staff member | `name`, `campus`, `role`, `specialty`, `gender`, `start_date`, `end_date`, `is_active` |
| `manifest.json` | — | seed, row count per file, the KPI rows miscounted on purpose |

`name` is a 16-character hex token, the format the pseudonymisation step expects.

## How it works

All parameters are at the top of [`generate.py`](generate.py).

1. **Students.** 800 students start in 22-23 and newcomers join every year. Students move up a ladder of
   programs (spark, build, circuit or forge, pixel). Pixel is the last program, so its students do not renew.
2. **Attendance.** Each student has 30 weekly sessions. Most miss a session now and then, a few miss many,
   and about 7% stop coming mid-year, after which their remaining sessions are cancelled. Absences get more
   frequent towards the end of the year.
3. **Renewal.** A student renews if they appear on next year's list. The chance falls with absences and
   collapses above 5, the threshold at which a family is owed a partial refund.
4. **Derived files.** The absence sheets and the KPI files are computed from the attendance and the lists,
   so they agree with each other. 22-23 has no absence sheets and its KPI shows 0 absences: absences were
   not recorded that year.

On seed 42 (23-24 to 25-26, pixel excluded), the 227 students with more than 5 absences renew 12% of the
time, against 60% for the other 1,765. Enrolment goes 800, 821, 755, 684.

## Deliberate mess

Real exports are messy, and the Silver layer and the reconciliation have work to do only if this data is too.

- Absence-sheet file names with typos: `abscences_spark_24-25`, `absences_circit_24-25`, and `absences_build_26-26`,
  which actually holds 25-26.
- `class_name` is `build01` where the course code is `build_01`, and about 4% of rows carry only the program (`build`).
- About 0.5% of sessions were booked twice, with one booking cancelled.
- About 5% extra students booked a trial and never came. They appear in attendance, never in an enrolment list.
- The last three sessions of 25-26 are still `pending`, because the extract was taken before they were marked.
- Three legacy KPI rows have renewals miscounted by 3 or 4 students, as a hand-kept spreadsheet would. The
  reconciliation should flag exactly those rows. `manifest.json` lists them.

## What it is not

The parameters are round numbers chosen to give the data a plausible shape and to make the pipeline's
job visible. They describe no real company.
