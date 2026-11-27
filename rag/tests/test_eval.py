'''
File:   test_eval.py
Brief:  Eval runner: the overrefusal set reports refusal rate and hit@5.
Author: Demetrius242
Date:   2026-11-28
Version: v0.1.0

Runs the real runner over a tiny overrefusal.jsonl in a temp eval dir
against the synthetic BM25-only engine: one covered-cell question that
must be answered (gold page from the synthetic manual) and one question
on an unknown engine that always refuses. Issue #15.
'''

from __future__ import annotations

import json
from pathlib import Path

from rag.eval import run_eval

CASES = [
    {
        "qid": "s01",
        "engine": "Тест-236М2",
        "question": "Момент затяжки крышек коренных подшипников",
        "gold_pages": [{"doc_id": "TEST-1 РК", "page": 3}],
        "kind": "overrefusal",
    },
    {
        "qid": "s02",
        "engine": "Другой-Двигатель",  # unknown → honest refusal
        "question": "Момент затяжки крышек коренных подшипников",
        "gold_pages": [{"doc_id": "TEST-1 РК", "page": 3}],
        "kind": "overrefusal",
    },
]


def test_overrefusal_reports_refusal_rate_and_hit5(
    rag_settings, engine
) -> None:
    '''refusal_rate counts refusals; hit@5 counts gold-page hits; both
    go into the metrics of one run, failures name the refused qids.'''
    eval_dir = Path(rag_settings.eval_dir)
    eval_dir.mkdir(parents=True, exist_ok=True)
    path = eval_dir / "overrefusal.jsonl"
    path.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in CASES),
        encoding="utf-8",
    )

    metrics = run_eval(["overrefusal"], settings=rag_settings, engine=engine)
    result = metrics["overrefusal"]
    assert result["cases"] == 2
    assert result["refusal_rate"] == 0.5
    assert result["hit@5"] == 0.5
    assert result["hit@1"] == 0.5
    assert result["failures"] == ["s02: over-refusal (cell covered)"]
