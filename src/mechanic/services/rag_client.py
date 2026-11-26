'''
File:   rag_client.py
Brief:  Manual manifest loader and async RAG client with mock fallback.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from shared.models import PageContent, SearchHit, SearchResponse

from mechanic.errors import MockApiError, RagUnavailableError

# ---------------------------------------------------------------------------
# Manifest doc model (matches the JSON structure in manuals/manifest.json).
# ---------------------------------------------------------------------------


class ManifestDoc:
    """Parsed entry from the manual manifest."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.doc_id: str = data["doc_id"]
        self.file: str = data["file"]
        self.engines: list[str] = data["engines"]
        self.kind: str = data["kind"]
        self.title: str = data["title"]
        self.pages: int = data["pages"]


# ---------------------------------------------------------------------------
# ManualManifest — read-only view of the manuals manifest JSON.
# ---------------------------------------------------------------------------


class ManualManifest:
    """Loads *manifest.json* from a directory and provides lookup helpers."""

    def __init__(self, manuals_dir: Path) -> None:
        self._manuals_dir = manuals_dir
        self._docs: dict[str, ManifestDoc] = {}
        manifests_path = manuals_dir / "manifest.json"
        if not manifests_path.is_file():
            raise RagUnavailableError(f"Manifest file not found: {manifests_path}")
        try:
            data = json.loads(manifests_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RagUnavailableError(f"Malformed manifest.json: {exc}") from exc

        for entry in data.get("documents", []):
            doc = ManifestDoc(entry)
            self._docs[doc.doc_id] = doc

    def doc(self, doc_id: str) -> ManifestDoc | None:
        """Return the manifest document by *doc_id*, or ``None``."""
        return self._docs.get(doc_id)

    def docs_for_engine(self, engine_model: str) -> list[ManifestDoc]:
        """Return all documents whose engine list contains *engine_model* (exact)."""
        return [d for d in self._docs.values() if engine_model in d.engines]

    def pdf_path(self, doc_id: str) -> Path | None:
        """Resolve the local PDF path for a document if it exists on disk."""
        doc = self._docs.get(doc_id)
        if doc is None:
            return None
        full_path = self._manuals_dir / doc.file
        if full_path.is_file():
            return full_path
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_doc_id(doc_id: str) -> str:
    """Strip surrounding whitespace, remove guillemets, collapse internal whitespace."""
    doc_id = doc_id.strip()
    doc_id = doc_id.replace("«", "").replace("»", "")
    doc_id = " ".join(doc_id.split())
    return doc_id.strip()


# ---------------------------------------------------------------------------
# RagClient — async RAG search with mock chunks fallback.
# ---------------------------------------------------------------------------


class RagClient:
    """HTTP client for the RAG service with local mock fallback."""

    def __init__(
        self,
        base_url: str,
        mock_chunks_path: Path | None,
        manuals_dir: Path,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            base_url: Root URL of the RAG service.
            mock_chunks_path: Optional path to a JSONL mock chunks file for fallback.
            manuals_dir: Directory containing ``manifest.json`` and PDF files.
            http: Optional pre-existing ``httpx.AsyncClient``.  When *None* a new
                client is created with standard timeouts and owned by this instance.
        """
        self._base_url = base_url.rstrip("/")
        self._mock_chunks_path = mock_chunks_path
        self._manifest = ManualManifest(manuals_dir) if manuals_dir else None
        if http is not None:
            self._http = http
            self._owned = False
        else:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
            )
            self._owned = True

    async def aclose(self) -> None:
        """Close the HTTP client *only* if it was self-owned."""
        if self._owned:
            await self._http.aclose()

    # -- search ---------------------------------------------------------------

    async def search(
        self, query: str, engine_model: str, top_k: int = 5
    ) -> SearchResponse:
        """Search for manual fragments matching *query* and *engine_model*.

        Args:
            query: Free-text search query.
            engine_model: Engine model to filter by (exact match both in
                the RAG service and in the mock fallback).
            top_k: Maximum number of results to return.

        Returns:
            A validated ``SearchResponse`` model instance.
        """
        url = f"{self._base_url}/search"
        payload = {"query": query, "engine_model": engine_model, "top_k": top_k}

        try:
            response = await self._http.post(url, json=payload)
        except httpx.RequestError:
            # Service down → fall back to mock chunks.
            return self._search_mock(query, engine_model, top_k)

        if response.status_code == 200:
            return SearchResponse.model_validate(response.json())

        # HTTP error (non-200) → authoritative answer from the service.
        try:
            detail = response.json().get("detail", "")
        except Exception:  # noqa: BLE001
            detail = ""

        if not detail:
            text = response.text[:300]
            detail = text if len(text) < 300 else text + "..."

        raise MockApiError("rag", response.status_code, detail)

    def _search_mock(
        self, query: str, engine_model: str, top_k: int
    ) -> SearchResponse:
        """Mock fallback search using a JSONL chunks file."""
        if self._mock_chunks_path is None or not self._mock_chunks_path.is_file():
            return SearchResponse(results=[], no_instruction=True)

        # Parse query words of length > 2.
        query_words = [w.lower() for w in query.split() if len(w) > 2]
        if not query_words:
            return SearchResponse(results=[], no_instruction=True)

        # Read and filter chunks.
        chunks: list[dict[str, Any]] = []
        try:
            text_content = self._mock_chunks_path.read_text(encoding="utf-8")
            for line in text_content.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                # Exact engine match.
                if obj.get("engine") != engine_model:
                    continue
                chunks.append(obj)
        except Exception:  # noqa: BLE001
            return SearchResponse(results=[], no_instruction=True)

        # Score each chunk.
        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in chunks:
            section = chunk.get("section") or ""
            text = chunk.get("text") or ""
            combined = (section + " " + text).lower()

            matches = sum(1 for w in query_words if w in combined)
            score = matches / len(query_words)

            if score > 0:
                scored.append((score, chunk))

        # Sort descending by score.
        scored.sort(key=lambda x: -x[0])
        top = scored[:top_k]

        results: list[SearchHit] = []
        for score_val, chunk in top:
            tier = "high" if score_val >= 0.5 else "med"
            results.append(
                SearchHit(
                    doc_id=chunk.get("doc_id", ""),
                    doc_title=chunk.get("doc_title", ""),
                    page_pdf=chunk.get("page_pdf", 1),
                    section=chunk.get("section"),
                    text=chunk.get("text", ""),
                    score=score_val,
                    tier=tier,
                )
            )

        if results:
            return SearchResponse(results=results, no_instruction=False)
        return SearchResponse(results=[], no_instruction=True)

    # -- get_page -------------------------------------------------------------

    async def get_page(self, doc_id: str, page_pdf: int) -> PageContent:
        """Retrieve a single document page.

        Args:
            doc_id: Document identifier.
            page_pdf: PDF page number (1-based).

        Returns:
            A validated ``PageContent`` model instance.

        Raises:
            MockApiError: On authoritative HTTP errors from the RAG service.
            RagUnavailableError: When neither remote nor local data is available.
        """
        doc_id = normalize_doc_id(doc_id)
        url = f"{self._base_url}/document/{doc_id}/page/{page_pdf}"

        try:
            response = await self._http.get(url)
        except httpx.RequestError:
            # Service down → fall back to local manifest + PDF.
            return self._get_page_local(doc_id, page_pdf)

        if response.status_code == 200:
            return PageContent.model_validate(response.json())

        # HTTP error (non-200) → authoritative answer from the service.
        try:
            detail = response.json().get("detail", "")
        except Exception:  # noqa: BLE001
            detail = ""

        if not detail:
            text = response.text[:300]
            detail = text if len(text) < 300 else text + "..."

        raise MockApiError("rag", response.status_code, detail)

    def _get_page_local(self, doc_id: str, page_pdf: int) -> PageContent:
        """Local fallback for get_page when RAG is unreachable."""
        if self._manifest is None:
            return PageContent(
                doc_id=doc_id,
                doc_title="",
                page_pdf=page_pdf,
                text="",
                pdf_path=None,
            )

        doc = self._manifest.doc(doc_id)
        if doc is None:
            raise RagUnavailableError(
                f"document {doc_id} is not in the manuals manifest"
            )

        pdf_path = self._manifest.pdf_path(doc_id)
        if pdf_path is None:
            raise RagUnavailableError(
                f"manual file for {doc_id} is not available on this server"
            )

        return PageContent(
            doc_id=doc_id,
            doc_title=doc.title,
            page_pdf=page_pdf,
            text="",
            pdf_path=str(pdf_path),
        )
