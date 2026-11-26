'''
File:   synth.py
Brief:  Synthetic PDF builder for rag tests (no real manuals needed).
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Builds tiny PDFs with Cyrillic text using a system font when available and
a graceful ASCII fallback elsewhere, so the suite runs offline without the
copyrighted manuals.
'''

from __future__ import annotations

import json
from pathlib import Path

import pymupdf

# Candidate fonts with Cyrillic coverage, checked in order.
_FONT_CANDIDATES = (
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def _find_font() -> str | None:
    '''Return the first available Cyrillic-capable font file, if any.'''
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


_FONT_PATH = _find_font()


def put_text(
    page: pymupdf.Page, xy: tuple[float, float], text: str, size: float = 11.0
) -> None:
    '''Insert Cyrillic-capable text onto a page.

    Args:
        page: Target page.
        xy: Baseline start point.
        text: Text to insert.
        size: Font size.
    '''
    if _FONT_PATH:
        page.insert_text(xy, text, fontsize=size, fontname="f0", fontfile=_FONT_PATH)
    else:
        ascii_only = text.encode("ascii", "ignore").decode()
        page.insert_text(xy, ascii_only, fontsize=size)


def write_manual(
    path: Path,
    pages: list[list[tuple[tuple[float, float], str, float]]],
) -> None:
    '''Write a multi-page synthetic PDF.

    Args:
        path: Output PDF path.
        pages: Per page, a list of (xy, text, size) insertions.
    '''
    doc = pymupdf.open()
    for insertions in pages:
        page = doc.new_page(width=595, height=842)
        for xy, text, size in insertions:
            put_text(page, xy, text, size)
    doc.save(str(path))
    doc.close()


def write_manifest(path: Path, docs: list[dict]) -> None:
    '''Write a manuals manifest.json.

    Args:
        path: Target manifest.json path (directory must exist).
        docs: Document entries.
    '''
    path.write_text(
        json.dumps({"documents": docs}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


__all__: list[str] = ["put_text", "write_manifest", "write_manual"]
