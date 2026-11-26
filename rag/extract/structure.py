'''
File:   structure.py
Brief:  Document structure: printed tables of contents and module registry.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

None of the six manuals has usable PDF bookmarks (236 RK stores 341 records
all named "Страница N", 536 RK stores 615 "Page N" records with wrong
targets), so the section map comes from the printed tables of contents:

- five documents have a printed TOC (three of them at the END of the file);
- the 536 RK manual has none — every "module" announces its title in the
  page header and its code (e.g. "Все 536-20-040040-020") in the footer;
  consecutive pages sharing a code form one module.

Printed page numbers differ from PDF pages by a per-document offset
(536 RE: printed = pdf - 1), detected here by matching titles against page
text and applied before assigning sections to pages.
'''

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.extract.layout import Line

# Pages inspected at the head and tail of a document for a printed TOC.
TOC_WINDOW = 12
# A TOC page must contain at least this many record-ending lines.
MIN_TOC_LINES = 6

# A line that ends a TOC record: "<title> <dot leader> <page number>".
# Dot leaders arrive as dots, ellipses or isolated numbers on the next line.
_TRAILING_NUMBER = re.compile(r"^(.*?)[\s.…·]{0,200}?(\d{1,3})[\s.…·]*$")
_NUMBER_ONLY = re.compile(r"^(\d{1,3})[\s.…·]*$")
_LEADER_RUN = re.compile(r"[.…·\s]{3,}")
_SECTION_NUMBER = re.compile(r"^(\d+(?:\.\d+)*)(?:\.?)[\s.]")


@dataclass
class Section:
    '''One section of the printed table of contents, mapped to PDF pages.'''

    title: str
    level: int
    page_start_pdf: int
    page_printed: int
    source: str = "toc_printed"
    code: str | None = None


@dataclass
class PageStructure:
    '''Structure metadata assigned to one page.'''

    section: str | None
    section_path: list[str]
    is_toc: bool


def _looks_like_toc(lines: list[Line]) -> bool:
    '''Return True when a page looks like a printed table of contents.

    Markdown-captured pages are flattened first, so a ruled-grid TOC
    counts too.
    '''
    endings = 0
    for text in _expand_markdown_lines(lines):
        stripped = text.strip()
        if _TRAILING_NUMBER.match(stripped) and not stripped.isdigit():
            endings += 1
    return endings >= MIN_TOC_LINES


def _clean_title(raw: str) -> str:
    '''Strip dot leaders and whitespace from a TOC record title.'''
    title = _LEADER_RUN.sub(" ", raw)
    return title.strip(" .…·\u00a0")


def _level_of(title: str) -> int:
    '''Derive the nesting level of a TOC record from its numbering.

    "1" or "ПРИЛОЖЕНИЕ ..." → 1, "2.7" → 2, "2.7.1" → 3; unnumbered titles
    whose first word is all-caps are level 1, other unnumbered titles
    level 2. Part codes of defect maps ("1002. Блок цилиндров") are
    treated as level 3 — they are details, not chapters.
    '''
    match = _SECTION_NUMBER.match(title + " ")
    if match:
        number = match.group(1)
        depth = number.count(".") + 1
        if depth == 1 and number.isdigit() and len(number) > 2:
            return 3  # defect-map part codes like "1002."
        return min(depth, 4)
    stripped = title.strip()
    first_word = stripped.split(maxsplit=1)[0] if stripped else ""
    if first_word and first_word.upper() == first_word and any(
        ch.isalpha() for ch in first_word
    ):
        return 1
    return 2


def _expand_markdown_lines(lines: list[Line]) -> list[str]:
    '''Flatten markdown table lines into plain text rows.

    ``find_tables`` sometimes captures a printed TOC (536 RE pages 282–284
    have a ruled grid); its markdown block is expanded so the ordinary
    record parser sees "title ... number" rows again.

    Args:
        lines: Page lines in reading order.

    Returns:
        Plain text items, one per visual row.
    '''
    items: list[str] = []
    for line in lines:
        if "|" not in line.text:
            items.append(line.text)
            continue
        for row in line.text.split("\n"):
            stripped = row.strip()
            if "|" in stripped:
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                cells = [c for c in cells if c and c.lower() not in ("стр.", "стр")]
                if cells:
                    items.append(" ".join(cells))
                # Empty or header-only rows carry nothing: skip entirely.
                continue
            if stripped:
                items.append(stripped)
    return items


