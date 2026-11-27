'''
File:   layout.py
Brief:  Coordinate-based reading order reconstruction for manual pages.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

``page.get_text()`` returns words in PDF-object order, which is scrambled in
the 236 RE tables ("− вертикальные 4 ... 415-455 ... 1-45)"). This module
rebuilds the visual order: words are derotated, grouped into visual lines by
the y-centre, sorted by x inside a line, and joined with gap-aware rules:

- gap below ``MICRO_GAP_RATIO * height``  → words glued without a space
  (the layer stores broken words like "ЗАТ" + "Я" + "ЖКИ" with zero gaps);
- gap above ``COLUMN_GAP_RATIO * height`` → column boundary, rendered " | "
  (table rows such as "− вертикальные | 415-455 (41-45)");
- otherwise → a single space.

Tables drawn with ruled lines are handled by :mod:`rag.extract.tables`, which
replaces their bbox with markdown before this module runs.
'''

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

MICRO_GAP_RATIO = 0.12
COLUMN_GAP_RATIO = 1.5
LINE_OVERLAP = 0.55
# A word this much taller than wide is written vertically (defect-map
# labels in the 236 RK manual are rotated 90° inside an upright page).
# The minimum height keeps narrow one-letter words ("р", "4", "(") in the
# horizontal flow — real rotated labels are long.
_VERTICAL_ASPECT = 2.2
_VERTICAL_MIN_HEIGHT = 15.0


@dataclass
class Word:
    '''One word with its derotated bounding rectangle.'''

    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        '''Word height, guarded against degenerate rectangles.'''
        return max(self.y1 - self.y0, 0.5)

    @property
    def y_center(self) -> float:
        '''Vertical centre of the word.'''
        return (self.y0 + self.y1) / 2


@dataclass
class Line:
    '''One visual line: joined text plus its vertical extent.'''

    text: str
    y0: float
    y1: float

    @property
    def y_center(self) -> float:
        '''Vertical centre of the line.'''
        return (self.y0 + self.y1) / 2


def page_words(page: pymupdf.Page) -> list[Word]:
    '''Extract words of *page* in derotated coordinates.

    PyMuPDF reports word rectangles in the unrotated coordinate system even
    for pages with a /Rotate flag; multiplying by ``derotation_matrix``
    maps them back to what a reader sees. Ten pages of the 236 RE manual
    are rotated by 90°, so this matters.

    Args:
        page: Opened PyMuPDF page.

    Returns:
        Word list in reader-visual coordinates.
    '''
    matrix = page.derotation_matrix
    words: list[Word] = []
    for x0, y0, x1, y1, text, *_rest in page.get_text("words"):
        rect = pymupdf.Rect(x0, y0, x1, y1) * matrix
        words.append(Word(text=text, x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1))
    return words


def group_lines(words: list[Word]) -> list[list[Word]]:
    '''Group words into visual lines by their vertical centre.

    Words arrive in arbitrary object order; sorting by the y-centre makes
    each visual row of the page (including table rows where the value sits
    to the right) emerge as one group.

    Args:
        words: Derotated words, any order.

    Returns:
        Line groups; each group is sorted by ``x0``.
    '''
    ordered = sorted(words, key=lambda w: w.y_center)
    lines: list[list[Word]] = []
    current: list[Word] = []
    center = 0.0
    for word in ordered:
        if current and abs(word.y_center - center) > LINE_OVERLAP * max(
            word.height, current[-1].height
        ):
            lines.append(current)
            current = []
        if not current:
            center = word.y_center
        current.append(word)
    if current:
        lines.append(current)
    for line in lines:
        line.sort(key=lambda w: w.x0)
    return lines


