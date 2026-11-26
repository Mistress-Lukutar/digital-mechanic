'''
File:   vehicles.py
Brief:  get_vehicle_info tool — vehicle card with history.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Tool executor returns a structured Russian-language card for the selected
vehicle, including recent check sessions and previous ticket records.
'''

from __future__ import annotations

import logging

from mechanic.agent.tools_base import ToolContext, ToolDef, ToolError, ToolOutcome

logger = logging.getLogger(__name__)


async def _execute_get_vehicle_info(
    args: dict, ctx: ToolContext
) -> str | ToolOutcome:
    """Execute the get_vehicle_info tool.

    Args:
        args: Parsed JSON arguments with optional *vehicle_id*.
        ctx: Tool context carrying vehicle defaults and services.

    Returns:
        A formatted Russian-language vehicle card with history.

    Raises:
        ToolError: If the vehicle is not found in the fleet.
    """
    hub = _require_hub(ctx)  # type: ignore[var-annotated]

    vehicle_id: str = args.get("vehicle_id") or ctx.vehicle_id
    if not vehicle_id:
        raise ToolError("Не указан vehicle_id (госномер)")

    try:
        card = hub.fleet.get_vehicle(vehicle_id)  # type: ignore[attr-defined]
    except Exception as exc:
        raise ToolError(str(exc)) from None

    lines: list[str] = []
    lines.append(f"Гаражный номер: {card.garage_no}")
    lines.append(f"Марка/модель: {card.make} {card.model or ''}".strip())
    lines.append(f"Тип: {card.vehicle_type}")
    lines.append(f"Двигатель: {card.engine_model}")
    lines.append(f"Топливо: {card.fuel}")
    lines.append("")

    # Recent sessions (newest first, up to 5).
    sessions = hub.fleet.sessions_desc(vehicle_id)  # type: ignore[attr-defined]
    lines.append("Последние проверки (новые сверху):")
    for s in sessions[:5]:
        lines.append(
            f"- {s.session_id} | {s.checked_at} | {s.status} | "
            f"{s.anomaly_type or '-'} | score {s.anomaly_score} | "
            f"conf {s.confidence} | {s.signal_quality}"
        )
    lines.append("")

    # Previous tickets.
    tickets = hub.ticket_log.list_by_vehicle(vehicle_id)  # type: ignore[attr-defined]
    if tickets:
        lines.append("Прошлые заявки:")
        for t in tickets:
            conclusion_preview = (t.payload.conclusion or "")[:80]
            lines.append(
                f"- {t.ticket_id} от {t.created_at:%Y-%m-%d} | "
                f"{t.payload.anomaly_type} | {conclusion_preview}"
            )
    else:
        lines.append("Прошлых заявок нет.")

    return "\n".join(lines)


def make_get_vehicle_info_tool() -> callable:
    """Factory for the get_vehicle_info tool definition.

    Returns:
        A callable that accepts a ServiceHub and returns a ToolDef.
    """

    def _factory(hub: object) -> ToolDef:
        return ToolDef(
            name="get_vehicle_info",
            description=(
                "Карточка ТС с историей проверок и прошлыми заявками; "
                "по умолчанию берётся выбранное ТС."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "vehicle_id": {
                        "type": "string",
                        "description": "госномер; по умолчанию выбранное ТС",
                    },
                },
            },
            executor=_execute_get_vehicle_info,
        )

    return _factory


def _require_hub(ctx: ToolContext) -> object:  # ServiceHub
    """Return the ServiceHub from *ctx* or raise ``ToolError``."""
    if ctx.services is None:
        raise ToolError("services are not wired into the tool context")
    return ctx.services  # type: ignore[return-value]


__all__: list[str] = ["make_get_vehicle_info_tool"]
