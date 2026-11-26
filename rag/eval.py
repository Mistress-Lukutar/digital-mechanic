'''
File:   eval.py
Brief:  Evaluation runner over the committed question sets.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Runs the search engine in-process against the committed eval sets in
data/eval/ and prints hit@1/hit@5 (±1 page), MRR, the value check for the
golden set and the refusal rate for the negative set. Run before every
stage commit; the hit@5/MRR numbers go into the commit message.

    python -m rag.eval --set all
'''

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from rag.config import get_settings
from rag.index.dense import DenseIndex
from rag.index.store import read_current
from rag.knowledge.loader import load_knowledge
from rag.search import SearchEngine

logger = logging.getLogger(__name__)

# Page tolerance: sections routinely spill onto the next page.
PAGE_TOLERANCE = 1

_SET_FILES = {
    "golden": "golden.jsonl",
    "manual": "manual.jsonl",
    "negative": "negative.jsonl",
}


@dataclass
class EvalCase:
    '''One eval question.'''

    qid: str
    engine: str
    question: str
    gold_pages: list[dict] = field(default_factory=list)  # [{doc_id, page}]
    value: str | None = None
    kind: str = ""
    fault_code: str | None = None


def load_set(path: Path) -> list[EvalCase]:
    '''Load one JSONL question set.

    Args:
        path: JSONL file path.

    Returns:
        Parsed cases.
    '''
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        cases.append(
            EvalCase(
                qid=str(data["qid"]),
                engine=str(data["engine"]),
                question=str(data["question"]),
                gold_pages=list(data.get("gold_pages", [])),
                value=data.get("value"),
                kind=str(data.get("kind", "")),
                fault_code=data.get("fault_code"),
            )
        )
    return cases


def _page_hit(
    results: list,
    gold_pages: list[dict],
) -> int | None:
    '''1-based rank of the first result inside a gold page (or its range).

    Gold entries are {"doc_id", "page"} or {"doc_id", "page", "page_end"}
    for sections spanning many pages (the fault tables run 50 pages in
    536 RE): any page of the section is a correct answer, ±1 more.

    Args:
        results: SearchHit list, best first.
        gold_pages: Gold entries.

    Returns:
        Rank or None.
    '''
    for rank, hit in enumerate(results, start=1):
        for gold in gold_pages:
            page = int(gold["page"])
            page_end = int(gold.get("page_end", page))
            if (
                hit.doc_id == gold["doc_id"]
                and page - PAGE_TOLERANCE
                <= hit.page_pdf
                <= page_end + PAGE_TOLERANCE
            ):
                return rank
    return None


def _value_present(value: str, page_text: str) -> bool:
    '''Check that every number of the gold value appears in the page text.

    Numbers are compared with separators normalised (dashes and spaces
    collapse); a gold value like "430-470 (43-47)" requires "430-470" and
    "43-47" both to appear on the page.

    Args:
        value: Expected value string from the golden set.
        page_text: Full text of the retrieved page.

    Returns:
        True when all number tokens of the value are on the page.
    '''
    def tokens(text: str) -> list[str]:
        normalized = re.sub(r"[–—]", "-", text)
        normalized = re.sub(r"\s*-\s*", "-", normalized)
        return re.findall(r"\d+(?:[.,]\d+)?(?:-\d+(?:[.,]\d+)?)*", normalized)

    expected = tokens(value)
    if not expected:
        return True
    found = tokens(page_text)
    found_join = " | ".join(found)
    return all(token in found_join for token in expected)


def run_eval(
    sets: list[str],
    settings=None,
    engine: SearchEngine | None = None,
    verbose: bool = False,
) -> dict:
    '''Run the requested eval sets and return metrics.

    Args:
        sets: Subset of {"golden", "manual", "negative"}.
        settings: Settings override (tests).
        engine: Pre-built engine override (tests).
        verbose: Print per-question outcomes.

    Returns:
        Metrics dict with per-set and overall numbers.
    '''
    settings = settings or get_settings()
    if engine is None:
        stored = read_current(settings.data_dir, settings.index_version)
        if stored is None:
            raise SystemExit(
                "no index built — run: python -m rag.ingest (or rag.setup)"
            )
        knowledge = load_knowledge(Path(__file__).parent / "knowledge")
        dense = None
        if settings.embed_model not in ("", "none") and stored.embed_model:
            dense = DenseIndex(
                settings.embed_model, settings.data_dir / "emb_cache", settings.device
            )
        engine = SearchEngine(stored, knowledge, settings, dense)

    eval_dir = Path(settings.eval_dir)
    metrics: dict = {}
    for set_name in sets:
        file_name = _SET_FILES.get(set_name)
        if file_name is None:
            raise SystemExit(f"unknown eval set: {set_name}")
        path = eval_dir / file_name
        if not path.is_file():
            logger.warning("eval set missing: %s", path)
            metrics[set_name] = {"cases": 0}
            continue
        cases = load_set(path)
        metrics[set_name] = _run_set(set_name, cases, engine, verbose)
    return metrics


