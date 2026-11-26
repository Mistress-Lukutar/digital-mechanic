'''
File:   tables.py
Brief:  Ruled-line tables to markdown replacement.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

``page.find_tables()`` reliably finds tables drawn with ruled lines (236 RK
defect maps, 236 RE page 6) and returns their cells; tables without lines
(the fault and tightening-torque tables the jury asks about) are NOT found
by it and are instead reconstructed by :mod:`rag.extract.layout` as
"left | right" visual rows.

This module extracts lined tables as markdown blocks and removes their
words from the normal flow, so layout does not double-read them.
'''

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from rag.extract.layout import Line, page_lines

# Minimum accepted table shape.
MIN_ROWS = 2
MIN_COLS = 2


@dataclass
class TableBlock:
    '''A lined table extracted as markdown with its position on the page.'''

    markdown: str
    y_top: float
    bbox: pymupdf.Rect


def _extract_tables(page: pymupdf.Page) -> list[TableBlock]:
    '''Find lined tables on *page* and render them as markdown.

    Args:
        page: Opened PyMuPDF page. Note that ``find_tables`` works in
            displayed-page coordinates; on rotated pages (ten in the 236 RE
            manual) its bbox is not comparable with derotated word rects,
            so tables on rotated pages are skipped rather than mis-cut.

    Returns:
        Accepted table blocks, topmost first.
    '''
    if page.rotation:
        return []
    blocks: list[TableBlock] = []
    try:
        found = page.find_tables()
    except Exception:  # noqa: BLE001 - find_tables can raise on odd pages
        return blocks
    for table in found.tables:
        rows = table.extract()
        if len(rows) < MIN_ROWS or len(rows[0]) < MIN_COLS:
            continue
        md_rows: list[str] = []
        for row in rows:
            cells = [(cell or "").strip().replace("\n", " ") for cell in row]
            if not any(cells):
                continue
            md_rows.append("| " + " | ".join(cells) + " |")
        if len(md_rows) < MIN_ROWS:
            continue
        bbox = pymupdf.Rect(table.bbox)
        blocks.append(
            TableBlock(markdown="\n".join(md_rows), y_top=bbox.y0, bbox=bbox)
        )
    blocks.sort(key=lambda b: b.y_top)
    return blocks


def page_with_tables(page: pymupdf.Page) -> list[Line]:
    '''Return the page's visual lines with lined tables replaced by markdown.

    Each accepted table becomes a single multi-line pseudo-line placed at
    the table's top edge; words inside a table bbox are dropped from the
    flow so they are not read twice. Layout handles the horizontal/
    vertical split and reading order.

    Args:
        page: Opened PyMuPDF page.

    Returns:
        Lines in reading order, table markdown merged in.
    '''
    blocks = _extract_tables(page)
    if not blocks:
        return page_lines(page)
    lines = page_lines(page, exclude=[b.bbox for b in blocks])
    lines.extend(
        Line(text=block.markdown, y0=block.y_top, y1=block.y_top) for block in blocks
    )
    lines.sort(key=lambda line: line.y0)
    return lines


__all__: list[str] = ["MIN_COLS", "MIN_ROWS", "TableBlock", "page_with_tables"]
