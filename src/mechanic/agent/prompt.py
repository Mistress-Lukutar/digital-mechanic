'''
File:   prompt.py
Brief:  System prompt builder for the digital mechanic agent with language selection.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.1

Reads a template from prompts/system.md (or uses a fallback), fills in
the vehicle context block and engine-specific documents block, then
returns the complete system prompt string. Supports an optional *language*
parameter to append a language-rule block for non-Russian responses.

The module-level PROMPTS_DIR constant can be monkeypatched by tests to
point at alternative directories.
'''

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default prompts directory relative to CWD (repo root).
# Tests may monkeypatch this to point at a temp dir.
PROMPTS_DIR: Path = Path("prompts")

# Language display names for the language-block instruction.
LANGUAGE_NAMES: dict[str, str] = {
    "kk": "казахский (қазақша)",
    "uz": "узбекский (oʻzbekcha, латиница)",
    "hi": "хинди (देवनागरी)",
}

_KNOWN_LANGUAGES: set[str] = {"ru", "kk", "uz", "hi"}

FALLBACK_TEMPLATE: str = """\
## 1. Role and Context

You are an engine diagnostic assistant for commercial vehicles.
Selected vehicle and engine are below.

**RULE:** Technical facts must come from the manuals for THIS engine only.

## 2. Tools

Use these tools as needed: get_diagnostic_result, search_manuals,
get_vehicle_info, create_ticket, show_document.

## 3. Vehicle Context (Russian)

{vehicle_block}

## 4. Documents (Russian)

{docs_block}

---
The agent must respond in Russian and follow the rules above.
"""


def build_system_prompt(
    hub: object, vehicle_id: str, language: str = "ru"
) -> str:  # ServiceHub
    """Build the full system prompt for a given vehicle.

    Reads the template from ``prompts/system.md`` (or uses a fallback),
    fills in the vehicle block and engine documents block, replaces
    placeholders, and appends a language-rule block when *language* is not
    ``"ru"`` (or when an unknown value is provided — it falls back to the
    Russian rule).

    Args:
        hub: The :class:`~mechanic.services.hub.ServiceHub` instance.
        vehicle_id: License-plate identifier of the selected vehicle.
        language: Target response language code. Valid values are ``"ru"``,
            ``"kk"``, ``"uz"``, ``"hi"``. Unknown values fall back to
            ``"ru"`` (a warning is logged).

    Returns:
        The complete system prompt string with all placeholders filled and
        the language block appended where applicable.
    """

    # Validate / normalise language parameter.
    if language not in _KNOWN_LANGUAGES:
        logger.warning(
            "build_system_prompt: unknown language '%s', falling back to 'ru'",
            language,
        )
        language = "ru"

    # Determine prompts directory path.
    prompts_path = PROMPTS_DIR / "system.md"
    if prompts_path.exists():
        template = prompts_path.read_text(encoding="utf-8")
    else:
        template = FALLBACK_TEMPLATE

    # Fetch vehicle data.
    from mechanic.services.fleet import FleetStore

    fleet: FleetStore = hub.fleet  # type: ignore[attr-defined]
    vehicle = fleet.get_vehicle(vehicle_id)
    engine_model: str = vehicle.engine_model

    latest = fleet.latest_session(vehicle_id)
    tickets = hub.ticket_log.list_by_vehicle(vehicle_id)  # type: ignore[attr-defined]

    # --- Build vehicle_block (Russian) ---
    vlines: list[str] = []
    vlines.append(f"ТС: {vehicle_id}")
    vlines.append(f"Гаражный номер: {vehicle.garage_no}")
    vlines.append(f"Марка/модель: {vehicle.make} {vehicle.model or ''}".strip())
    vlines.append(f"Тип: {vehicle.vehicle_type}")
    vlines.append(f"**Двигатель: {engine_model}**")
    vlines.append(f"Топливо: {vehicle.fuel}")
    vlines.append("")

    # Latest check info.
    if latest is not None:
        vlines.append(
            f"Последняя проверка: {latest.session_id} | "
            f"{latest.checked_at} | {latest.status}"
        )
        if latest.anomaly_type:
            vlines.append(
                f"  тип: {latest.anomaly_type}, score={latest.anomaly_score}, "
                f"conf={latest.confidence}, quality={latest.signal_quality}"
            )
    else:
        vlines.append("Последняя проверка: нет данных")
    vlines.append("")

    # History (last 5 anomalies).
    sessions = fleet.sessions_desc(vehicle_id)
    anomaly_sessions = [s for s in sessions if s.anomaly_type is not None]
    if anomaly_sessions[:2]:
        vlines.append("История (последние аномалии):")
        for a in anomaly_sessions[:2]:
            vlines.append(
                f"- {a.session_id} | {a.checked_at} | {a.anomaly_type} | "
                f"score {a.anomaly_score}"
            )
    else:
        vlines.append("История аномалий: нет")
    vlines.append("")

    # Tickets.
    if tickets:
        vlines.append("Прошлые заявки:")
        for t in tickets[:5]:
            conclusion_preview = (t.payload.conclusion or "")[:80]
            vlines.append(
                f"- {t.ticket_id} от {t.created_at:%Y-%m-%d} | "
                f"{t.payload.anomaly_type} | {conclusion_preview}"
            )
    else:
        vlines.append("Прошлых заявок нет.")

    vehicle_block = "\n".join(vlines)

    # --- Build docs_block (Russian) ---
    from mechanic.services.rag_client import ManualManifest

    manifest: ManualManifest = hub.manifest  # type: ignore[attr-defined]
    docs = manifest.docs_for_engine(engine_model)

    dlines: list[str] = [f"Руководства на двигатель {engine_model}:"]
    for d in docs:
        dlines.append(f"- \u00ab{d.doc_id}\u00bb \u2014 {d.title} ({d.pages} стр.)")
    dlines.append(
        "Полные тексты ищи через search_manuals; страницы указывай как в PDF."
    )

    docs_block = "\n".join(dlines)

    # --- Replace placeholders ---
    result = template.replace("{vehicle_block}", vehicle_block)
    result = result.replace("{docs_block}", docs_block)

    # --- Append language block (blank-line separated) ---
    if language == "ru":
        lang_block = (
            "\n"
            "## ЯЗЫК ОТВЕТА\n"
            "\n"
            "Отвечай на языке вопроса пользователя (по умолчанию — русский). "
            "Цитаты\n"
            "`[обозначение документа, стр. N]`, обозначения документов, цифры и\n"
            "технические термины из руководства не переводи — приводи их так,\n"
            "как в источнике."
        )
    else:
        lang_name = LANGUAGE_NAMES[language]
        lang_block = (
            "\n"
            "## ЯЗЫК ОТВЕТА\n"
            "\n"
            f"Отвечай на языке: {lang_name}. Цитаты\n"
            "`[обозначение документа, стр. N]`, обозначения документов, цифры и\n"
            "термины из руководства не переводи — приводи их так, как в источнике,\n"
            "поясняя на языке ответа."
        )

    result += lang_block

    return result


__all__: list[str] = ["PROMPTS_DIR", "LANGUAGE_NAMES", "build_system_prompt"]
