'''
File:   ingest.py
Brief:  CLI orchestrator of the PDF ingestion pipeline.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Usage:
    python -m rag.ingest [--pdf-dir data/manuals] [--out data/rag]
                         [--only DOC_ID] [--no-embed] [--no-tables]

Steps per document: passport → extract pages (layout + tables + text
normalisation + running-header removal) → structure (printed TOC or the
536 RK module registry) → chunks → BM25 index (and embeddings unless
--no-embed) → a new version directory + current.json pointer.

Everything written lands under data/rag/ which is gitignored — extracted
manual text and indexes never enter the repository.
'''

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pymupdf

# Classic table detector, no bundled neural layout (issue #1, follow-up
# F-1): on pymupdf >= 2.2 find_tables() silently runs the pymupdf/layout
# BoxRFDGNN model over ONNX with ~64 intra-op threads per page, which pegs
# every core during ingestion — and on our manuals it finds FEWER tables
# than the classic detector («236.01.01 РК» p.286: neural 0, classic 1).
# The flag is checked first by Page.get_layout and short-circuits; setting
# _get_layout = None would not survive the lazy import's activate().
pymupdf._layout_enabled = False

from rag.config import RagSettings, get_settings  # noqa: E402
from rag.extract.chunker import PageRecord, chunk_page  # noqa: E402
from rag.extract.layout import Line  # noqa: E402
from rag.extract.passport import measure  # noqa: E402
from rag.extract.quality import measure_document, write_report  # noqa: E402
from rag.extract.structure import (  # noqa: E402
    assign_page_sections,
    build_module_registry,
    build_sections,
    detect_offset,
    find_toc_pages,
    parse_toc,
)
from rag.extract.tables import page_with_tables  # noqa: E402
from rag.extract.textnorm import normalize_page_text  # noqa: E402
from rag.extract.wordforms import build_wordforms, prune  # noqa: E402
from rag.extract.wordforms import save as save_wordforms  # noqa: E402
from rag.index.bm25 import BM25Index  # noqa: E402
from rag.index.dense import DenseIndex  # noqa: E402
from rag.index.store import write_version  # noqa: E402
from rag.index.tokenizer import tokenize  # noqa: E402
from rag.knowledge.loader import load_knowledge  # noqa: E402
from rag.search import normalize_engine  # noqa: E402

logger = logging.getLogger(__name__)

# A line in the top/bottom band repeating on this many pages is a running
# header/footer (plan-B §5.4: >= 30% of pages, at least 10 pages).
_RUNNING_MIN_PAGES = 10
_RUNNING_SHARE = 0.3
# Bands of the page considered header/footer (fractions of page height).
_HEADER_BAND = 0.08
_FOOTER_BAND = 0.10


