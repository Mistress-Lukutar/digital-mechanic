'''
File:   fusion.py
Brief:  Result fusion (RRF) and the tier decision.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

BM25 scores are not comparable between queries, so ranked lists from the
lexical and (when available) dense retrievers are merged with Reciprocal
Rank Fusion. The reported score is the comparable quantity: the cosine of
the chunk in hybrid mode, or the IDF-normalised BM25 relevance otherwise.
'''

from __future__ import annotations

import numpy as np

RRF_K = 60


def fuse(
    ranked_lists: list[list[int]],
    engine_mask: np.ndarray | None = None,
) -> dict[int, float]:
    '''Merge ranked chunk lists with RRF.

    Args:
        ranked_lists: Chunk indices, best first, one list per query variant
            and per retriever.
        engine_mask: Optional boolean mask; masked chunks are dropped even
            if some list contains them (defence in depth: scoring is
            already masked, this guards the fusion inputs).

    Returns:
        chunk index → RRF score (higher is better).
    '''
    fused: dict[int, float] = {}
    for ranked in ranked_lists:
        for position, chunk_idx in enumerate(ranked):
            if engine_mask is not None and not engine_mask[chunk_idx]:
                continue
            fused[chunk_idx] = fused.get(chunk_idx, 0.0) + 1.0 / (
                RRF_K + position + 1
            )
    return fused


def order_candidates(
    fused: dict[int, float],
    comparable: dict[int, float],
) -> list[int]:
    '''Order fused candidates by their comparable score.

    Evaluated on the issue #14 eval sets and NOT used by the engine:
    comparable-first ordering lifts hit@1/MRR but lets saturated BM25
    pages (full query-term coverage) overtake dense-confirmed gold pages,
    dropping manual hit@5 below the hybrid baseline. Kept as a utility
    for future experiments; the engine orders by RRF.

    Args:
        fused: chunk index → RRF score (ties broken by it).
        comparable: chunk index → cosine or normalised BM25 relevance.

    Returns:
        Chunk indices, best first.
    '''
    return sorted(
        fused,
        key=lambda idx: (comparable.get(idx, 0.0), fused[idx]),
        reverse=True,
    )


__all__: list[str] = ["RRF_K", "fuse", "order_candidates"]