def parse_toc(lines: list[Line]) -> list[tuple[str, int]]:
    '''Parse a printed table of contents page into (title, printed page).

    Records can span several visual lines: the title continues until a line
    ends with (or consists of) the page number. Dot leaders are removed;
    markdown-captured TOCs are flattened first.

    Args:
        lines: TOC page lines in reading order.

    Returns:
        List of (clean title, printed page number) records.
    '''
    records: list[tuple[str, int]] = []
    pending = ""
    for text in _expand_markdown_lines(lines):
        text = text.strip()
        if not text:
            continue
        number_only = _NUMBER_ONLY.match(text)
        if number_only and pending:
            records.append((_clean_title(pending), int(number_only.group(1))))
            pending = ""
            continue
        match = _TRAILING_NUMBER.match(text)
        if match and not number_only:
            title_part = match.group(1)
            page = int(match.group(2))
            combined = (pending + " " + title_part).strip()
            if _clean_title(combined):
                records.append((_clean_title(combined), page))
            pending = ""
            continue
        # A continuation line: the record title is not finished yet.
        pending = (pending + " " + text).strip()
    return records


def find_toc_pages(pages: list[tuple[int, list[Line]]]) -> list[int]:
    '''Locate printed-TOC pages among the first and last pages of a document.

    Args:
        pages: (page_pdf, lines) for every page of the document.

    Returns:
        PDF page numbers that look like tables of contents.
    '''
    count = len(pages)
    candidates = list(range(1, min(TOC_WINDOW, count) + 1))
    candidates += list(range(max(1, count - TOC_WINDOW + 1), count + 1))
    result: list[int] = []
    seen: set[int] = set()
    for page_pdf, lines in pages:
        if page_pdf in seen or page_pdf not in candidates:
            continue
        if _looks_like_toc(lines):
            result.append(page_pdf)
            seen.add(page_pdf)
    return sorted(result)


def detect_offset(
    records: list[tuple[str, int]],
    pages: list[tuple[int, list[Line]]],
    max_shift: int = 5,
) -> int:
    '''Detect the printed→PDF page offset by matching titles to page text.

    For each candidate shift k the number of records whose (normalized)
    25-character title prefix appears on PDF page "printed + k" is counted;
    the shift with the most matches wins. 536 RE has offset +1 (printed 26
    sits on PDF page 27), the rest sit at 0.

    Args:
        records: Parsed TOC records (title, printed page).
        pages: All pages of the document.
        max_shift: Maximum |offset| tried.

    Returns:
        The best offset (added to printed page to get the PDF page).
    '''
    texts: dict[int, str] = {}
    for page_pdf, lines in pages:
        joined = " ".join(line.text for line in lines)
        texts[page_pdf] = re.sub(r"[\s\u00a0]+", "", joined).lower()

    best_k, best_hits = 0, -1
    for k in range(-max_shift, max_shift + 1):
        hits = 0
        for title, printed in records:
            probe = re.sub(r"[\s\u00a0]+", "", title).lower()[:25]
            if not probe:
                continue
            if texts.get(printed + k, "").find(probe) != -1:
                hits += 1
        if hits > best_hits:
            best_k, best_hits = k, hits
    return best_k


def build_sections(
    records: list[tuple[str, int]],
    offset: int,
    page_count: int,
) -> list[Section]:
    '''Convert TOC records into leveled sections on PDF pages.

    Args:
        records: Parsed TOC records (title, printed page).
        offset: Printed→PDF offset from :func:`detect_offset`.
        page_count: Total pages, used to clamp the last section's end.

    Returns:
        Sections sorted by start page with levels from numbering.
    '''
    sections: list[Section] = []
    for title, printed in records:
        page_pdf = printed + offset
        if not 1 <= page_pdf <= page_count:
            continue
        sections.append(
            Section(
                title=title,
                level=_level_of(title),
                page_start_pdf=page_pdf,
                page_printed=printed,
            )
        )
    sections.sort(key=lambda s: s.page_start_pdf)
    return sections


# --- 536 RK module registry -------------------------------------------------

