'''
File:   test_index.py
Brief:  Tokenizer, BM25 index, store roundtrip.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from pathlib import Path

import numpy as np

from rag.index.bm25 import BM25Index
from rag.index.tokenizer import normalize_text, tokenize


def test_tokenize_keeps_designations() -> None:
    '''designations and ranges stay whole and gain expansions.'''
    tokens = tokenize("Момент затяжки ЯМЗ-536, зазор 0,26-0,32 мм")
    assert "ямз-536" in tokens
    assert "ямз" in tokens
    assert "536" in tokens
    assert "0,26-0,32" in tokens
    assert "0,26" in tokens
    assert "0,32" in tokens


def test_tokenize_stems_and_fixes_typo() -> None:
    '''Cyrillic words stem; the ЯМ3 layer typo is corrected.'''
    tokens = tokenize("подшипников ЯМ3 крышек")
    assert "подшипник" in tokens
    assert "крышек" in tokens
    assert "ямз" in tokens
    assert "ям3" not in tokens


def test_normalize_text() -> None:
    '''lowercase, ё→е.'''
    assert normalize_text("Ёлки ЗАТЯЖКИ") == "елки затяжки"


def test_bm25_mask_and_roundtrip(tmp_path: Path) -> None:
    '''scores respect the engine mask; save/load keeps the vocabulary.'''
    docs = [
        tokenize("момент затяжки крышек коренных подшипников"),
        tokenize("регулировка тепловых зазоров клапанов"),
        tokenize("тепловые зазоры клапанного механизма"),
    ]
    engines = [["ЯМЗ-236М2"], ["ЯМЗ-536"], ["ЯМЗ-536"]]
    index = BM25Index.build(docs, engines)

    mask_236 = index.doc_mask_engines["ЯМЗ-236М2"].astype(np.float32)
    scores = index.normalized("момент затяжки подшипников", mask=mask_236)
    assert scores[0] > 0
    assert scores[1] == 0 and scores[2] == 0  # other engines: strictly zero
    assert 0.0 < scores[0] <= 1.0

    index.save(tmp_path / "bm25")
    loaded = BM25Index.load(tmp_path / "bm25")
    again = loaded.normalized("момент затяжки подшипников", mask=mask_236)
    assert np.allclose(again, scores)


def test_engine_search_contract(engine) -> None:
    '''end-to-end: filtering, refusal, honest empty result.'''
    resp = engine.search("момент затяжки крышек коренных подшипников", "Тест-236М2")
    assert not resp.no_instruction
    assert resp.results
    hit = resp.results[0]
    assert hit.doc_id == "TEST-1 РК"
    assert hit.page_pdf == 3
    assert hit.tier in ("high", "med")
    assert 0.0 < (hit.score or 0) <= 1.0
    # foreign engine → refusal
    foreign = engine.search("момент затяжки", "Другой-Двигатель")
    assert foreign.no_instruction and not foreign.results
    # "цепь стартера" must NOT trigger the F14 refusal
    ok = engine.search("цепь стартера", "Тест-236М2")
    assert not ok.no_instruction


def test_engine_f14_refusal(engine) -> None:
    '''the verified-none cell refuses the fault topic query.'''
    from rag.knowledge.loader import CoverageStatus

    # The synthetic engine has no matrix row; emulate a verified none cell.
    engine.knowledge.coverage["ТЕСТ-236М2"] = {
        "F14": CoverageStatus(status="none", note="test")
    }
    resp = engine.search("цепь грм гидронатяжитель", "Тест-236М2")
    assert resp.no_instruction and not resp.results
    # A query without the fault topic is NOT refused by the same cell.
    ok = engine.search("момент затяжки крышек", "Тест-236М2")
    assert not ok.no_instruction
