'''
File:   tickets.py
Brief:  create_ticket tool — prepares a ticket draft.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Tool executor builds a TicketPayload from agent-supplied arguments,
determines urgency (from agent or rules), and returns a ToolOutcome
carrying a ticket_draft event for UI rendering.
'''

from __future__ import annotations

import logging
from collections.abc import Callable

from pydantic import ValidationError

from mechanic.agent.tools_base import ToolContext, ToolDef, ToolError, ToolOutcome

logger = logging.getLogger(__name__)


def _require_hub(ctx: ToolContext) -> object:  # ServiceHub
    """Return the ServiceHub from *ctx* or raise ``ToolError``."""
    if ctx.services is None:
        raise ToolError("services are not wired into the tool context")
    return ctx.services  # type: ignore[return-value]


async def _execute_create_ticket(
    args: dict, ctx: ToolContext
) -> str | ToolOutcome:
    """Execute the create_ticket tool.

    Args:
        args: Parsed JSON arguments with required *anomaly_type*,
            *conclusion*, *operations*, and *references*.
        ctx: Tool context carrying vehicle/session defaults and services.

    Returns:
        A ``ToolOutcome`` containing draft confirmation text and a
        ``ticket_draft`` event payload.

    Raises:
        ToolError: If the session is not found or pydantic validation
            fails on the ticket payload.
    """
    from shared.models import Reference, TicketPayload

    hub = _require_hub(ctx)  # type: ignore[var-annotated]

    # Step 1: resolve session_id and vehicle_id.
    session_id: str | None = args.get("session_id") or ctx.session_id
    if not session_id:
        latest = hub.fleet.latest_session(ctx.vehicle_id)  # type: ignore[attr-defined]
        if latest is None:
            raise ToolError(
                f"Для ТС {ctx.vehicle_id} нет проверок; укажите session_id"
            )
        session_id = latest.session_id

    vehicle_id: str = ctx.vehicle_id

    # Step 2: fetch the diagnostic context.
    try:
        session_record = hub.fleet.get_session(  # type: ignore[attr-defined]
            vehicle_id, session_id
        )
    except Exception as exc:
        raise ToolError(str(exc)) from None

    # Step 3: determine urgency and rationale.
    anomaly_type: str | None = args.get("anomaly_type")
    if not anomaly_type:
        raise ToolError(
            "Не указан anomaly_type (код неисправности F01…F14)"
        )
    from mechanic.services.priority import suggest_urgency

    fault_title = hub.fleet.fault_title(anomaly_type)  # type: ignore[attr-defined]
    suggestion = suggest_urgency(session_record, fault_title=fault_title)

    agent_urgency: str | None = args.get("urgency")
    if agent_urgency is not None:
        # Validate enum values.
        if agent_urgency not in ("low", "medium", "high"):
            raise ToolError(
                f"Недопустимое значение urgency: {agent_urgency}; "
                "должно быть low, medium или high"
            )
        urgency = agent_urgency
    else:
        urgency = suggestion.urgency

    # Rationale: agent-provided wins; fallback to suggestion's rationale.
    priority_rationale: str | None = args.get("priority_rationale")
    if priority_rationale is not None:
        rationale = priority_rationale
    else:
        rationale = suggestion.rationale

    urgency_source: str = "agent" if agent_urgency is not None else "rules"

    # Step 4: build and validate TicketPayload.
    operations: list[str] = args.get("operations", [])
    spare_parts: list[str] = args.get("spare_parts") or []
    conclusion: str = args.get("conclusion", "")

    try:
        references_raw: list[dict] = args.get("references") or []
        references: list[Reference] = [Reference(**r) for r in references_raw]
        payload = TicketPayload(
            vehicle_id=vehicle_id,
            session_id=session_id,
            anomaly_type=anomaly_type,
            conclusion=conclusion,
            urgency=urgency,
            operations=operations,
            spare_parts=spare_parts,
            references=references,
        )
    except ValidationError as exc:
        # Build a short Russian message listing failing fields.
        error_fields: list[str] = []
        for err in exc.errors():
            field_path = " -> ".join(str(f) for f in err.get("loc", []))
            error_fields.append(field_path)
        raise ToolError(
            "Ошибка валидации заявки: некорректны поля "
            + ", ".join(error_fields)
        ) from None

    # Step 5: return the outcome.
    content = (
        f"Черновик заявки готов и показан механику. Подача \u2014 кнопкой в форме "
        f"(ты НЕ подаёшь заявку). Сессия {session_id}, приоритет {urgency}."
    )

    event_payload: dict = {
        "payload": payload.model_dump(),
        "priority_rationale": rationale,
        "urgency_source": urgency_source,
        "session_id": session_id,
    }

    return ToolOutcome(
        content=content,
        is_error=False,
        event=("ticket_draft", event_payload),
    )


def make_create_ticket_tool() -> Callable[[object], ToolDef]:
    """Factory for the create_ticket tool definition.

    Returns:
        A callable that accepts a ServiceHub and returns a ToolDef.
    """

    def _factory(hub: object) -> ToolDef:
        return ToolDef(
            name="create_ticket",
            description=(
                "Собрать черновик заявки на дефектовку для показа механику; "
                "подача происходит кнопкой в интерфейсе."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "anomaly_type": {
                        "type": "string",
                        "pattern": "^F(0[1-9]|1[0-4])$",
                    },
                    "conclusion": {"type": "string"},
                    "urgency": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": (
                            "если не указан \u2014 рассчитай по правилам "
                            "(правила известны из результата диагностики)"
                        ),
                    },
                    "operations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "spare_parts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "manual": {"type": "string"},
                                "pdf_page": {
                                    "type": "integer",
                                    "minimum": 1,
                                },
                            },
                            "required": ["manual", "pdf_page"],
                        },
                    },
                    "priority_rationale": {
                        "type": "string",
                        "description": (
                            "обоснование приоритета одной строкой, "
                            "если считаешь сам"
                        ),
                    },
                    "session_id": {
                        "type": "string",
                        "description": (
                            "проверка, к которой относится заявка"
                        ),
                    },
                },
                "required": ["anomaly_type", "conclusion", "operations", "references"],
            },
            executor=_execute_create_ticket,
        )

    return _factory


__all__: list[str] = ["make_create_ticket_tool"]
