'''
File:   setup.py
Brief:  One-command manual onboarding: recognise, place, index.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

The issued PDFs are not in the repository (copyright). This command takes a
directory with the issued files (whatever they are named), recognises every
manual, places it under the manifest file name and builds the index:

    python -m rag.setup --from "C:\\path\\to\\pdfs"

Recognition order per manual: exact manifest file name → documented alias
(the hackathon bundle ships two manuals under Russian names) → fingerprint
(page count from the manifest + designation regex over the first pages).
Files land in MANUALS_DIR (default data/manuals) as a copy; --link uses a
hard link instead. The backend (participant A) serves PDFs from that same
directory, so nothing else is needed on its side.
'''

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

import pymupdf

from rag.config import RagSettings, get_settings
from rag.extract.passport import matches_designation, measure
from rag.knowledge.loader import load_knowledge

logger = logging.getLogger(__name__)


def recognise(
    source_dir: Path,
    manifest_docs: list[dict],
    knowledge_docs: dict,
) -> tuple[dict[str, Path], list[str]]:
    '''Map every manifest doc_id to a source PDF, when found.

    Args:
        source_dir: Directory holding the issued files (any names).
        manifest_docs: manifest.json documents list.
        knowledge_docs: docs.yaml info (aliases, fingerprints).

    Returns:
        (doc_id → source path, problems list for unrecognised docs).
    '''
    files = [p for p in source_dir.iterdir() if p.suffix.lower() == ".pdf"]
    by_lower = {p.name.lower(): p for p in files}

    found: dict[str, Path] = {}
    problems: list[str] = []
    for entry in manifest_docs:
        doc_id = entry["doc_id"]
        expected_pages = int(entry.get("pages", 0))
        info = knowledge_docs.get(doc_id)
        candidates: list[Path] = []
        names = [entry["file"]]
        if info:
            names.extend(info.aliases)
        for name in names:
            direct = by_lower.get(name.lower())
            if direct:
                candidates.append(direct)
        # Alias/near-name match before fingerprinting.
        chosen: Path | None = None
        for candidate in candidates:
            if _page_count_ok(candidate, expected_pages):
                chosen = candidate
                break
        if chosen is None and info is not None and info.fingerprint:
            for candidate in files:
                if candidate in candidates:
                    continue
                passport = measure(str(candidate))
                if (
                    passport.pages == expected_pages
                    and matches_designation(passport, info.fingerprint)
                ):
                    chosen = candidate
                    break
        if chosen is not None:
            found[doc_id] = chosen
        else:
            problems.append(
                f"{doc_id}: not recognised in {source_dir} "
                f"(expected {entry['file']}, {expected_pages} pages)"
            )
    return found, problems


def _page_count_ok(path: Path, expected: int) -> bool:
    '''True when the file opens and has the expected page count.'''
    try:
        with pymupdf.open(path) as doc:
            return doc.page_count == expected
    except Exception:  # noqa: BLE001 - unreadable file is just not a match
        return False


def place(
    found: dict[str, Path],
    manuals_dir: Path,
    manifest_docs: list[dict],
    link: bool = False,
) -> list[tuple[str, str]]:
    '''Copy or hard-link recognised files under the manifest names.

    Args:
        found: doc_id → source path from :func:`recognise`.
        manuals_dir: Target directory (MANUALS_DIR).
        manifest_docs: manifest.json documents list.
        link: Hard-link instead of copy (same volume only).

    Returns:
        (doc_id, action) pairs: "copied" | "linked" | "already-placed".
    '''
    manuals_dir.mkdir(parents=True, exist_ok=True)
    file_by_id = {entry["doc_id"]: entry["file"] for entry in manifest_docs}
    actions: list[tuple[str, str]] = []
    for doc_id, source in found.items():
        target = manuals_dir / file_by_id[doc_id]
        if (
            target.is_file()
            and target.stat().st_size == source.stat().st_size
        ):
            actions.append((doc_id, "already-placed"))
            continue
        if link:
            try:
                if target.exists():
                    target.unlink()
                target.hardlink_to(source.resolve())
                actions.append((doc_id, "linked"))
                continue
            except OSError:
                logger.warning("hard link failed for %s — falling back to copy", doc_id)
        shutil.copy2(source, target)
        actions.append((doc_id, "copied"))
    return actions


def main() -> None:
    '''CLI entry point: recognise, place, then ingest.'''
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(
        prog="python -m rag.setup",
        description=(
            "Place the issued manual PDFs under the manifest names and build "
            "the search index (one command)."
        ),
    )
    parser.add_argument(
        "--from",
        dest="source",
        type=Path,
        required=True,
        help="directory with the issued PDF files (any file names)",
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="hard-link files instead of copying (same disk volume only)",
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="skip embeddings (BM25-only index, no model download)",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="only place the files, do not build the index",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help=(
            "run the eval gate (python -m rag.eval --set all) after the "
            "build; needs the external question sets in RAG_EVAL_DIR"
        ),
    )
    args = parser.parse_args()

    settings = get_settings()
    source: Path = args.source
    if not source.is_dir():
        raise SystemExit(f"source directory not found: {source}")

    manifest_path = settings.manuals_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_docs = manifest.get("documents", [])
    knowledge = load_knowledge(Path(__file__).parent / "knowledge")

    found, problems = recognise(source, manifest_docs, knowledge.docs)
    if problems:
        for problem in problems:
            print(f"  ! {problem}")
    if not found:
        raise SystemExit("no manuals recognised — nothing to do")

    actions = place(found, settings.manuals_dir, manifest_docs, link=args.link)
    for doc_id, action in actions:
        print(f"  {doc_id}: {action}")
    print(
        f"{len(found)}/{len(manifest_docs)} manuals in place at {settings.manuals_dir}"
    )

    if args.skip_ingest:
        return
    if len(found) < len(manifest_docs):
        print("building the index for the recognised manuals only "
              "(re-run after adding the rest)")

    from rag.ingest import run_ingest

    summary = run_ingest(
        pdf_dir=settings.manuals_dir,
        data_dir=settings.data_dir,
        only=None,
        use_embeddings=not args.no_embed,
        settings=settings,
    )
    print(f"index {summary['version']} built: {summary['n_chunks']} chunks")
    if args.eval:
        _run_eval_gate(settings)
    print("start the service: uvicorn rag.service:app --port 8003")
    print(
        "backend switch: RAG_API_URL=http://127.0.0.1:8003 in .env "
        "(already the default)"
    )


def _run_eval_gate(settings: RagSettings) -> None:
    '''Run the eval sets right after the build (issue #14 H2).

    The build is only half of the reproducibility contract — the eval
    numbers must come from THIS build, so ``--eval`` chains the eval
    runner and propagates its exit code (a failing gate fails the
    command). Skipped with a note when RAG_EVAL_DIR has no question sets.

    Args:
        settings: RAG settings (eval_dir holds the external JSONL sets).
    '''
    import subprocess
    import sys

    set_files = ("manual.jsonl", "golden.jsonl", "negative.jsonl")
    if not any((settings.eval_dir / name).is_file() for name in set_files):
        print(
            f"  ! eval skipped: no question sets in RAG_EVAL_DIR "
            f"({settings.eval_dir}) — see scripts/fetch_external.py"
        )
        return
    result = subprocess.run(
        [sys.executable, "-m", "rag.eval", "--set", "all"],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
