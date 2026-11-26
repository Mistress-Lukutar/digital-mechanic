'''
File:   test_textnorm.py
Brief:  Normalisation rules: hyphens, soft hyphens, ranges, letter spacing.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from rag.extract.textnorm import normalize_page_text


def test_hyphen_break_lower() -> None:
    '''lowercase + hyphen + newline joins without the hyphen.'''
    assert "внимательно" in normalize_page_text("внима-\nтельно смотрим")


def test_hyphen_break_upper() -> None:
    '''all-caps hyphen break joins without the hyphen.'''
    assert "АГРЕГАТА" in normalize_page_text("АГРЕ-\nГАТА")


def test_prefix_break_keeps_hyphen() -> None:
    '''model prefixes keep their hyphen across a break.'''
    assert "ЯМЗ-5362" in normalize_page_text("ЯМЗ-\n5362 нового образца")


def test_soft_hyphen_becomes_dash() -> None:
    '''U+00AD from some font runs is treated as a regular hyphen.'''
    text = "вертикальные 430\u00ad470 (43\u00ad47)"
    normalized = normalize_page_text(text)
    assert "***REMOVED***" in normalized
    assert "***REMOVED***" in normalized


def test_range_space_normalisation() -> None:
    '''"***REMOVED***" collapses to "***REMOVED***"; en dash unifies.'''
    assert "***REMOVED***" in normalize_page_text("***REMOVED***")
    assert "***REMOVED***" in normalize_page_text("430–470")
    assert "***REMOVED***" in normalize_page_text("***REMOVED***")  # ellipsis kept


def test_letter_spacing_joined() -> None:
    '''letter-spaced headings collapse into words.'''
    assert "РЕЗЬБОВЫХ" in normalize_page_text("Р Е З Ь Б О В Ы Х соединений")


def test_letter_spacing_leaves_words_alone() -> None:
    '''ordinary text is untouched; short runs stay apart.'''
    text = "М10 гайка и 4 болта"
    assert normalize_page_text(text) == text
