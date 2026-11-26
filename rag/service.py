'''
File:   service.py
Brief:  RAG search service (FastAPI) for participant B.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Run separately from the backend:  uvicorn rag.service:app --port 8003
Contract (fixed, shapes from shared/models.py):
  POST /search                              → SearchResponse
  GET  /document/{doc_id}/page/{page_pdf}   → PageContent
  GET  /health                              → service and index facts
Without a built index the service starts and answers 503 with a hint;
without the embedding model it serves BM25-only (mode in /health).
'''

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from shared.models import PageContent, SearchResponse

from rag.config import RagSettings, get_settings
from rag.index.dense import DenseIndex
from rag.index.store import read_current
from rag.knowledge.expand import detect_fault  # noqa: F401 (docs: used by search)
from rag.knowledge.loader import Knowledge, load_knowledge
from rag.schemas import SearchRequest
from rag.search import SearchEngine

logger = logging.getLogger(__name__)


class AppState:
    '''Everything loaded once at startup.'''

    settings: RagSettings
    knowledge: Knowledge
    engine: SearchEngine | None
    dense: DenseIndex | None


state = AppState()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    '''Load knowledge, index and the embedding model at startup.'''
    state.settings = get_settings()
    state.knowledge = load_knowledge(Path(__file__).parent / "knowledge")
    state.dense = None
    if state.settings.embed_model and state.settings.embed_model != "none":
        cache_dir = state.settings.data_dir / "emb_cache"
        state.dense = DenseIndex(
            state.settings.embed_model, cache_dir, device=state.settings.device
        )
    stored = read_current(state.settings.data_dir, state.settings.index_version)
    if stored is None:
        logger.warning(
            "no built index under %s — /search returns 503", state.settings.data_dir
        )
        state.engine = None
    else:
        state.engine = SearchEngine(
            stored, state.knowledge, state.settings, state.dense
        )
        logger.info(
            "index %s loaded: %s chunks, mode %s",
            stored.version,
            len(stored.chunks),
            state.engine.mode,
        )
    yield


app = FastAPI(
    title="Digital Mechanic RAG service",
    description="Manual search for participant B (hackathon issue #1).",
    version="0.1.0",
    lifespan=lifespan,
)
# Open CORS like the issued mock services (architecture-B §8).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_engine() -> SearchEngine:
    '''Return the loaded engine or raise 503 with a build hint.'''
    if state.engine is None:
        raise HTTPException(
            status_code=503,
            detail="index not built yet; run: python -m rag.ingest",
        )
    return state.engine


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    '''Search the manuals of one engine, strictly filtered before scoring.'''
    engine = _require_engine()
    try:
        return engine.search(
            query=request.query,
            engine_model=request.engine_model,
            top_k=request.top_k,
            fault_code=request.fault_code,
            doc_id=request.doc_id,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("search failed")
        raise HTTPException(status_code=500, detail=f"search failed: {exc}") from exc


@app.get("/document/{doc_id}/page/{page_pdf}", response_model=PageContent)
async def get_page(doc_id: str, page_pdf: int) -> PageContent:
    '''Return one page's text plus the local PDF path (may be None).'''
    engine = _require_engine()
    stored = engine.index
    key = (doc_id, page_pdf)
    if page_pdf < 1 or key not in stored.page_text:
        raise HTTPException(
            status_code=404, detail=f"page not found: {doc_id} p.{page_pdf}"
        )

    doc_title = None
    pdf_path: str | None = None
    chunk = next((c for c in stored.chunks if c.doc_id == doc_id), None)
    if chunk is not None:
        doc_title = chunk.doc_title
    manuals_dir = state.settings.manuals_dir
    if manuals_dir.is_dir():
        candidate = manuals_dir / _manifest_file_name(doc_id)
        if candidate.is_file():
            pdf_path = str(candidate.resolve())
    return PageContent(
        doc_id=doc_id,
        doc_title=doc_title or doc_id,
        page_pdf=page_pdf,
        text=stored.page_text[key],
        pdf_path=pdf_path,
    )


@app.get("/health")
async def health() -> dict:
    '''Service facts: mode, index version, per-doc chunk counts.'''
    engine = state.engine
    if engine is None:
        return {"status": "no_index", "mode": "none", "hint": "python -m rag.ingest"}
    stored = engine.index
    return {
        "status": "ok",
        "mode": engine.mode,
        "index_version": stored.version,
        "built_at": stored.built_at,
        "embedding_model": stored.embed_model,
        "n_chunks": len(stored.chunks),
        "n_pages": len(stored.page_text),
        "docs": stored.manifest.docs,
    }


_MANIFEST_CACHE: dict[str, str] | None = None


def _manifest_file_name(doc_id: str) -> str:
    '''Resolve doc_id → PDF file name from the manuals manifest.

    Args:
        doc_id: Manifest designation ("236.01.01 РК").

    Returns:
        File name from manifest.json, or the doc_id itself when unknown.
    '''
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        _MANIFEST_CACHE = {}
        manifest_path = state.settings.manuals_dir / "manifest.json"
        if manifest_path.is_file():
            import json

            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in data.get("documents", []):
                _MANIFEST_CACHE[entry["doc_id"]] = entry["file"]
    return _MANIFEST_CACHE.get(doc_id, doc_id)


@app.get("/documents")
async def documents() -> list[dict]:
    '''Passport of the indexed documents (ids, titles, engines, pages).'''
    engine = _require_engine()
    result: list[dict] = []
    seen: set[str] = set()
    for chunk in engine.index.chunks:
        if chunk.doc_id in seen:
            continue
        seen.add(chunk.doc_id)
        result.append(
            {
                "doc_id": chunk.doc_id,
                "doc_title": chunk.doc_title,
                "doc_type": chunk.doc_type,
                "engines": chunk.engines,
            }
        )
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8003)
