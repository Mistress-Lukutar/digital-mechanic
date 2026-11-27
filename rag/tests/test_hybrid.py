'''
File:   test_hybrid.py
Brief:  Hybrid-mode regression: a BM25-only chunk survives the tier cut.
Author: Demetrius242
Date:   2026-11-28
Version: v0.1.0

The dense part is a scripted stub: every query encodes onto a unit vector
that matches only the distractor chunks, so the gold chunk stays found
only by BM25 (its cosine is 0.0, below DENSE_MIN_COSINE — it never enters
cos_best). The engine must still surface that chunk with its BM25 tier:
the comparable score is merged per chunk, not taken from one retriever
(issue #14 H1 — the old cos_best-or-bm25_best fallback zeroed it).
'''

from __future__ import annotations

import numpy as np
import pytest

from rag.search import SearchEngine


class _ScriptedDense:
    '''Stub of DenseIndex: every query encodes to one fixed unit vector.'''

    def __init__(self, vector: np.ndarray) -> None:
        self._vector = vector
        self.available = True

    def encode_queries(self, queries: list[str]) -> np.ndarray:
        return np.tile(self._vector, (len(queries), 1))


@pytest.fixture()
def hybrid_engine(engine) -> SearchEngine:
    '''The BM25-only engine upgraded to hybrid with a scripted dense part.

    Page-3 chunks embed onto e1, page-4 chunks onto e0; the stub encodes
    every query onto e0 — dense sees only page 4, BM25 sees everything.
    '''
    page3 = np.array([0.0, 1.0], dtype=np.float32)
    page4 = np.array([1.0, 0.0], dtype=np.float32)
    embeddings = np.zeros((len(engine.index.chunks), 2), dtype=np.float32)
    for row, chunk in enumerate(engine.index.chunks):
        embeddings[row] = page3 if chunk.page_pdf == 3 else page4
    engine.index.embeddings = embeddings
    engine.dense = _ScriptedDense(page4)
    return engine


def test_hybrid_mode_reports_hybrid(hybrid_engine) -> None:
    '''embeddings + available model → the engine is in hybrid mode.'''
    assert hybrid_engine.mode == "hybrid"


def test_bm25_only_chunk_survives_tier_cut(hybrid_engine) -> None:
    '''A chunk with no dense recall keeps its BM25 score in hybrid mode.'''
    resp = hybrid_engine.search(
        "момент затяжки крышек коренных подшипников", "Тест-236М2"
    )
    assert not resp.no_instruction
    assert resp.results, "everything dropped would mean the merge regressed"
    hit = next((h for h in resp.results if h.page_pdf == 3), None)
    assert hit is not None, "BM25-only chunk was dropped by the tier cut"
    assert hit.tier in ("high", "med")
    assert (hit.score or 0.0) >= 0.55
    # The dense distractors are still in the response (cosine 1.0).
    assert any(h.page_pdf == 4 for h in resp.results)


def test_bm25_only_number_query_survives(hybrid_engine) -> None:
    '''A «по цифре» query that dense cannot see still returns its page.'''
    resp = hybrid_engine.search("415-455", "Тест-236М2")
    assert not resp.no_instruction
    assert resp.results
    assert any(h.page_pdf == 3 for h in resp.results)
