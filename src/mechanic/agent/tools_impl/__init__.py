'''
File:   __init__.py
Brief:  Agent tool helpers and registry builder.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Exports ``_require_hub`` for use inside every executor,
``build_registry`` to assemble a ToolRegistry from a ServiceHub,
and re-exports the five tool factory functions so callers can import
from this package directly.
'''

from __future__ import annotations

import logging

from mechanic.agent.tools_base import ToolContext, ToolRegistry
from mechanic.agent.tools_impl.report_issue import make_report_issue_tool

logger = logging.getLogger(__name__)


def _require_hub(ctx: ToolContext) -> object:  # ServiceHub
    """Return the ServiceHub wired into *ctx*, or raise ``ToolError``.

    Args:
        ctx: The tool context carrying optional services.

    Returns:
        The :class:`~mechanic.services.hub.ServiceHub` instance.

    Raises:
        ToolError: If ``ctx.services`` is ``None``.
    """
    from mechanic.agent.tools_base import ToolError

    if ctx.services is None:
        raise ToolError("services are not wired into the tool context")
    return ctx.services  # type: ignore[return-value]


def build_registry(hub: object) -> ToolRegistry:  # ServiceHub
    """Register all five agent tools on a fresh :class:`ToolRegistry`.

    The tools are registered in the documented order:
    diagnostics, manuals, vehicles, tickets, documents.

    Args:
        hub: The :class:`~mechanic.services.hub.ServiceHub` instance.

    Returns:
        A fully populated :class:`ToolRegistry`.
    """
    from mechanic.agent.tools_base import ToolRegistry

    reg = ToolRegistry()

    # Import factories lazily to avoid circular deps at module level.
    from mechanic.agent.tools_impl.diagnostics import make_get_diagnostic_result_tool
    from mechanic.agent.tools_impl.documents import make_show_document_tool
    from mechanic.agent.tools_impl.manuals import make_search_manuals_tool
    from mechanic.agent.tools_impl.report_issue import (
        make_report_issue_tool,
    )
    from mechanic.agent.tools_impl.tickets import make_create_ticket_tool
    from mechanic.agent.tools_impl.vehicles import make_get_vehicle_info_tool

    reg.register(make_get_diagnostic_result_tool()(hub))
    reg.register(make_search_manuals_tool()(hub))
    reg.register(make_get_vehicle_info_tool()(hub))
    reg.register(make_create_ticket_tool()(hub))
    reg.register(make_report_issue_tool()(hub))
    reg.register(make_show_document_tool()(hub))

    return reg


__all__: list[str] = [
    "_require_hub",
    "build_registry",
    "make_get_diagnostic_result_tool",
    "make_search_manuals_tool",
    "make_get_vehicle_info_tool",
    "make_create_ticket_tool",
    "make_report_issue_tool",
    "make_show_document_tool",
]
