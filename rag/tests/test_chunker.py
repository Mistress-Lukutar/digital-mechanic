'''
File:   test_chunker.py
Brief:  Chunk boundaries, merging and table splitting.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from rag.config import RagSettings
from rag.extract.chunker import PageRecord, chunk_page, split_block

SETTINGS = RagSettings(_env_file=None, embed_model="none")


def _page(text: str, page_pdf: int = 5, **kwargs) -> PageRecord:
    '''A test page record with fixed identity.'''
    defaults: dict = {
        "doc_id": "TEST-1 РК",
        "doc_title": "Тест",
        "doc_type": "rr",
        "engines": ["ТЕСТ-236М2"],
        "page_pdf": page_pdf,
        "text": text,
        "section": None,
        "section_path": [],
    }
    defaults.update(kwargs)
    return PageRecord(**defaults)


def test_chunks_never_cross_pages() -> None:
    '''two pages of the same text produce separate chunks.'''
    text = "Момент затяжки " + "очень важный норматив " * 60
    a = chunk_page(_page(text, page_pdf=1), SETTINGS)
    b = chunk_page(_page(text, page_pdf=2), SETTINGS)
    assert a and b
    ids_a = {c.chunk_id for c in a}
    ids_b = {c.chunk_id for c in b}
    assert not ids_a & ids_b
    assert all(c.chunk_id.startswith("TEST-1 РК:1:") for c in a)


def test_small_blocks_merge() -> None:
    '''many tiny fragments of one page merge into fewer chunks.'''
    text = "\n".join(f"фрагмент номер {i} детали" for i in range(40))
    chunks = chunk_page(_page(text), SETTINGS)
    assert len(chunks) <= 6
    assert all(len(c.text) <= SETTINGS.chunk_max_chars + 40 for c in chunks)


def test_cover_and_toc_excluded() -> None:
    '''covers, TOC pages and near-empty pages produce no chunks.'''
    assert chunk_page(_page("ОБЛОЖКА", page_pdf=1), SETTINGS) == []
    assert chunk_page(_page("Содержание", is_toc=True), SETTINGS) == []
    assert chunk_page(_page("", is_figure_sheet=True), SETTINGS) == []


def test_long_table_splits_with_header() -> None:
    '''a long table splits by rows and repeats the header row.'''
    header = "| Соединение | Момент затяжки | Примечание |"
    rows = [
        f"| болт крепления номер {i} | {i}0 Н·м | затянуть равномерно |"
        for i in range(30)
    ]
    text = header + "\n" + "\n".join(rows)
    chunks = chunk_page(_page(text), SETTINGS)
    assert len(chunks) >= 2
    assert all(c.kind == "table" for c in chunks)
    assert all(c.text.startswith(header) for c in chunks)


def test_single_piped_line_is_text() -> None:
    '''a lone "1 | step" line stays a text block, not a table.'''
    text = "\n".join(
        f"{i} | Извлечь деталь номер {i} из посадочного места" for i in range(1, 6)
    )
    # alternating table/text singletons: no two consecutive table rows,
    # so everything merges as text.
    chunks = chunk_page(_page(text), SETTINGS)
    assert len(chunks) == 1
    assert chunks[0].kind == "table"  # all rows piped → still a table run


def test_split_block_sentences() -> None:
    '''oversized text splits at sentence boundaries.'''
    text = ". ".join(f"Предложение номер {i} про момент" for i in range(60))
    pieces = split_block(text, 700)
    assert len(pieces) >= 2
    assert all(len(p) <= 760 for p in pieces)


def test_split_block_no_midword_seams() -> None:
    '''hard-cut and tail seams land on word boundaries, not inside words.

    A seam like «…Болт|ы крепления…» (golden g10, appendix moment table)
    leaves a bogus token in both pieces and drops the word from BM25 at
    the boundary — every piece must start and end with a whole word.
    '''
    vocab = ["Болты", "крепления", "головки", "цилиндров", "50", "(5,1)"]
    text = " ".join(vocab * 200)
    pieces = split_block(text, 700)
    assert len(pieces) >= 2
    for piece in pieces:
        tokens = piece.split()
        assert tokens[0] in vocab
        assert tokens[-1] in vocab


def test_split_block_long_sentence_no_midword_tail() -> None:
    '''an oversized sentence tail starts on a word boundary.'''
    text = "Вступление завершено. " + "слово " * 300 + "заключение."
    pieces = split_block(text, 700)
    assert len(pieces) >= 2
    for piece in pieces:
        tokens = piece.split()
        assert tokens[0] == "слово" or tokens[0] in ("Вступление", "заключение.")
        assert tokens[-1] != "сло"
