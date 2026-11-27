'''
File:   bootstrap.py
Brief:  Deployment bootstrap: fetch documents, build and cache the index.
Author: Demetrius242
Date:   2026-11-27
Version: v0.2.0

One command for a fresh deployment: download the issued manual PDFs and
case DOCX files from the shared storage link (MANUALS_DOWNLOAD_URL in
the gitignored .env), recognise them, build the search index with
embeddings and cache everything outside git:

    python scripts/bootstrap.py                # full: fetch + BM25 + embeddings
    python scripts/bootstrap.py --no-embed     # BM25-only (no ~2.3 GB model)
    python scripts/bootstrap.py --force-index  # rebuild even when cached

Layout (all outside the repository when MANUALS_DIR is configured
external — the recommended setup):

    <MANUALS_DIR>/manifest.json   seeded from data/manuals/manifest.json
    <MANUALS_DIR>/<doc>.pdf       manuals under manifest names (rag.setup)
    <MANUALS_DIR>/_staging/       fetched originals (kept for offline re-runs)
    <RAG_DATA_DIR>/               built index (default data/rag/, gitignored)

Idempotent: already-downloaded files are skipped by size, and a built
index in RAG_DATA_DIR is reused, so a re-deploy is a no-op cache hit.
The embedding model itself is cached by sentence-transformers outside
the repository. Nothing derived from the copyrighted manuals ever
enters the repository.
'''

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import fetch_manuals  # noqa: E402  (sibling script, same directory)

STAGING_DIRNAME = "_staging"


def env_value(name: str, default: str = "") -> str:
    '''Read a variable from the environment, falling back to repo .env.

    Args:
        name: Variable name (e.g. MANUALS_DIR).
        default: Value when the variable is set nowhere.

    Returns:
        Trimmed value or the default.
    '''
    value = os.environ.get(name)
    if value:
        return value.strip()
    return fetch_manuals.read_env_file(REPO_ROOT).get(name, default).strip()


def manuals_dir() -> Path:
    '''Target directory of the issued documents (env / .env / default).'''
    return Path(env_value("MANUALS_DIR", "data/manuals"))


def rag_data_dir() -> Path:
    '''RAG cache directory (env / .env / default data/rag).'''
    return Path(env_value("RAG_DATA_DIR", "data/rag"))


def manifest_files() -> list[str]:
    '''Expected file names of the six manuals per manifest.json.'''
    manifest = REPO_ROOT / "data" / "manuals" / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [entry["file"] for entry in data.get("documents", [])]


def documents_in_place(directory: Path) -> bool:
    '''Whether every manifest manual file already sits in *directory*.'''
    files = manifest_files()
    return bool(files) and all((directory / name).is_file() for name in files)


def seed_manifest(target: Path) -> None:
    '''Place the repository manifest.json into the manuals directory.

    rag.setup and the backend both read the manifest from MANUALS_DIR;
    when that directory is external it does not exist in a fresh clone,
    so the bootstrap seeds it (repo metadata, no copyrighted content).

    Args:
        target: The manuals directory (MANUALS_DIR).
    '''
    target.mkdir(parents=True, exist_ok=True)
    source = REPO_ROOT / "data" / "manuals" / "manifest.json"
    destination = target / "manifest.json"
    if source.is_file() and not destination.exists():
        shutil.copy2(source, destination)
        print(f"[bootstrap] seeded manifest.json into {target}")


def stage_originals(target: Path, staging: Path) -> None:
    '''Move fetched originals from the target root into the staging dir.

    The staging dir is the single place original-named files live; the
    target root ends up holding only manifest-named manuals, so re-runs
    reuse them instead of re-downloading.

    Args:
        target: The manuals directory (MANUALS_DIR).
        staging: The originals directory (<MANUALS_DIR>/_staging).
    '''
    keep = set(manifest_files()) | {"manifest.json"}
    staging.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.pdf", "*.docx"):
        for path in target.glob(pattern):
            if path.name in keep:
                continue
            destination = staging / path.name
            if not destination.exists():
                shutil.move(str(path), str(destination))