def _run_set(
    set_name: str,
    cases: list[EvalCase],
    engine: SearchEngine,
    verbose: bool,
) -> dict:
    '''Evaluate one set against the engine.

    Args:
        set_name: Set label.
        cases: Parsed cases.
        engine: Built search engine.
        verbose: Print per-question outcomes.

    Returns:
        Metrics dict.
    '''
    ranks: list[int] = []
    hits1 = 0
    hits5 = 0
    values_ok = 0
    values_checked = 0
    refusals = 0
    failures: list[str] = []
    for case in cases:
        response = engine.search(
            query=case.question,
            engine_model=case.engine,
            top_k=5,
            fault_code=case.fault_code,
        )
        if set_name == "negative":
            if response.no_instruction:
                refusals += 1
            else:
                top = response.results[0] if response.results else None
                failures.append(
                    f"{case.qid}: expected refusal, got "
                    f"{top.doc_id if top else '?'} p.{top.page_pdf if top else '?'}"
                )
            if verbose:
                print(f"  {case.qid}: refusal={response.no_instruction}")
            continue
        rank = _page_hit(response.results, case.gold_pages)
        if rank is not None:
            ranks.append(rank)
            hits5 += 1
            hits1 += rank == 1
        else:
            failures.append(f"{case.qid}: no gold page in top-5")
        if verbose:
            top = [
                f"{h.doc_id}:p{h.page_pdf}({h.tier},{h.score})"
                for h in response.results
            ]
            print(f"  {case.qid}: rank={rank} {' '.join(top)}")
        if set_name == "golden" and case.value:
            values_checked += 1
            # Any cited page carrying the value counts; check every match.
            value_ok = False
            matched: list[tuple[str, int]] = []
            for hit in response.results:
                for gold in case.gold_pages:
                    page = int(gold["page"])
                    page_end = int(gold.get("page_end", page))
                    if (
                        hit.doc_id == gold["doc_id"]
                        and page - PAGE_TOLERANCE
                        <= hit.page_pdf
                        <= page_end + PAGE_TOLERANCE
                    ):
                        matched.append((hit.doc_id, hit.page_pdf))
            for doc_id, page_pdf in matched:
                page_text = engine.index.page_text.get((doc_id, page_pdf), "")
                if _value_present(case.value, page_text):
                    value_ok = True
                    break
            if value_ok:
                values_ok += 1
            elif matched:
                failures.append(f"{case.qid}: value not on {matched}")
            else:
                failures.append(f"{case.qid}: value unchecked (page missed)")

    total = len(cases)
    result: dict = {"cases": total}
    if set_name == "negative":
        result["refusal_rate"] = round(refusals / total, 3) if total else None
    else:
        result["hit@1"] = round(hits1 / total, 3) if total else None
        result["hit@5"] = round(hits5 / total, 3) if total else None
        result["mrr"] = (
            round(sum(1.0 / r for r in ranks) / total, 3) if total else None
        )
    if set_name == "golden":
        result["value_checks"] = values_checked
        result["values_ok"] = values_ok if values_checked else None
    result["failures"] = failures[:20]
    return result


def main() -> None:
    '''CLI entry point.'''
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(
        prog="python -m rag.eval",
        description="Run the committed eval question sets against the index.",
    )
    parser.add_argument(
        "--set",
        default="all",
        choices=["all", "golden", "manual", "negative"],
        help="which set(s) to run",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    sets = ["golden", "manual", "negative"] if args.set == "all" else [args.set]
    metrics = run_eval(sets, verbose=args.verbose)
    for set_name, numbers in metrics.items():
        print(f"== {set_name} ==")
        for key, value in numbers.items():
            if key != "failures":
                print(f"  {key}: {value}")
        for failure in numbers.get("failures", []):
            print(f"  ! {failure}")


if __name__ == "__main__":
    main()
