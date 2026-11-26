'''
File:   test_structure.py
Brief:  Printed-TOC parsing, markdown flattening, offset detection.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from rag.extract.layout import Line
from rag.extract.structure import (
    _level_of,
    assign_page_sections,
    build_sections,
    detect_offset,
    parse_toc,
)


def _lines(texts: list[str]) -> list[Line]:
    '''Wrap plain strings as evenly spaced lines.'''
    return [
        Line(text=t, y0=float(i * 12), y1=float(i * 12 + 11))
        for i, t in enumerate(texts)
    ]


def test_parse_toc_multiline_record() -> None:
    '''a title continued on the next line and the number alone at the end.'''
    lines = _lines(
        [
            "Пуск двигателя с помощью электрофакельного",
            "устройства (ЭФУ) . . . . . . . . . .",
            "18",
            "Особенности зимней эксплуатации . . . . 20",
        ]
    )
    records = parse_toc(lines)
    assert (
        "Пуск двигателя с помощью электрофакельного устройства (ЭФУ)", 18
    ) in records
    assert ("Особенности зимней эксплуатации", 20) in records


def test_parse_toc_markdown_captured() -> None:
    '''a TOC captured by find_tables is flattened and parsed.'''
    lines = [
        Line(
            text=(
                "|  | Стр. |\n| ВНИМАНИЕ! | 4 |\n"
                "| ПРИМЕНЯЕМОСТЬ И ОСОБЕННОСТИ | 5 |\n"
                "| ТЕХНИЧЕСКАЯ ХАРАКТЕРИСТИКА | 26 |"
            ),
            y0=80.0,
            y1=200.0,
        ),
    ]
    records = parse_toc(lines)
    assert ("ВНИМАНИЕ!", 4) in records
    assert ("ПРИМЕНЯЕМОСТЬ И ОСОБЕННОСТИ", 5) in records
    assert ("ТЕХНИЧЕСКАЯ ХАРАКТЕРИСТИКА", 26) in records


def test_levels() -> None:
    '''numbering depth and caps decide levels.'''
    assert _level_of("1 Общие сведения") == 1
    assert _level_of("2.7 Требования к дефектации") == 2
    assert _level_of("5.10.5 Коромысла клапанов") == 3
    assert _level_of("ПРИЛОЖЕНИЕ В - Моменты затяжки") == 1
    assert _level_of("Регулировка клапанного механизма") == 2


def test_offset_detection() -> None:
    '''titles found one page after the printed number give offset +1.'''
    # Fake document: printed page 10 actually sits on PDF page 11.
    texts: list[tuple[int, list[Line]]] = []
    for pdf_page in range(9, 14):
        body = "Наполненный текст про регулировку клапанов двигателя"
        if pdf_page == 11:
            body = "Регулировка клапанного механизма зазоры"
        texts.append((pdf_page, _lines([body])))
    records = [("Регулировка клапанного механизма", 10)]
    assert detect_offset(records, texts, max_shift=2) == 1


def test_assign_sections_hierarchy() -> None:
    '''a page inherits the path of all active section levels.'''
    sections = build_sections(
        [("ТЕХНИЧЕСКОЕ ОБСЛУЖИВАНИЕ", 1), ("Регулировка клапанов", 3)], 0, 10
    )
    assert [s.level for s in sections] == [1, 2]  # caps → 1, unnumbered → 2
    pages = assign_page_sections(sections, toc_pages=[], page_count=10)
    assert pages[1].section_path == ["ТЕХНИЧЕСКОЕ ОБСЛУЖИВАНИЕ"]
    assert pages[3].section_path == ["ТЕХНИЧЕСКОЕ ОБСЛУЖИВАНИЕ", "Регулировка клапанов"]
    assert not pages[1].is_toc
