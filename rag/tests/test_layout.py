'''
File:   test_layout.py
Brief:  Reading-order reconstruction on synthetic pages.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

import pymupdf

from rag.extract.layout import page_lines
from rag.tests.synth import put_text


def test_broken_words_glue(tmp_path) -> None:
    '''zero-gap word pieces of one visual line glue into whole words.'''
    path = tmp_path / "p.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    # "ЗАТЯЖКИ" written as three zero-gap pieces, like the 236 RE layer.
    put_text(page, (100, 100), "ЗАТ", 11)
    put_text(page, (121.2, 100), "Я", 11)
    put_text(page, (127.4, 100), "ЖКИ", 11)
    put_text(page, (170, 100), "ОСНОВНЫХ", 11)
    doc.save(str(path))
    doc.close()

    doc = pymupdf.open(str(path))
    lines = page_lines(doc[0])
    assert any("ЗАТЯЖКИ ОСНОВНЫХ" in line.text for line in lines)


def test_table_row_pipe(tmp_path) -> None:
    '''a wide column gap is rendered as " | " keeping row pairing.'''
    path = tmp_path / "p.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    put_text(page, (60, 100), "Болты крепления крышек коренных подшипников:", 11)
    put_text(page, (400, 100), "***REMOVED*** ***REMOVED***", 11)
    put_text(page, (60, 115), "Болты крепления крышек шатунов:", 11)
    put_text(page, (400, 115), "200-220 (20-22)", 11)
    doc.save(str(path))
    doc.close()

    doc = pymupdf.open(str(path))
    lines = page_lines(doc[0])
    # The arial test font may extract hyphens as U+00AD; compare prefixes.
    assert any(
        "подшипников: | 430" in line.text for line in lines
    ), [line.text for line in lines]
    assert any(
        "шатунов: | 200" in line.text for line in lines
    ), [line.text for line in lines]


def test_reading_order_top_to_bottom(tmp_path) -> None:
    '''lines come out in y order regardless of insertion order.'''
    path = tmp_path / "p.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    put_text(page, (60, 200), "вторая строка", 11)
    put_text(page, (60, 100), "первая строка", 11)
    doc.save(str(path))
    doc.close()

    doc = pymupdf.open(str(path))
    texts = [line.text for line in page_lines(doc[0])]
    assert texts.index("первая строка") < texts.index("вторая строка")
