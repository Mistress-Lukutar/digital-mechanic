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
    text = "вертикальные 415\u00ad455 (41\u00ad45)"
    normalized = normalize_page_text(text)
    assert "415-455" in normalized
    assert "(41-45)" in normalized


def test_range_space_normalisation() -> None:
    '''"95- 110" collapses to "95-110"; en dash unifies.'''
    assert "95-110" in normalize_page_text("95- 110")
    assert "415-455" in normalize_page_text("415–455")
    assert "12…15,7" in normalize_page_text("12…15,7")  # ellipsis kept


def test_letter_spacing_joined() -> None:
    '''letter-spaced headings collapse into words.'''
    assert "РЕЗЬБОВЫХ" in normalize_page_text("Р Е З Ь Б О В Ы Х соединений")


def test_letter_spacing_leaves_words_alone() -> None:
    '''ordinary text is untouched; short runs stay apart.'''
    text = "М10 гайка и 4 болта"
    assert normalize_page_text(text) == text


def test_glue_broken_words() -> None:
    '''space-broken fragments join when the sum is a corpus word.'''
    wordforms = {"подшипников": 40, "динамометрических": 12, "затяжки": 90}
    text = "по дшипнико в: затяжка динамометр ических ключей"
    glued = normalize_page_text(text, wordforms)
    assert "подшипников:" in glued
    assert "динамометрических" in glued


def test_glue_leaves_real_words_alone() -> None:
    '''two real words whose concatenation is not a word stay apart.'''
    wordforms = {"подшипников": 40, "коренных": 55, "подшипниковкоренных": 0}
    text = "крышек коренных подшипников"
    assert normalize_page_text(text, wordforms) == text


def test_glue_always_broken_words() -> None:
    '''words that never appear intact merge from frequent fragments.'''
    wordforms = {"динамометр": 5}  # only the nominative is intact
    fragments = {"динамометр": 20, "ических": 30}
    glued = normalize_page_text(
        "ключей динамометр ических", wordforms, fragments
    )
    assert "динамометрических" in glued


def test_glue_disabled_without_dictionary() -> None:
    '''no dictionary → no glue (plain normalisation).'''
    text = "по дшипнико в"
    assert normalize_page_text(text, None) == text
