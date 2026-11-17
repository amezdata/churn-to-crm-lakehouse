"""Reverse ETL (PoC): Gold scores to the simulated CRM via the vault. Does not touch the star schema."""

from __future__ import annotations

from datetime import date
from typing import Any

from transforms.pii import FORBIDDEN_COLUMNS, TOKEN_COLUMNS

CRM_SCORES_TABLE = "scores_churn"
BAND_HIGH = "high"
BAND_MEDIUM = "medium"
BAND_LOW = "low"
HIGH_FRACTION = 0.10
MEDIUM_CUMULATIVE_FRACTION = 0.30
CRM_COLUMNS = (
    "student_token",
    "source_system",
    "student_id",
    "enrolment_id",
    "score_churn",
    "risk_band",
    "scoring_date",
)


def build_crm_scores_churn(
    scores: list[dict[str, Any]],
    vault: list[dict[str, Any]],
    *,
    scored_on: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join `gold.scores_churn` with `silver.identity_map`. Only the CRM receives `student_token`."""
    scoring_date = scored_on or date.today()
    by_student = _vault_by_student(vault)
    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    missing = 0
    for row in scores:
        student_id = _student_key(row.get("student_id"))
        identity = by_student.get(student_id)
        if identity is None:
            missing += 1
            continue
        matched.append((row, identity))

    bands = _risk_bands([_as_float(row.get("score_churn")) or 0.0 for row, _identity in matched])
    crm_rows: list[dict[str, Any]] = []
    for (row, identity), band in zip(matched, bands, strict=True):
        crm_rows.append(
            _crm_row(
                {
                    "student_token": identity["student_token"],
                    "source_system": identity.get("source_system") or row.get("source_system"),
                    "student_id": row.get("student_id"),
                    "enrolment_id": row.get("enrolment_id"),
                    "score_churn": _as_float(row.get("score_churn")),
                    "risk_band": band,
                    "scoring_date": scoring_date,
                }
            )
        )
    metrics = {
        "n_scores": len(scores),
        "n_written": len(crm_rows),
        "n_missing_from_vault": missing,
        "n_high": sum(1 for row in crm_rows if row["risk_band"] == BAND_HIGH),
        "n_medium": sum(1 for row in crm_rows if row["risk_band"] == BAND_MEDIUM),
        "n_low": sum(1 for row in crm_rows if row["risk_band"] == BAND_LOW),
        "scoring_date": scoring_date.isoformat(),
    }
    return crm_rows, metrics


def _vault_by_student(vault: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    indexed: dict[Any, dict[str, Any]] = {}
    for row in vault:
        student_id = _student_key(row.get("student_id"))
        token = row.get("student_token")
        if student_id is None or token is None:
            continue
        if student_id in indexed:
            continue
        indexed[student_id] = {
            "student_token": token,
            "source_system": row.get("source_system"),
        }
    return indexed


def _risk_bands(scores: list[float]) -> list[str]:
    """High = top decile (Precision@decile); medium = next 20 %; low = the rest."""
    count = len(scores)
    if count == 0:
        return []
    high_cut = max(1, int(count * HIGH_FRACTION))
    medium_cut = max(high_cut, int(count * MEDIUM_CUMULATIVE_FRACTION))
    ranked = sorted(range(count), key=lambda index: (-scores[index], index))
    bands = [BAND_LOW] * count
    for position, index in enumerate(ranked):
        if position < high_cut:
            bands[index] = BAND_HIGH
        elif position < medium_cut:
            bands[index] = BAND_MEDIUM
    return bands


def _crm_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key in CRM_COLUMNS:
        cleaned[key] = row.get(key)
    for key in list(cleaned):
        if key == "student_token":
            continue
        if key in FORBIDDEN_COLUMNS or key in TOKEN_COLUMNS or key.endswith("_token"):
            del cleaned[key]
    return cleaned


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _student_key(value: Any) -> Any:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value
