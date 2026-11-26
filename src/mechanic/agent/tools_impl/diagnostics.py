'''
File:   diagnostics.py
Brief:  get_diagnostic_result tool — fetches ML diagnostic result.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Tool executor calls the Mock ML service to retrieve a diagnostic result
for a given vehicle and session, returning a formatted Russian-language
report or a ToolError on failure.
'''

from __future__ import annotations

import logging

from mechanic.agent.tools_base import ToolContext, ToolDef, ToolError, ToolOutcome

logger = logging.getLogger(__name__)


async def _execute_diagnostics(
    args: dict, ctx: ToolContext
) -> str | ToolOutcome:
    """Execute the get_diagnostic_result tool.

    Args:
        args: Parsed JSON arguments with optional *vehicle_id* and *session_id*.
        ctx: Tool context carrying vehicle/session defaults and services.

    Returns:
        A formatted diagnostic report string, or a ``ToolOutcome`` on error.

    Raises:
        ToolError: If the ML service is unreachable or returns an HTTP error.
    """
    from mechanic.errors import MockApiError

    hub = _require_hub(ctx)  # type: ignore[var-annotated]

    vehicle_id: str = args.get("vehicle_id") or ctx.vehicle_id
    session_id: str | None = args.get("session_id") or ctx.session_id

    if not vehicle_id:
        raise ToolError("Не указан vehicle_id (госномер) и нет выбранного ТС")

    # Resolve session_id if not provided.
    if not session_id:
        latest = hub.fleet.latest_session(vehicle_id)
        if latest is None:
            raise ToolError(
                f"Для ТС {vehicle_id} нет проверок; укажите session_id"
            )
        session_id = latest.session_id

    try:
        diag = await hub.ml.diagnose(vehicle_id, session_id)  # type: ignore[attr-defined]
    except MockApiError as exc:
        raise ToolError(
            f"ML-сервис недоступен или не знает эту проверку: {exc.detail}"
        ) from None

    content = (
        f"Результат проверки {session_id} ТС {vehicle_id}:\n"
        f"{diag.model_dump_json(indent=2)}"
    )
    return content


def make_get_diagnostic_result_tool() -> callable:
    """Factory for the get_diagnostic_result tool definition.

    Returns:
        A callable that accepts a ServiceHub and returns a ToolDef.
    """

    def _factory(hub: object) -> ToolDef:
        return ToolDef(
            name="get_diagnostic_result",
            description=(
                "Получить результат акустической проверки двигателя (ML-сервис); "
                "по умолчанию берётся выбранное ТС и последняя проверка."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "vehicle_id": {
                        "type": "string",
                        "description": "госномер ТС; по умолчанию берётся выбранное ТС",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "id проверки; по умолчанию последняя проверка",
                    },
                },
            },
            executor=_execute_diagnostics,
        )

    return _factory


def _require_hub(ctx: ToolContext) -> object:  # ServiceHub
    """Return the ServiceHub from *ctx* or raise ``ToolError``."""
    if ctx.services is None:
        raise ToolError("services are not wired into the tool context")
    return ctx.services  # type: ignore[return-value]


__all__: list[str] = ["make_get_diagnostic_result_tool"]
