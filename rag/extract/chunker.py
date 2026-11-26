'''
File:   chunker.py
Brief:  Page-bounded chunks for indexing.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Chunks never cross a page: a fact on the second page cited with the first
page's number is a wrong citation, and citations are what the jury checks.
A page up to ``chunk_max_chars`` becomes one chunk; longer pages split at
paragraph boundaries, then at sentence boundaries with overlap. Table rows
(lines containing " | ") form table blocks; a long table splits by rows with
its header row repeated in every part.
'''

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from rag.config import RagSettings

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# Minimum table row count before splitting a table block by rows.
TABLE_SPLIT_ROWS = 12


@dataclass
class PageRecord:
    '''Input page as stored in pages.jsonl.'''

    doc_id: str
    doc_title: str
    doc_type: str
    engines: list[str]
    page_pdf: int
    text: str
    section: str | None
    section_path: list[str]
    is_toc: bool = False
    is_figure_sheet: bool = False


@dataclass
class Chunk:
    '''One indexable chunk, strictly inside a single page.'''

    chunk_id: str
    doc_id: str
    doc_title: str
    doc_type: str
    engines: list[str]
    page_pdf: int
    section: str | None
    section_path: list[str]
    kind: str  # "text" | "table"
    text: str
    text_hash: str

    @property
    def embed_text(self) -> str:
        '''Text with a document/section context prefix for embeddings.'''
        context = self.doc_title
        if self.section:
            context = f"{self.doc_title} › {self.section}"
        return f"{context}\n{self.text}"


def _text_hash(text: str) -> str:
    '''Stable short hash of chunk text (embedding cache key).'''
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def split_block(text: str, max_chars: int) -> list[str]:
    '''Split one text block into pieces within *max_chars*.

    Splits prefer paragraphs, then sentences; the last resort is a hard cut
    with a small overlap so numbers at the seam stay searchable.

    Args:
        text: Block text without internal newlines-breaking structure.
        max_chars: Maximum piece length.

    Returns:
        Non-empty pieces.
    '''
    if len(text) <= max_chars:
        return [text]
    paragraphs = _PARAGRAPH_BREAK.split(text)
    if len(paragraphs) > 1:
        pieces: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                if current:
                    pieces.append(current)
                    current = ""
                pieces.extend(split_block(paragraph, max_chars))
                continue
            candidate = f"{current}\n{paragraph}" if current else paragraph
            if len(candidate) <= max_chars:
                current = candidate
                continue
            pieces.append(current)
            current = paragraph
        if current:
            pieces.append(current)
        return [p for p in pieces if p.strip()]
    sentences = _SENTENCE_BOUNDARY.split(text)
    if len(sentences) > 1:
        pieces = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}" if current else sentence
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                pieces.append(current)
            current = sentence[-max_chars:] if len(sentence) > max_chars else sentence
        if current:
            pieces.append(current)
        return [p for p in pieces if p.strip()]
    # Hard cut with overlap.
    step = max_chars - 60
    return [text[start : start + max_chars] for start in range(0, len(text), step)]


def _split_table_rows(rows: list[str], max_chars: int) -> list[str]:
    '''Split table rows into parts within *max_chars*, repeating the header.

    Args:
        rows: Markdown table rows ("| a | b |").
        max_chars: Maximum part length.

    Returns:
        Table parts, each including the header row.
    '''
    header = rows[0]
    parts: list[str] = []
    current: list[str] = [header]
    size = len(header)
    for row in rows[1:]:
        if size + len(row) + 1 > max_chars and len(current) > 1:
            parts.append("\n".join(current))
            current = [header]
            size = len(header)
        current.append(row)
        size += len(row) + 1
    if len(current) > 1:
        parts.append("\n".join(current))
    return parts


