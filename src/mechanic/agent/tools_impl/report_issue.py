'''
File:   report_issue.py
Brief:  report_issue tool — forwards a non-standard situation to the admin
        alert store.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0

Tool executor captures an issue description, looks up the vehicle's engine
model, and inserts an ``agent_report`` alert so administrators see the
problem automatically.
'''

from __future__ import annotations

import logging
from collections.abc import Callable

from mechanic.agent.tools_base import (
    ToolContext,
    ToolDef,
    ToolError,
    ToolOutcome,
)

logger = logging.getLogger(__name__)


def _require_hub(ctx: ToolContext) -> object:  # ServiceHub
    """Return the ServiceHub from *ctx* or raise ``ToolError``."""
    if ctx.services is None:
        raise ToolError("services are not wired into the tool context")
    return ctx.services  # type: ignore[return-value]


async def _execute_report_issue(
    args: dict, ctx: ToolContext
) -> str | ToolOutcome:
    """Execute the report_issue tool.

    Args:
        args: Parsed JSON arguments with required *issue* field.
        ctx: Tool context carrying vehicle/session defaults and services.

    Returns:
        A confirmation string informing the mechanic that the issue
        has been forwarded to the administrator.

    Raises:
        ToolError: If the issue text is empty or missing.
    """
    hub = _require_hub(ctx)  # type: ignore[var-annotated]
    issue = (args.get("issue") or "").strip()
    if not issue:
        raise ToolError("Не указан текст проблемы (issue)")
    engine_model: str | None = None
    try:
        engine_model = hub.fleet.get_vehicle(ctx.vehicle_id).engine_model  # type: ignore[attr-defined]
    except Exception:
        engine_model = None
    hub.alerts.add(  # type: ignore[attr-defined]
        kind="agent_report",
        text=issue,
        username=ctx.username,
        vehicle_id=ctx.vehicle_id,
        session_id=ctx.session_id,
        engine_model=engine_model,
    )
    return (
        "Ситуация передана администратору. Продолжай помогать механику: "
        "дай конкретное действие или прямой ответ, не оставляй его без пути."
    )


def make_report_issue_tool() -> Callable[[object], ToolDef]:
    """Factory for the report_issue tool definition.

    Returns:
        A callable that accepts a ServiceHub and returns a ToolDef.
    """

    def _factory(hub: object) -> ToolDef:
        return ToolDef(
            name="report_issue",
            description=(
                "Передать администратору нестандартную ситуацию (в руководстве "
                "нет данных, противоречивые сведения, сомнительная диагностика); "
                "вызывай, когда механик может остаться без ответа."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "issue": {
                        "type": "string",
                        "description": (
                            "краткое описание проблемы для администратора: что "
                            "случилось, по какой машине/двигателю, что мешает"
                        ),
                    },
                },
                "required": ["issue"],
            },
            executor=_execute_report_issue,
        )

    return _factory


__all__: list[str] = ["make_report_issue_tool"]
