'''
File:   passport.py
Brief:  Per-document passport: metadata, page statistics, recognition.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Reads the issued PDFs read-only and produces the per-document facts used by
ingest and setup: page count, text volume, figure sheets, rotated pages and
the designation fingerprint used to recognise a file when its name differs
(the hackathon bundle ships two manuals under Russian file names).
'''

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf


@dataclass
class DocPassport:
    '''Measured facts about one PDF file.'''

    path: str
    pages: int
    chars: int
    figure_sheets: int  # pages with almost no text
    rotated_pages: list[int]
    cover_text: str  # first-page text, for fingerprinting

    @property
    def designation(self) -> str | None:
        '''First document designation found on the cover pages, if any.'''
        return None


def measure(path: str) -> DocPassport:
    '''Measure one PDF file without writing anything.

    Args:
        path: Path of the PDF file.

    Returns:
        Measured passport.
    '''
    with pymupdf.open(path) as doc:
        page_count = doc.page_count
        chars = 0
        figure_sheets = 0
        rotated: list[int] = []
        for number, page in enumerate(doc, start=1):
            text = page.get_text()
            chars += len(text)
            if len(text.strip()) < 20:
                figure_sheets += 1
            if page.rotation:
                rotated.append(number)
        cover = doc[0].get_text()
        if page_count > 1:
            cover += "\n" + doc[1].get_text()
    return DocPassport(
        path=path,
        pages=page_count,
        chars=chars,
        figure_sheets=figure_sheets,
        rotated_pages=rotated,
        cover_text=cover,
    )


def matches_designation(passport: DocPassport, pattern: str) -> bool:
    '''Check the passport cover against a designation regex.

    Args:
        passport: Measured passport.
        pattern: Regex searched (case-insensitively) in the cover text.

    Returns:
        True when the designation appears on the first pages.
    '''
    return re.search(pattern, passport.cover_text, re.IGNORECASE) is not None


__all__: list[str] = ["DocPassport", "matches_designation", "measure"]
