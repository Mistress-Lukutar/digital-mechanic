'''
File:   documents_api.py
Brief:  Manual document listing, page retrieval and file download.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Provides the ``/api/documents`` router with endpoints for listing available
manuals, fetching individual pages via RAG, and downloading raw PDF files.
'''

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from mechanic.api.deps import get_hub
from mechanic.errors import MockApiError, RagUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


async def _auth_user(request: Request) -> object:  # TokenUser
    """Resolve bearer token to :class:`TokenUser`."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    token = auth_header[7:]
    user = get_hub().auth.resolve_token(token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    return user


@router.get("")
async def list_documents(
    user=Depends(_auth_user),
) -> list[dict]:
    """List all available manual documents.

    Iterates over engines known from the fleet and collects deduplicated
    manifest entries for each engine.
    """
    hub = get_hub()
    # Collect all engine models from the fleet.
    try:
        vehicles = hub.fleet.list_vehicles()
        engines = sorted({v.engine_model for v in vehicles})
    except Exception:  # noqa: BLE001
        engines = []

    seen: set[str] = set()
    docs: list[dict] = []
    for engine in engines:
        for doc in hub.manifest.docs_for_engine(engine):
            if doc.doc_id not in seen:
                seen.add(doc.doc_id)
                docs.append(
                    {
                        "doc_id": doc.doc_id,
                        "title": doc.title,
                        "pages": doc.pages,
                        "engines": doc.engines,
                        "file": doc.file,
                    }
                )
    return docs


@router.get("/{doc_id}/page/{page_pdf}")
async def get_page(
    doc_id: str,
    page_pdf: int,
    user=Depends(_auth_user),
) -> dict:
    """Fetch a single page of a manual document."""
    hub = get_hub()
    try:
        page = await hub.rag.get_page(doc_id, page_pdf)
    except RagUnavailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MockApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return {
        "doc_id": page.doc_id,
        "doc_title": page.doc_title or "",
        "page_pdf": page.page_pdf,
        "text": page.text,
        "pdf_path": page.pdf_path,
    }


@router.get("/{doc_id}/file")
async def get_file(
    doc_id: str,
    user=Depends(_auth_user),
) -> FileResponse:
    """Return the raw PDF file for a document."""
    hub = get_hub()
    doc = hub.manifest.doc(doc_id)
    if doc is None:
        raise HTTPException(
            status_code=404, detail="manual file not available"
        )

    pdf_path = hub.manifest.pdf_path(doc_id)
    if pdf_path is None:
        raise HTTPException(
            status_code=404, detail="manual file not available"
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=doc.file,
    )
