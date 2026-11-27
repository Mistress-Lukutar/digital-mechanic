"""
File:   priority.py
Brief:  Deterministic urgency suggestion for diagnostic results.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Maps a :class:`~shared.models.DiagnosticResult` to an urgency level
based on fault-code criticality and anomaly score thresholds.
The rationale text is in Russian — it is shown directly to the mechanic
in the UI.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from shared.models import DiagnosticResult

# Fault codes that indicate engine-integrity faults risking route failure:
# valvetrain (F01), oil pressure (F02), overheating/coolant (F03),
# diesel fuel delivery (F08), turbo (F09), timing chain (F14).
CRITICAL_CODES: frozenset[str] = frozenset(
    {"F01", "F02", "F03", "F08", "F09", "F14"}
)

# Fault codes tied to a specific fuel system: code -> fuel substring the
# vehicle card must contain (lowercase). Extend as new codes demand.
FUEL_COMPATIBLE_FUELS: dict[str, str] = {"F08": "дизель"}


class UrgencySuggestion(BaseModel):
    """Suggested urgency level for a diagnostic finding.

    Attributes:
        urgency: One of ``"low"``, ``"medium"``, or ``"high"``.
        rationale: Russian-language explanation shown to the mechanic.
    """

    urgency: Literal["low", "medium", "high"]
    rationale: str


def suggest_urgency(
    diag: DiagnosticResult, fault_title: str
) -> UrgencySuggestion:
    """Determine urgency for a diagnostic finding.

    Rules (in priority order):
        1. Critical fault code AND (anomaly_score >= 0.7 OR confidence >= 0.75)
           → ``"high"``
        2. Critical fault code but moderate readings
           → ``"medium"``
        3. Non-critical code with anomaly_score >= 0.8
           → ``"medium"``
        4. Everything else
           → ``"low"``

    Args:
        diag: The diagnostic result to evaluate.
        fault_title: Human-readable title of the fault unit (used in rationale).

    Returns:
        An :class:`UrgencySuggestion` with the computed urgency and Russian rationale.
    """
    anomaly_score = diag.anomaly_score if diag.anomaly_score is not None else 0.0
    confidence = diag.confidence if diag.confidence is not None else 0.0
    is_critical = diag.anomaly_type in CRITICAL_CODES if diag.anomaly_type else False

    # Format values for display — "нет данных" when None
    score_display: str
    conf_display: str
    if diag.anomaly_score is None:
        score_display = "нет данных"
    else:
        score_display = str(diag.anomaly_score)
    if diag.confidence is None:
        conf_display = "нет данных"
    else:
        conf_display = str(diag.confidence)

    # Rule 1: critical code with high enough scores → high
    if is_critical and (anomaly_score >= 0.7 or confidence >= 0.75):
        return UrgencySuggestion(
            urgency="high",
            rationale=(
                f"Приоритет высокий: критичный узел «{fault_title}» "
                f"(score {score_display}, confidence {conf_display}) "
                f"— поставить на дефектовку до выпуска в рейс."
            ),
        )

    # Rule 2: critical code but moderate readings → medium
    if is_critical:
        return UrgencySuggestion(
            urgency="medium",
            rationale=(
                f"Приоритет средний: критичный узел «{fault_title}», "
                f"показания умеренные (score {score_display}, "
                f"confidence {conf_display}) — дефектовка на ближайшем ТО, "
                f"работа под наблюдением."
            ),
        )

    # Rule 3: non-critical but significant deviation → medium
    if anomaly_score >= 0.8:
        return UrgencySuggestion(
            urgency="medium",
            rationale=(
                f"Приоритет средний: узел «{fault_title}» значительно отклоняется "
                f"от нормы (score {score_display}) — дефектовка на ближайшем ТО, "
                f"работа под наблюдением."
            ),
        )

    # Rule 4: everything else → low
    if diag.anomaly_score is None or diag.confidence is None:
        return UrgencySuggestion(
            urgency="low",
            rationale=(
                f"Приоритет низкий: «{fault_title}» — машина работает, "
                f"узел проверяется на следующей проверке "
                f"(score {score_display}, confidence {conf_display})."
            ),
        )
    return UrgencySuggestion(
        urgency="low",
        rationale=(
            f"Приоритет низкий: «{fault_title}» — машина работает, "
            f"узел проверяется на следующей проверке."
        ),
    )
