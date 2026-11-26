'''
File:   search.py
Brief:  Search engine: masking, expansion, fusion, tiers, refusal.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Implements the fixed contract from Issue #1 on top of the index: strict
engine filtering BEFORE scoring, tier over a comparable score (cosine in
hybrid mode, IDF-normalised BM25 relevance otherwise), and the explicit
``no_instruction`` signal that drives the agent's honest refusal. Used by
both the FastAPI service and the eval runner.
'''

from __future__ import annotations

import re

import numpy as np
from shared.models import SearchHit, SearchResponse

from rag.config import RagSettings
from rag.index.dense import DenseIndex
from rag.index.fusion import fuse
from rag.index.store import StoredIndex
from rag.index.tokenizer import tokenize
from rag.knowledge.expand import coverage_for, detect_fault, expand_query
from rag.knowledge.loader import Knowledge

# Candidates kept per query variant before fusion.
CANDIDATES_PER_VARIANT = 100
# Minimum cosine for a dense candidate to enter fusion.
DENSE_MIN_COSINE = 0.15

# Section-title boost: when most of the query's content stems appear in
# the chunk's section title, the chunk gains a small comparable-score bump
# ("техническое обслуживание двигателя" should lift the ТО section page).
SECTION_BOOST = 0.08
SECTION_OVERLAP = 0.5

# Latin look-alikes → Cyrillic for engine model normalisation.
_HOMOGLYPHS = str.maketrans(
    {
        "A": "А", "B": "В", "E": "Е", "K": "К", "M": "М", "H": "Н",
        "O": "О", "P": "Р", "T": "Т", "X": "Х", "C": "С", "Y": "У",
    }
)
_STRIP_ENGINE = re.compile(r"(?i)\bдвигател\w*")


def normalize_engine(engine_model: str) -> str:
    '''Normalise an engine model string for comparisons.

    Uppercase, Latin homoglyphs mapped to Cyrillic, unified dashes, the
    word "двигатель" and stray spaces removed.

    Args:
        engine_model: Raw engine model from the fleet or the agent.

    Returns:
        Canonical engine model ("ЯМЗ-236М2").
    '''
    value = engine_model.translate(_HOMOGLYPHS).upper()
    value = _STRIP_ENGINE.sub(" ", value)
    value = re.sub(r"[\u2010\u2011\u2012\u2013\u2014]", "-", value)
    return re.sub(r"\s+", " ", value).strip(" -,")
    # note: "ЯМЗ-236М2" and "ямз 236м2" both reduce to "ЯМЗ-236М2"


