'''
File:   documents.py
Brief:  show_document tool — opens a manual page.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Tool executor retrieves a single document page from the RAG service,
returning either text content or a PDF-path fallback, and emits a
document event for UI panel rendering.
'''

from __future__ import annotations

import logging

from mechanic.agent.tools_base import ToolContext, ToolDef, ToolError, ToolOutcome

logger = logging.getLogger(__name__)


def _require_hub(ctx: ToolContext) -> object:  # ServiceHub
    """Return the ServiceHub from *ctx* or raise ``ToolError``."""
    if ctx.services is None:
        raise ToolError("services are not wired into the tool context")
    return ctx.services  # type: ignore[return-value]


async def _execute_show_document(
    args: dict, ctx: ToolContext
) -> str | ToolOutcome:
    """Execute the show_document tool.

    Args:
        args: Parsed JSON arguments with required *doc_id* and *page_pdf*.
        ctx: Tool context carrying vehicle defaults and services.

    Returns:
        A ``ToolOutcome`` with page content text and a ``document`` event.

    Raises:
        ToolError: If the document is unavailable on the server.
    """
    from mechanic.errors import MockApiError, RagUnavailableError

    hub = _require_hub(ctx)  # type: ignore[var-annotated]

    doc_id: str = args.get("doc_id", "")
    page_pdf: int = args.get("page_pdf", 1)

    if not doc_id:
        raise ToolError("Не указан doc_id (обозначение документа)")

    try:
        page = await hub.rag.get_page(doc_id, page_pdf)  # type: ignore[attr-defined]
    except RagUnavailableError:
        raise ToolError(
            f"Документ \u00ab{doc_id}\u00bb недоступен на сервере "
            f"(нет ни RAG-сервиса, ни файла руководства)."
        ) from None
    except MockApiError as exc:
        raise ToolError(str(exc)) from None

    # Build content.
    header = (
        f"Страница {page_pdf} документа "
        f"\u00ab{doc_id}\u00bb открыта в панели."
    )
    parts: list[str] = [header]
    if page.text:
        parts.append(f"\nТекст страницы:\n{page.text[:1500]}")
    else:
        parts.append("\nТекст страницы недоступен (работает только PDF-файл).")

    content = "\n".join(parts)

    event_payload: dict = {
        "doc_id": doc_id,
        "doc_title": page.doc_title or "",
        "page_pdf": page_pdf,
        "pdf_path": page.pdf_path or "",
        "has_text": bool(page.text),
    }

    return ToolOutcome(
        content=content,
        is_error=False,
        event=("document", event_payload),
    )


def make_show_document_tool() -> callable:
    """Factory for the show_document tool definition.

    Returns:
        A callable that accepts a ServiceHub and returns a ToolDef.
    """

    def _factory(hub: object) -> ToolDef:
        return ToolDef(
            name="show_document",
            description=(
                "Открыть страницу руководства в панели рядом с чатом; "
                "нужны doc_id и номер страницы PDF."
            ),
            parameters_json_schema={
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "обозначение документа из результатов поиска",
                    },
                    "page_pdf": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "номер страницы PDF, от 1",
                    },
                },
                "required": ["doc_id", "page_pdf"],
            },
            executor=_execute_show_document,
        )

    return _factory


__all__: list[str] = ["make_show_document_tool"]
