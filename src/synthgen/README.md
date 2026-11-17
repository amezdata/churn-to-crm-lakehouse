# synthgen

Packaged synthetic generator for the BrainLab greenfield sources. It produces coherent operational data (no real PII) to populate the lakehouse and demonstrate the pipeline end to end. It can be reinstalled for another campus without changing the data contract.

The output vocabulary (files, columns, statuses and time slots) is aligned with the STEMStar sources. `bronze_columns.py` maps the generator's internal keys to the Bronze column names and file names. Technical keys (`prg_level_1`, `rgb_led`, hex tokens) are kept for referential integrity.

## What it generates

| Destination | Format | Content |
|---|---|---|
| `data/synthetic/brainlab/brainlab_*.csv` | CSV | Programs, projects, rooms, employees, students, guardians, leads, offerings, enrolments, payments, class sessions, attendance and occupancy |
| `data/synthetic/brainlab/brainlab_platform_logs.jsonl` | JSON Lines | Platform session events: `session_started`, `session_paused`, `session_resumed`, `session_completed`, `session_abandoned` |
| `data/synthetic/brainlab/manifest.json` | JSON | Generation date, source system, file names and row counts |

Time slots follow the operating pattern `thursday slot_1` (day + slot), not raw clock times. The educational Report pillar (questions, grading and difficulty scores) is out of scope for this package.

By default, the landing (Bronze) tables include the usual mess of an operational source: attendance aliases from a second check-in app, missing tokens, occasional event typos, a duplicated event and a room name with a trailing space. The `--clean` option writes the same model without those defects.

## Usage

From the repository root:

```powershell
python scripts/generate_brainlab.py
python scripts/generate_brainlab.py --scale medium --seed 42
python scripts/generate_brainlab.py --clean
python scripts/generate_brainlab.py --overlap-tokens-file data\raw\stemstar_tokens.txt
```

As a module, with `src` on the `PYTHONPATH`:

```powershell
python -m synthgen --output data\synthetic\brainlab --seed 42
```

`--overlap-tokens-file` accepts one 16-character hex token per line (already pseudonymized STEMStar students) to simulate identity resolution across systems. Defaults are seed 42 and scale `small`.

## Tests

```powershell
python -m pytest tests
```

They check referential integrity, respect for the operating envelope capacities, no sessions on closed days, no clear-text PII, and that the logs carry no pedagogical payload.

## Contracts

The related data contracts (enrolment, attendance and platform logs) are in `contracts/` at the repository root. They define schema, quality and SLA before the data exists.