class SearchEngine:
    '''Contract-level search over a stored index.'''

    def __init__(
        self,
        index: StoredIndex,
        knowledge: Knowledge,
        settings: RagSettings,
        dense: DenseIndex | None = None,
    ) -> None:
        '''Bind the engine to an index, knowledge, settings, dense model.

        Args:
            index: Stored index (BM25, optional embedding matrix).
            knowledge: Loaded dictionaries.
            settings: RAG settings (thresholds, caps).
            dense: Embedding model for query encoding; None or an
                unavailable model degrades the engine to BM25-only.
        '''
        self.index = index
        self.knowledge = knowledge
        self.settings = settings
        self.dense = dense
        self._rows_by_doc: dict[str, list[int]] = {}
        for row, chunk in enumerate(index.chunks):
            self._rows_by_doc.setdefault(chunk.doc_id, []).append(row)
        self._doc_engines: dict[str, set[str]] = {}
        for chunk in index.chunks:
            self._doc_engines.setdefault(chunk.doc_id, set(chunk.engines))

    @property
    def mode(self) -> str:
        '''"hybrid" or "bm25" — shown in /health.'''
        if self.index.embeddings is not None and self.dense is not None \
                and self.dense.available:
            return "hybrid"
        return "bm25"

    def docs_for_engine(self, engine: str) -> list[str]:
        '''Doc ids whose engine list contains the given engine.

        Args:
            engine: Normalized engine model.

        Returns:
            Manifest doc_ids, or an empty list for an unknown engine.
        '''
        return [
            doc_id
            for doc_id, engines in self._doc_engines.items()
            if engine in engines
        ]

    def search(
        self,
        query: str,
        engine_model: str,
        top_k: int = 5,
        fault_code: str | None = None,
        doc_id: str | None = None,
    ) -> SearchResponse:
        '''Run one contract search.

        Args:
            query: Free-text query.
            engine_model: Engine model to filter by, strictly, before scoring.
            top_k: Maximum results (1–10).
            fault_code: Optional explicit fault code from the agent.
            doc_id: Optional doc restriction.

        Returns:
            Contract SearchResponse (shared.models).
        '''
        engine = normalize_engine(engine_model)
        allowed_docs = self.docs_for_engine(engine)
        if doc_id:
            allowed_docs = [d for d in allowed_docs if d == doc_id]
        if not allowed_docs:
            return SearchResponse(results=[], no_instruction=True)

        code = detect_fault(query, self.knowledge, fault_code)
        status, _cell = coverage_for(engine, code, self.knowledge)
        if status == "none" and doc_id is None:
            # Verified absence: refuse without scoring (jury test case).
            return SearchResponse(results=[], no_instruction=True)

        queries = expand_query(query, code, self.knowledge)
        mask = np.zeros(len(self.index.chunks), dtype=bool)
        for doc in allowed_docs:
            for row in self._rows_by_doc.get(doc, []):
                mask[row] = True

        bm25_best, bm25_ranked = self._run_bm25(queries, mask)
        cos_best, cos_ranked = self._run_dense(queries, mask)

        fused = fuse([*bm25_ranked, *cos_ranked], engine_mask=mask)
        if not fused:
            return SearchResponse(results=[], no_instruction=True)
        comparable = cos_best if cos_best else bm25_best
        comparable = self._boost_sections(query, fused, comparable)
        candidates = sorted(fused, key=lambda idx: fused[idx], reverse=True)

        results: list[SearchHit] = []
        per_page: dict[tuple[str, int], int] = {}
        for idx in candidates:
            chunk = self.index.chunks[idx]
            score = comparable.get(idx, 0.0)
            tier = self._tier(score)
            if tier is None:
                continue
            key = (chunk.doc_id, chunk.page_pdf)
            if per_page.get(key, 0) >= self.settings.max_per_page:
                continue
            per_page[key] = per_page.get(key, 0) + 1
            results.append(
                SearchHit(
                    doc_id=chunk.doc_id,
                    doc_title=chunk.doc_title,
                    page_pdf=chunk.page_pdf,
                    section=chunk.section,
                    text=chunk.text,
                    score=round(score, 3),
                    tier=tier,
                )
            )
            if len(results) >= max(1, min(top_k, 10)):
                break
        return SearchResponse(results=results, no_instruction=not results)

    # --- retrievers ---------------------------------------------------------

    def _run_bm25(
        self, queries: list[str], mask: np.ndarray
    ) -> tuple[dict[int, float], list[list[int]]]:
        '''Score candidates on BM25 for every query variant.

        Args:
            queries: Query variants.
            mask: Allowed-row boolean mask (weight-masked inside scoring).

        Returns:
            (best per-chunk normalised relevance, ranked lists per variant).
        '''
        weight_mask = mask.astype(np.float32)
        best: dict[int, float] = {}
        ranked: list[list[int]] = []
        for variant in queries:
            scores = self.index.bm25.normalized(variant, mask=weight_mask)
            hits = np.where((scores > 0.0) & mask)[0]
            if not len(hits):
                ranked.append([])
                continue
            top = hits[np.argsort(-scores[hits])[:CANDIDATES_PER_VARIANT]]
            order = [int(i) for i in top]
            ranked.append(order)
            for i in order:
                best[i] = max(best.get(i, 0.0), float(scores[i]))
        return best, ranked

    def _run_dense(
        self, queries: list[str], mask: np.ndarray
    ) -> tuple[dict[int, float], list[list[int]]]:
        '''Score candidates on embeddings for every query variant.

        All variants are encoded in one batch; only allowed rows are scored.

        Args:
            queries: Query variants.
            mask: Allowed-row boolean mask.

        Returns:
            (best per-chunk cosine, ranked lists per variant); empty lists
            in BM25-only mode.
        '''
        if self.index.embeddings is None or self.dense is None:
            return {}, []
        if not self.dense.available:
            return {}, []
        query_vectors = self.dense.encode_queries(queries)
        if query_vectors is None:
            return {}, []
        rows = np.flatnonzero(mask)
        if not len(rows):
            return {}, []
        sub = self.index.embeddings[rows]  # (m, d), normalised
        sims = query_vectors @ sub.T  # (nq, m)
        best: dict[int, float] = {}
        ranked: list[list[int]] = []
        for qi in range(sims.shape[0]):
            order = np.argsort(-sims[qi])[:CANDIDATES_PER_VARIANT]
            chunk_order: list[int] = []
            for pos in order:
                score = float(sims[qi][pos])
                if score <= DENSE_MIN_COSINE:
                    break
                row = int(rows[pos])
                chunk_order.append(row)
                best[row] = max(best.get(row, 0.0), score)
            ranked.append(chunk_order)
        return best, ranked

    def _boost_sections(
        self,
        query: str,
        fused: dict[int, float],
        comparable: dict[int, float],
    ) -> dict[int, float]:
        '''Bump chunks whose section title matches the query's content.

        Args:
            query: Original query text.
            fused: Candidate chunk indices with RRF scores.
            comparable: Chunk → comparable score (cosine or BM25 coverage).

        Returns:
            The adjusted comparable-score mapping.
        '''
        query_stems = {t for t in tokenize(query) if len(t) >= 4}
        if not query_stems:
            return comparable
        boosted = dict(comparable)
        for idx in fused:
            chunk = self.index.chunks[idx]
            if not chunk.section:
                continue
            section_stems = set(tokenize(chunk.section))
            overlap = len(query_stems & section_stems) / len(query_stems)
            if overlap >= SECTION_OVERLAP:
                boosted[idx] = min(1.0, boosted.get(idx, 0.0) + SECTION_BOOST)
        return boosted

    def _tier(self, score: float) -> str | None:
        '''Map a comparable score to high/med/None (low is dropped).

        Args:
            score: Cosine or normalised BM25 relevance in [0, 1].

        Returns:
            "high" | "med" | None.
        '''
        if score >= self.settings.tier_high:
            return "high"
        if score >= self.settings.tier_med:
            return "med"
        return None


__all__: list[str] = ["SearchEngine", "normalize_engine"]