def extract_document(
    doc_id: str,
    doc_title: str,
    doc_type: str,
    engines: list[str],
    path: Path,
    settings: RagSettings,
    toc_hint_pages: list[int],
    toc_hint_offset: int | None,
    toc_hint_source: str = "auto",
    wordforms: dict[str, int] | None = None,
    fragment_forms: dict[str, int] | None = None,
) -> tuple[list[PageRecord], list[dict]]:
    '''Run the full extraction pipeline for one document.

    Args:
        doc_id: Manifest designation ("236.01.01 РК").
        doc_title: Manifest title.
        doc_type: re | rr | re_rr (from the manifest kind).
        engines: Engine models from the manifest.
        path: PDF file path.
        settings: RAG settings.
        toc_hint_pages: Printed-TOC page hint from docs.yaml (may be empty).
        toc_hint_offset: Printed→PDF offset hint (None → auto-detect).
        toc_hint_source: auto | printed | modules.
        wordforms: Corpus word-form dictionary (broken-word glue).
        fragment_forms: Frequent-fragment table (always-broken words).

    Returns:
        (page records, sections payload for diagnostics).
    '''
    doc = measure(str(path))
    logger.info(
        "%s: %d pages, %d chars, %d figure sheets, rotated %s",
        path.name, doc.pages, doc.chars, doc.figure_sheets, doc.rotated_pages,
    )
    with pymupdf.open(path) as pdf:
        pages_data: list[tuple[int, list[Line]]] = []
        for number, page in enumerate(pdf, start=1):
            lines = page_with_tables(page)
            pages_data.append((number, lines))

        page_count = pdf.page_count

    # --- structure ----------------------------------------------------------
    # "modules" forces the module registry (536 RK has no printed TOC and
    # auto-detection false-positives on its cover pages); "printed" uses
    # the hinted pages; "auto" looks for a printed TOC first.
    if toc_hint_source == "modules":
        toc_pages = []
    elif toc_hint_source == "printed" or toc_hint_pages:
        toc_pages = (
            list(range(toc_hint_pages[0], toc_hint_pages[-1] + 1))
            if toc_hint_pages
            else find_toc_pages(pages_data)
        )
    else:
        toc_pages = find_toc_pages(pages_data)
    sections_payload: list[dict] = []
    if toc_pages:
        records: list[tuple[str, int]] = []
        for page_pdf, lines in pages_data:
            if page_pdf in toc_pages:
                records.extend(parse_toc(lines))
        offset = toc_hint_offset
        if offset is None:
            offset = detect_offset(records, pages_data)
        sections = build_sections(records, offset, page_count)
        logger.info("%s: printed TOC on %s, offset %s, %d sections",
                    doc_id, toc_pages, offset, len(sections))
    else:
        registry = build_module_registry(pages_data)
        sections = registry.sections
        logger.info("%s: module registry with %d sections", doc_id, len(sections))
    page_struct = assign_page_sections(sections, toc_pages, page_count)
    for section in sections:
        sections_payload.append(
            {
                "title": section.title,
                "level": section.level,
                "page_start_pdf": section.page_start_pdf,
                "code": section.code,
                "source": section.source,
            }
        )

    # --- running headers and page text --------------------------------------
    running = _running_lines(pages_data)
    printed_by_page = _printed_numbers(pages_data)
    page_records: list[PageRecord] = []
    for page_pdf, lines in pages_data:
        filtered: list[str] = []
        for line in lines:
            text = line.text.strip()
            if text in running or (page_pdf, text) in printed_by_page:
                continue
            filtered.append(line.text)
        text = normalize_page_text("\n".join(filtered), wordforms, fragment_forms)
        struct = page_struct.get(page_pdf)
        page_records.append(
            PageRecord(
                doc_id=doc_id,
                doc_title=doc_title,
                doc_type=doc_type,
                engines=list(engines),
                page_pdf=page_pdf,
                text=text,
                section=struct.section if struct else None,
                section_path=struct.section_path if struct else [],
                is_toc=bool(struct and struct.is_toc),
                is_figure_sheet=len(text.strip()) < 20,
            )
        )
    return page_records, sections_payload


def _document_bounds(pages_data: list[tuple[int, list[Line]]]) -> tuple[float, float]:
    '''Vertical extent of all text in the document (header/footer bands).

    Args:
        pages_data: (page_pdf, lines) for every page.

    Returns:
        (min y0, max y1) across every line.
    '''
    all_lines = [line for _p, lines in pages_data for line in lines]
    if not all_lines:
        return 0.0, 1.0
    return min(line.y0 for line in all_lines), max(line.y1 for line in all_lines)


def _in_band(line: Line, bounds: tuple[float, float]) -> bool:
    '''True when the line sits in the header or footer band of the document.

    Args:
        line: One line.
        bounds: Document vertical extent from :func:`_document_bounds`.

    Returns:
        True for the top 8% and bottom 10% bands.
    '''
    y_top, y_bot = bounds
    height = max(y_bot - y_top, 1.0)
    return (
        line.y_center - y_top <= _HEADER_BAND * height
        or y_bot - line.y_center <= _FOOTER_BAND * height
    )