def index_cached(want_embeddings: bool) -> bool:
    '''Whether RAG_DATA_DIR already holds a usable built index.

    Lightweight check (pointer file + version directory + embeddings
    artifact when wanted) — no index loading.

    Args:
        want_embeddings: Require the dense artifact (emb.npy) too.

    Returns:
        True when the cached index can be served without a rebuild.
    '''
    data_dir = rag_data_dir()
    if not (data_dir / "current.json").is_file():
        return False
    try:
        from rag.index.store import latest_version

        version = latest_version(data_dir / "index")
    except Exception:
        return False
    if version is None:
        return False
    version_dir = data_dir / "index" / version
    if not (version_dir / "chunks.jsonl").is_file():
        return False
    if want_embeddings and not (version_dir / "emb.npy").is_file():
        return False
    return True


def fetch_documents(target: Path, staging: Path) -> None:
    '''Download the issued documents unless the manuals are all placed.

    Args:
        target: The manuals directory (MANUALS_DIR).
        staging: Where the fetch puts original-named files.
    '''
    if documents_in_place(target):
        print(f"[bootstrap] manuals already in place: {target}")
        return
    stage_originals(target, staging)
    seed_manifest(target)
    link = env_value("MANUALS_DOWNLOAD_URL")
    if not link:
        staged_pdfs = len(list(staging.glob("*.pdf")))
        if staged_pdfs >= len(manifest_files()):
            print(
                f"[bootstrap] no MANUALS_DOWNLOAD_URL, but staging already "
                f"holds {staged_pdfs} PDFs — continuing offline"
            )
            return
        raise SystemExit(
            "ERROR: documents are missing and MANUALS_DOWNLOAD_URL is not set.\n"
            "Put the shared storage link into the gitignored .env:\n"
            "  MANUALS_DOWNLOAD_URL=https://...\n"
            "The link must never be committed (enforced by a guard test)."
        )
    print(f"[bootstrap] fetching documents into {staging} ...")
    try:
        fetch_manuals.main(["--to", str(staging)])
    except SystemExit:
        # Network failure with a previously populated staging dir is fine:
        # rag.setup needs only the PDFs that are already there.
        staged_pdfs = len(list(staging.glob("*.pdf")))
        if staged_pdfs >= len(manifest_files()):
            print(
                f"[bootstrap] fetch failed, but staging already holds "
                f"{staged_pdfs} PDFs — continuing with what is on disk"
            )
        else:
            raise


def build_index(staging: Path, want_embeddings: bool, force: bool) -> None:
    '''Recognise the staged files, place them under manifest names, index.

    Args:
        staging: Directory holding the fetched originals.
        want_embeddings: False builds a BM25-only index (no model download).
        force: Rebuild even when a cached index is present.
    '''
    if not force and index_cached(want_embeddings):
        print(
            f"[bootstrap] index cache hit in {rag_data_dir()} — skipping the "
            "build (use --force-index to rebuild)"
        )
        return
    print(
        "[bootstrap] building the search index "
        + ("(BM25 + embeddings) ..." if want_embeddings else "(BM25-only) ...")
    )
    command = [
        sys.executable,
        "-m",
        "rag.setup",
        "--from",
        str(staging),
        "--link",
    ]
    if not want_embeddings:
        command.append("--no-embed")
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def main(argv: list[str] | None = None) -> None:
    '''Entry point: fetch what is missing, build what is not cached.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    '''
    parser = argparse.ArgumentParser(
        description="Deployment bootstrap: fetch the issued documents from the "
        "shared storage link and build/cache the search index. Idempotent — "
        "safe to re-run on every deploy."
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="BM25-only index (skips the ~2.3 GB embedding model download)",
    )
    parser.add_argument(
        "--force-index",
        action="store_true",
        help="rebuild the index even when a cached version exists",
    )
    args = parser.parse_args(argv)

    target = manuals_dir()
    staging = target / STAGING_DIRNAME
    fetch_documents(target, staging)
    build_index(staging, want_embeddings=not args.no_embed, force=args.force_index)
    print(
        "[bootstrap] done. Cached outside git: documents in "
        f"{target.resolve()}, index in {(REPO_ROOT / rag_data_dir()).resolve()}"
    )


if __name__ == "__main__":
    main()
