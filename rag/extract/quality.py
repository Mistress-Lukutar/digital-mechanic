'''
File:   quality.py
Brief:  Text-layer quality metrics and the review report.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

The metric — the share of inter-word gaps below 12% of the font height —
shows WHERE the text layer is broken (the layout glue fixes most of it).
Pages with a high share are listed in the report for a human eye check;
the metric is a worklist, not a verdict.
'''

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import pymupdf

from rag.extract.layout import group_lines, page_words


@dataclass
class PageQuality:
    '''Quality measures of one page.'''

    page_pdf: int
    micro_gap_ratio: float  # share of gaps below MICRO_GAP_RATIO * height
    joins: int  # number of zero-gap glues layout performed
    status: str  # "ok" | "flagged"


def measure_page(page: pymupdf.Page) -> PageQuality:
    '''Measure the text layer of one page.

    Args:
        page: Opened PyMuPDF page.

    Returns:
        Per-page measures.
    '''
    total_gaps = 0
    micro = 0
    for group in group_lines(page_words(page)):
        for current, nxt in zip(group, group[1:], strict=False):
            gap = nxt.x0 - current.x1
            if gap <= 0.2:
                total_gaps += 1
                micro += 1
            elif gap > 0.2:
                total_gaps += 1
    ratio = micro / total_gaps if total_gaps >= 10 else 0.0
    status = "flagged" if ratio > 0.02 else "ok"
    return PageQuality(
        page_pdf=page.number + 1,
        micro_gap_ratio=round(ratio, 4),
        joins=micro,
        status=status,
    )


def measure_document(doc: pymupdf.Document) -> list[PageQuality]:
    '''Measure every page of a document.

    Args:
        doc: Opened PyMuPDF document.

    Returns:
        Per-page measures in page order.
    '''
    return [measure_page(doc[number]) for number in range(doc.page_count)]


def write_report(path: str, report: dict[str, list[PageQuality]]) -> None:
    '''Write the quality report as JSON.

    Args:
        path: Output JSON path.
        report: doc_id → page measures.
    '''
    payload = {
        doc_id: [asdict(q) for q in pages] for doc_id, pages in report.items()
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)


__all__: list[str] = ["PageQuality", "measure_document", "measure_page", "write_report"]