def _running_lines(pages_data: list[tuple[int, list[Line]]]) -> set[str]:
    '''Detect running header/footer texts across a document.

    A text repeated on at least max(10, 30%) of pages inside the bands is a
    running line ("536.3902150 РЭ", "Руководство по ремонту ..."). Purely
    numeric lines are page numbers, handled separately.

    Args:
        pages_data: (page_pdf, lines) for every page.

    Returns:
        Exact line texts to remove everywhere.
    '''
    n_pages = len(pages_data)
    if n_pages == 0:
        return set()
    threshold = max(_RUNNING_MIN_PAGES, int(_RUNNING_SHARE * n_pages))
    bounds = _document_bounds(pages_data)
    counts: dict[str, int] = {}
    for _page_pdf, lines in pages_data:
        seen: set[str] = set()
        for line in lines:
            if _in_band(line, bounds):
                text = line.text.strip()
                if text and not text.isdigit() and text not in seen:
                    seen.add(text)
                    counts[text] = counts.get(text, 0) + 1
    return {text for text, count in counts.items() if count >= threshold}


def _printed_numbers(pages_data: list[tuple[int, list[Line]]]) -> set[tuple[int, str]]:
    '''Collect digits-only band lines as printed page numbers.

    Args:
        pages_data: (page_pdf, lines) for every page.

    Returns:
        Set of (page_pdf, digits text) pairs to remove from page text.
    '''
    bounds = _document_bounds(pages_data)
    result: set[tuple[int, str]] = set()
    for page_pdf, lines in pages_data:
        for line in lines:
            text = line.text.strip()
            if text.isdigit() and _in_band(line, bounds):
                result.add((page_pdf, text))
    return result