def assemble_line(line: list[Word]) -> str:
    '''Join the words of one visual line with gap-aware separators.

    Args:
        line: Words of one line sorted by ``x0``.

    Returns:
        Line text with zero-gap words glued, wide gaps marked " | ".
    '''
    parts: list[str] = []
    previous: Word | None = None
    for word in line:
        if previous is not None:
            gap = word.x0 - previous.x1
            height = max(word.height, previous.height)
            if gap <= MICRO_GAP_RATIO * height:
                parts.append("")  # broken word: glue without a space
            elif gap >= COLUMN_GAP_RATIO * height:
                parts.append(" | ")
            else:
                parts.append(" ")
        parts.append(word.text)
        previous = word
    return "".join(parts).strip()


def _is_vertical(word: Word) -> bool:
    '''True when the word is written top-to-bottom instead of left-to-right.

    Args:
        word: Derotated word.

    Returns:
        True for vertical (rotated) text words.
    '''
    width = max(word.x1 - word.x0, 0.5)
    height = word.y1 - word.y0
    return height >= _VERTICAL_MIN_HEIGHT and height > _VERTICAL_ASPECT * width


def _vertical_columns(words: list[Word]) -> list[Line]:
    '''Group vertical words into columns and read them top-to-bottom.

    Defect-map column labels ("Возможные неисправности", "Твердость")
    are written vertically; grouping by x-centre reconstructs them as
    readable lines instead of one-character noise.

    Args:
        words: Vertical words (see :func:`_is_vertical`).

    Returns:
        One line per column, words joined top-to-bottom.
    '''
    if not words:
        return []
    ordered = sorted(words, key=lambda w: w.x0)
    columns: list[list[Word]] = []
    current: list[Word] = []
    center = 0.0
    for word in ordered:
        c = (word.x0 + word.x1) / 2
        width = max(word.x1 - word.x0, 1.0)
        if current and abs(c - center) > 1.2 * width:
            columns.append(current)
            current = []
        if not current:
            center = c
        current.append(word)
    if current:
        columns.append(current)
    lines: list[Line] = []
    for column in columns:
        column.sort(key=lambda w: w.y0)
        parts: list[str] = []
        previous: Word | None = None
        for word in column:
            if previous is not None:
                gap = word.y0 - previous.y1
                width = max(word.x1 - word.x0, previous.x1 - previous.x0, 1.0)
                if gap <= MICRO_GAP_RATIO * width:
                    parts.append("")  # one label wrapped across rows
                else:
                    parts.append(" ")
            parts.append(word.text)
            previous = word
        text = "".join(parts).strip()
        if text:
            lines.append(
                Line(
                    text=text,
                    y0=min(w.y0 for w in column),
                    y1=max(w.y1 for w in column),
                )
            )
    return lines


def page_lines(
    page: pymupdf.Page, exclude: list[pymupdf.Rect] | None = None
) -> list[Line]:
    '''Reconstruct the visual lines of *page* in reading order.

    Words whose centre falls inside an *exclude* rectangle are dropped
    (used to keep ruled tables from being read twice). Horizontal lines
    come first (top-to-bottom); vertical label columns are appended after
    them so their text stays searchable without breaking the flow.

    Args:
        page: Opened PyMuPDF page.
        exclude: Optional word-rects to skip (table bboxes).

    Returns:
        Lines in reading order with vertical extents for the running
        header/footer detection.
    '''
    words = page_words(page)
    if exclude:
        def kept(w: Word) -> bool:
            centre = pymupdf.Point((w.x0 + w.x1) / 2, (w.y0 + w.y1) / 2)
            return not any(rect.contains(centre) for rect in exclude)
        words = [w for w in words if kept(w)]
    horizontal = [w for w in words if not _is_vertical(w)]
    vertical = [w for w in words if _is_vertical(w)]
    result: list[Line] = []
    for group in group_lines(horizontal):
        text = assemble_line(group)
        if not text:
            continue
        result.append(
            Line(text=text, y0=min(w.y0 for w in group), y1=max(w.y1 for w in group))
        )
    result.extend(_vertical_columns(vertical))
    return result


__all__: list[str] = [
    "COLUMN_GAP_RATIO",
    "LINE_OVERLAP",
    "MICRO_GAP_RATIO",
    "Line",
    "Word",
    "assemble_line",
    "group_lines",
    "page_lines",
    "page_words",
]