def _blocks_of(text: str) -> list[tuple[str, str]]:
    '''Group page lines into (kind, block) pairs.

    Contiguous runs of " | "-rows (two or more) form "table" blocks; a
    single piped line (procedure step numbering "1 | Извлечь ...") stays
    in the text flow, otherwise alternating kinds would shred the page
    into one-line blocks.

    Args:
        text: Page text.

    Returns:
        List of (kind, block text) in reading order.
    '''
    lines = [line.rstrip() for line in text.split("\n")]
    # First pass: mark table rows.
    kinds = ["table" if " | " in line else "text" for line in lines]
    # Second pass: isolated table marks become text.
    for i, kind in enumerate(kinds):
        if kind != "table":
            continue
        prev_table = i > 0 and kinds[i - 1] == "table"
        next_table = i + 1 < len(kinds) and kinds[i + 1] == "table"
        if not (prev_table or next_table):
            kinds[i] = "text"
    blocks: list[tuple[str, str]] = []
    buf: list[str] = []
    kind = "text"
    for line, line_kind in zip(lines, kinds, strict=False):
        if not line:
            if buf:
                blocks.append((kind, "\n".join(buf)))
                buf = []
            kind = "text"
            continue
        if buf and line_kind != kind:
            blocks.append((kind, "\n".join(buf)))
            buf = []
        kind = line_kind
        buf.append(line)
    if buf:
        blocks.append((kind, "\n".join(buf)))
    return blocks


def chunk_page(page: PageRecord, settings: RagSettings) -> list[Chunk]:
    '''Split one page into chunks, never crossing the page boundary.

    Blocks accumulate into chunks up to ``chunk_max_chars`` (defect-map
    pages produce many tiny fragments that belong together); oversized
    blocks split by paragraphs/sentences, tables by rows with a repeated
    header.

    Args:
        page: Page record with cleaned text and structure metadata.
        settings: RAG settings (chunk size cap).

    Returns:
        Chunks in reading order; empty for cover/TOC/near-empty pages.
    '''
    if page.is_toc or page.is_figure_sheet:
        return []
    if page.page_pdf == 1 and len(page.text.strip()) < 200:
        return []  # cover page
    if len(page.text.strip()) < 20:
        return []

    # First pass: split oversized blocks into pieces.
    pieces: list[tuple[str, str]] = []
    for kind, block in _blocks_of(page.text):
        if kind == "table":
            rows = [r for r in block.split("\n") if r.strip()]
            if len(rows) >= TABLE_SPLIT_ROWS:
                pieces.extend(
                    ("table", part) for part in _split_table_rows(
                        rows, settings.chunk_max_chars
                    )
                )
                continue
        pieces.extend(("table" if kind == "table" else "text", piece)
                      for piece in split_block(block, settings.chunk_max_chars))

    # Second pass: merge small neighbouring pieces into one chunk.
    chunks: list[Chunk] = []

    def emit(text: str, kind: str) -> None:
        '''Append one chunk with stable ids.'''
        chunks.append(
            Chunk(
                chunk_id=f"{page.doc_id}:{page.page_pdf}:{len(chunks)}",
                doc_id=page.doc_id,
                doc_title=page.doc_title,
                doc_type=page.doc_type,
                engines=list(page.engines),
                page_pdf=page.page_pdf,
                section=page.section,
                section_path=list(page.section_path),
                kind=kind,
                text=text,
                text_hash=_text_hash(text),
            )
        )

    buf: list[str] = []
    size = 0
    buf_kind = "text"
    for kind, piece in pieces:
        if not piece.strip():
            continue
        if buf and size + len(piece) + 1 > settings.chunk_max_chars:
            emit("\n".join(buf), buf_kind)
            buf = []
            size = 0
            buf_kind = "text"
        buf.append(piece)
        size += len(piece) + 1
        if kind == "table":
            buf_kind = "table"
    if buf:
        emit("\n".join(buf), buf_kind)
    return chunks


__all__: list[str] = [
    "Chunk",
    "PageRecord",
    "TABLE_SPLIT_ROWS",
    "chunk_page",
    "split_block",
]