def run_ingest(
    pdf_dir: Path,
    data_dir: Path,
    only: str | None = None,
    use_embeddings: bool = True,
    settings: RagSettings | None = None,
) -> dict:
    '''Build a full index version from the manuals directory.

    Args:
        pdf_dir: Directory with manifest.json and the PDF files.
        data_dir: Output directory (data/rag, gitignored).
        only: Restrict to one doc_id (debug builds).
        use_embeddings: Build the dense part too.
        settings: Settings override (tests).

    Returns:
        Summary dict (version, per-doc chunk counts).
    '''
    settings = settings or get_settings()
    knowledge = load_knowledge(Path(__file__).parent / "knowledge")
    manifest_path = pdf_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    kind_to_type = {
        "operation_manual": "re",
        "repair_manual": "rr",
        "operation_service_repair_manual": "re_rr",
    }
    all_chunks = []
    all_pages: list[dict] = []
    quality_report: dict[str, list] = {}
    docs_summary: dict[str, dict[str, int]] = {}
    # Phase 0: resolve every manual's file, then build the corpus
    # word-form dictionary (used to glue space-broken words).
    resolved: list[tuple[dict, object]] = []
    for entry in manifest.get("documents", []):
        doc_id = entry["doc_id"]
        if only and doc_id != only:
            continue
        info = knowledge.docs.get(doc_id)
        file_name = entry["file"]
        candidates = [pdf_dir / file_name]
        if info:
            candidates += [pdf_dir / alias for alias in info.aliases]
        path = next((c for c in candidates if c.is_file()), None)
        if path is None:
            logger.warning(
                "%s: manual file not found (%s) — skipped", doc_id, file_name
            )
            continue
        resolved.append((entry, path))

    dictionary_path = data_dir / "wordforms.json"
    raw_counts = build_wordforms([p for _e, p in resolved])
    wordforms = prune(raw_counts)
    fragment_forms = prune(raw_counts)
    save_wordforms(wordforms, dictionary_path)
    logger.info(
        "word-form dictionary: %d words", len(wordforms),
    )

    for entry, path in resolved:
        doc_id = entry["doc_id"]
        info = knowledge.docs.get(doc_id)
        # Engines are stored normalised so query-side matching is exact.
        engines = [normalize_engine(e) for e in entry["engines"]]
        toc_pages_hint = info.toc_pages if info else []
        toc_offset_hint = info.toc_offset if info else None
        toc_source_hint = info.toc_source if info else "auto"
        page_records, sections_payload = extract_document(
            doc_id=doc_id,
            doc_title=entry["title"],
            doc_type=kind_to_type.get(entry.get("kind", ""), "re"),
            engines=engines,
            path=path,
            settings=settings,
            toc_hint_pages=toc_pages_hint,
            toc_hint_offset=toc_offset_hint,
            toc_hint_source=toc_source_hint,
            wordforms=wordforms,
            fragment_forms=fragment_forms,
        )
        chunks: list = []
        for page in page_records:
            chunks.extend(chunk_page(page, settings))
        all_chunks.extend(chunks)
        all_pages.extend(
            {
                "doc_id": page.doc_id,
                "page_pdf": page.page_pdf,
                "text": page.text,
                "section": page.section,
                "section_path": page.section_path,
                "is_toc": page.is_toc,
                "is_figure_sheet": page.is_figure_sheet,
            }
            for page in page_records
        )
        docs_summary[doc_id] = {"chunks": len(chunks), "pages": len(page_records)}
        docs_summary[doc_id]["sections"] = len(sections_payload)
        with pymupdf.open(path) as pdf:
            quality_report[doc_id] = measure_document(pdf)
        logger.info("%s: %d pages → %d chunks", doc_id, len(page_records), len(chunks))

    if not all_chunks:
        raise SystemExit(
            "no chunks built — are the manual PDFs in place? "
            "Run: python -m rag.setup --from <dir-with-pdfs>"
        )

    token_lists = [tokenize(chunk.embed_text) for chunk in all_chunks]
    engine_lists = [chunk.engines for chunk in all_chunks]
    bm25 = BM25Index.build(token_lists, engine_lists)

    embeddings = None
    embed_model = None
    if use_embeddings and settings.embed_model not in ("", "none"):
        dense = DenseIndex(
            settings.embed_model, data_dir / "emb_cache", settings.device
        )
        embeddings = dense.embed_texts([chunk.embed_text for chunk in all_chunks])
        if embeddings is not None:
            embed_model = settings.embed_model
        else:
            logger.warning("embedding model unavailable — building BM25-only index")

    version = write_version(
        data_dir, all_chunks, all_pages, bm25, embeddings, embed_model
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    write_report(str(data_dir / "quality_report.json"), quality_report)
    return {"version": version, "docs": docs_summary, "n_chunks": len(all_chunks)}


def main() -> None:
    '''CLI entry point.'''
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(
        prog="python -m rag.ingest",
        description="Build the RAG index from the issued manual PDFs.",
    )
    parser.add_argument("--pdf-dir", type=Path, default=None, help="manuals directory")
    parser.add_argument("--out", type=Path, default=None, help="output data directory")
    parser.add_argument("--only", type=str, default=None, help="build one doc_id only")
    parser.add_argument(
        "--no-embed", action="store_true", help="skip embeddings (BM25-only index)"
    )
    args = parser.parse_args()

    settings = get_settings()
    pdf_dir = args.pdf_dir or settings.manuals_dir
    data_dir = args.out or settings.data_dir
    summary = run_ingest(
        pdf_dir=pdf_dir,
        data_dir=data_dir,
        only=args.only,
        use_embeddings=not args.no_embed,
        settings=settings,
    )
    print(f"index {summary['version']} built: {summary['n_chunks']} chunks")
    for doc_id, stats in summary["docs"].items():
        print(f"  {doc_id}: {stats['pages']} pages, {stats['chunks']} chunks, "
              f"{stats.get('sections', 0)} sections")
    print("start the service: uvicorn rag.service:app --port 8003")


if __name__ == "__main__":
    main()