_MODULE_CODE = re.compile(r"536-\d{2}-\d{6}-\d{3}")


@dataclass
class ModuleRegistry:
    '''Module map of the 536 RK manual (it has no printed TOC).'''

    sections: list[Section] = field(default_factory=list)


def parse_module_code(line_text: str) -> str | None:
    '''Extract a module code ("Все 536-20-040040-020") from a footer line.

    Args:
        line_text: One page line.

    Returns:
        The code without the leading "Все ", or None.
    '''
    match = _MODULE_CODE.search(line_text)
    return match.group(0) if match else None


def build_module_registry(
    pages: list[tuple[int, list[Line]]],
) -> ModuleRegistry:
    '''Build the module registry for the 536 RK manual.

    Consecutive pages carrying the same footer code form a module; the
    module title is the first substantial header line of its first page.
    Modules are grouped into level-1 sections by the code prefix
    ("536-20" etc.), titled after their first module.

    Args:
        pages: (page_pdf, lines) for every page of the document.

    Returns:
        Registry with a flat, sorted section list.
    '''
    page_code: dict[int, str] = {}
    page_title: dict[int, str] = {}
    for page_pdf, lines in pages:
        for line in lines:
            code = parse_module_code(line.text)
            if code:
                page_code[page_pdf] = code
                break
        for line in lines:
            text = line.text.strip()
            if (
                len(text) >= 6
                and not text.isdigit()
                and not parse_module_code(text)
                and not text.lower().startswith(("все ", "страница"))
            ):
                page_title[page_pdf] = text
                break

    # Collapse consecutive pages into modules.
    sections: list[Section] = []
    current_code: str | None = None
    current_start = 0
    for page_pdf in sorted(set(page_code) | set(page_title)):
        code = page_code.get(page_pdf)
        if code != current_code:
            if current_code is not None:
                sections.append(
                    Section(
                        title=page_title.get(current_start, current_code),
                        level=2,
                        page_start_pdf=current_start,
                        page_printed=0,
                        source="module_header",
                        code=current_code,
                    )
                )
            current_code = code
            current_start = page_pdf
    if current_code is not None:
        sections.append(
            Section(
                title=page_title.get(current_start, current_code),
                level=2,
                page_start_pdf=current_start,
                page_printed=0,
                source="module_header",
                code=current_code,
            )
        )

    # Level-1 groups by code prefix, titled after their first module.
    grouped: dict[str, Section] = {}
    for section in sections:
        prefix = (section.code or "").rsplit("-", 1)[0]
        grouped.setdefault(
            prefix,
            Section(
                title=section.title,
                level=1,
                page_start_pdf=section.page_start_pdf,
                page_printed=0,
                source="module_header",
                code=prefix,
            ),
        )
    all_sections = sorted(
        [*grouped.values(), *sections], key=lambda s: s.page_start_pdf
    )
    return ModuleRegistry(sections=all_sections)


def assign_page_sections(
    sections: list[Section],
    toc_pages: list[int],
    page_count: int,
) -> dict[int, PageStructure]:
    '''Assign a section path to every page of a document.

    A page's section is the last section whose start page is not after it;
    the full path reconstructs the heading hierarchy by level. TOC pages
    are flagged and excluded from indexing later.

    Args:
        sections: Sorted section list (any mix of levels).
        toc_pages: PDF page numbers that are printed TOCs.
        page_count: Total page count.

    Returns:
        page_pdf → PageStructure for every page.
    '''
    result: dict[int, PageStructure] = {}
    stack: list[tuple[int, str]] = []  # (level, title)
    idx = 0
    for page in range(1, page_count + 1):
        while idx < len(sections) and sections[idx].page_start_pdf <= page:
            section = sections[idx]
            level = section.level
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, section.title))
            idx += 1
        path = [title for _lvl, title in stack]
        result[page] = PageStructure(
            section=path[-1] if path else None,
            section_path=path,
            is_toc=page in toc_pages,
        )
    return result


__all__: list[str] = [
    "MIN_TOC_LINES",
    "ModuleRegistry",
    "PageStructure",
    "Section",
    "TOC_WINDOW",
    "assign_page_sections",
    "build_module_registry",
    "build_sections",
    "detect_offset",
    "find_toc_pages",
    "parse_module_code",
    "parse_toc",
]
