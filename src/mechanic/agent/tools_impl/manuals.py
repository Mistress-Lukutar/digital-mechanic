'''
File:   manuals.py
Brief:  search_manuals tool — searches manual fragments.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Tool executor calls the RAG service to search for manual fragments
matching a query against a specific engine model, returning either
a numbered list of hits or a NO_INSTRUCTION response.
'''

from __future__ import annotations

import logging

from mechanic.agent.tools_base import ToolContext, ToolDef, ToolError, ToolOutcome

logger = logging.getLogger(__name__)


async def _execute_search_manuals(
    args: dict, ctx: ToolContext
) -> str | ToolOutcome:
    """Execute the search_manuals tool.

    Args:
        args: Parsed JSON arguments with required *query* and optional
            *engine_model*.
        ctx: Tool context carrying vehicle defaults and services.

    Returns:
        A formatted list of search hits, or a ``ToolOutcome`` with
        ``is_error=False`` when no instruction is found.

    Raises:
        ToolError: When the RAG service returns an HTTP error.
    """
    from mechanic.errors import MockApiError

    hub = _require_hub(ctx)  # type: ignore[var-annotated]

    query: str = args.get("query", "")
    if not query:
        raise ToolError("Поисковый запрос (query) обязателен")

    engine_model: str | None = args.get("engine_model")
    if not engine_model:
        # Fall back to the vehicle's engine model.
        vehicle = hub.fleet.get_vehicle(ctx.vehicle_id)  # type: ignore[attr-defined]
        engine_model = vehicle.engine_model

    try:
        resp = await hub.rag.search(query, engine_model, top_k=5)  # type: ignore[attr-defined]
    except MockApiError as exc:
        raise ToolError(str(exc)) from None

    if resp.no_instruction or not resp.results:
        content = (
            f"NO_INSTRUCTION: в руководствах на двигатель {engine_model} "
            f'по запросу "{query}" инструкций не найдено. '
            "Сообщи механику, что инструкции нет, и рекомендуй дефектовку "
            "(допустима общая проверка узла). "
            "НЕ используй данные из руководств других двигателей."
        )
        return ToolOutcome(content=content, is_error=False)

    lines: list[str] = []
    for i, hit in enumerate(resp.results, start=1):
        tier_label = hit.tier if hit.tier else "tier ?"
        text_snippet = (hit.text or "")[:800]
        line = (
            f"{i}. [{hit.doc_id}, стр. {hit.page_pdf}] "
            f"({tier_label}, score={hit.score})\n{text_snippet}"
        )
        lines.append(line)

    header = f"Найдено фрагментов: {len(resp.results)} (двигатель {engine_model})"
    content = header + "\n\n" + "\n\n".join(lines)
    return content


def make_search_manuals_tool() -> callable:
    """Factory for the search_manuals tool definition.

    Returns:
        A callable that accepts a ServiceHub and returns a ToolDef.
    """

    def _factory(hub: object) -> ToolDef:
        return ToolDef(
            name="search_manuals",
            description=(
                "Поиск по руководствам текущего двигателя; возвращает список "
                "фрагментов с номерами страниц и цитатами."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "поисковый запрос по руководствам",
                    },
                    "engine_model": {
                        "type": "string",
                        "description": (
                            "модель двигателя; по умолчанию двигатель "
                            "выбранного ТС — НЕ меняй без необходимости"
                        ),
                    },
                },
                "required": ["query"],
            },
            executor=_execute_search_manuals,
        )

    return _factory


def _require_hub(ctx: ToolContext) -> object:  # ServiceHub
    """Return the ServiceHub from *ctx* or raise ``ToolError``."""
    if ctx.services is None:
        raise ToolError("services are not wired into the tool context")
    return ctx.services  # type: ignore[return-value]


__all__: list[str] = ["make_search_manuals_tool"]
