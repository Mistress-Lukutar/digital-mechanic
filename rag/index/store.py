'''
File:   store.py
Brief:  Index version directories and the current-version pointer.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

A version directory (data/rag/index/vNNN/) holds the bm25 model, the
embedding matrix, the chunks copy it was built from, pages text and a
manifest. A new version is built next to the current one, checked by eval,
then ``current.json`` is flipped — the old version stays until the demo
is over. All of data/rag/ is gitignored: extracted manual text never
enters the repository.
'''

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from rag.extract.chunker import Chunk
from rag.index.bm25 import BM25Index

_VERSION_RE = re.compile(r"^v(\d+)$")


@dataclass
class IndexManifest:
    '''Facts about one built index version.'''

    version: str
    built_at: str
    embed_model: str | None
    n_chunks: int
    n_pages: int
    docs: dict[str, dict[str, int]]


@dataclass
class StoredIndex:
    '''Everything the service needs at query time.'''

    version: str
    built_at: str
    embed_model: str | None
    chunks: list[Chunk]
    bm25: BM25Index
    embeddings: np.ndarray | None  # rows aligned with chunks, or None
    page_text: dict[tuple[str, int], str]  # (doc_id, page_pdf) → page text
    doc_pages: dict[str, dict[int, str]]  # doc_id → {page_pdf: title?} unused
    manifest: IndexManifest

    @property
    def mode(self) -> str:
        '''"hybrid" when embeddings are loaded, "bm25" otherwise.'''
        return "hybrid" if self.embeddings is not None else "bm25"


def latest_version(index_root: Path) -> str | None:
    '''Return the highest built version name, or None.

    Args:
        index_root: Directory holding vNNN subdirectories.

    Returns:
        "vNNN" of the latest version.
    '''
    if not index_root.is_dir():
        return None
    versions = [
        entry.name
        for entry in index_root.iterdir()
        if entry.is_dir() and _VERSION_RE.match(entry.name)
    ]
    if not versions:
        return None
    return max(versions, key=lambda name: int(name[1:]))


def read_current(data_dir: Path, pinned: str | None = None) -> StoredIndex | None:
    '''Load the index the service should serve.

    Args:
        data_dir: RAG data directory (holds index/ and current.json).
        pinned: Optional exact version to load instead of the pointer.

    Returns:
        Loaded index, or None when nothing is built yet.
    '''
    index_root = data_dir / "index"
    version = pinned or _read_pointer(data_dir) or latest_version(index_root)
    if version is None:
        return None
    directory = index_root / version
    if not directory.is_dir():
        return None

    chunks = _load_chunks(directory / "chunks.jsonl")
    bm25 = BM25Index.load(directory / "bm25")
    emb_path = directory / "emb.npy"
    embeddings: np.ndarray | None = None
    if emb_path.is_file():
        matrix = np.load(emb_path)
        if len(chunks) and matrix.shape[0] == len(chunks):
            embeddings = matrix
    manifest_data = json.loads(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    manifest = IndexManifest(
        version=manifest_data.get("version", version),
        built_at=manifest_data.get("built_at", ""),
        embed_model=manifest_data.get("embed_model"),
        n_chunks=manifest_data.get("n_chunks", len(chunks)),
        n_pages=manifest_data.get("n_pages", 0),
        docs=manifest_data.get("docs", {}),
    )
    page_text = _load_pages(directory / "pages.jsonl")
    return StoredIndex(
        version=version,
        built_at=manifest.built_at,
        embed_model=manifest.embed_model,
        chunks=chunks,
        bm25=bm25,
        embeddings=embeddings,
        page_text=page_text,
        doc_pages={},
        manifest=manifest,
    )


def write_version(
    data_dir: Path,
    chunks: list[Chunk],
    page_records: list[dict],
    bm25: BM25Index,
    embeddings: np.ndarray | None,
    embed_model: str | None,
) -> str:
    '''Write a new index version and point current.json at it.

    Args:
        data_dir: RAG data directory.
        chunks: Chunks the index was built from.
        page_records: Page records (pages.jsonl payload) for /document.
        bm25: Built BM25 index.
        embeddings: Aligned embedding matrix or None (BM25-only build).
        embed_model: Embedding model name or None.

    Returns:
        The version name written ("vNNN").
    '''
    index_root = data_dir / "index"
    index_root.mkdir(parents=True, exist_ok=True)
    number = 1
    if latest_version(index_root) is not None:
        number = int(latest_version(index_root)[1:]) + 1  # type: ignore[union-attr]
    version = f"v{number:03d}"
    directory = index_root / version
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)

    bm25.save(directory / "bm25")
    if embeddings is not None:
        np.save(directory / "emb.npy", embeddings)
    _dump_jsonl(directory / "chunks.jsonl", [c.__dict__ for c in chunks])
    _dump_jsonl(directory / "pages.jsonl", page_records)

    docs: dict[str, dict[str, int]] = {}
    pages_seen: set[tuple[str, int]] = set()
    for chunk in chunks:
        stats = docs.setdefault(chunk.doc_id, {"chunks": 0, "pages": 0})
        stats["chunks"] += 1
        pages_seen.add((chunk.doc_id, chunk.page_pdf))
    for doc_id, _page_pdf in pages_seen:
        docs[doc_id]["pages"] += 1
    built_at = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest = {
        "version": version,
        "built_at": built_at,
        "embed_model": embed_model,
        "n_chunks": len(chunks),
        "n_pages": len(pages_seen),
        "docs": docs,
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    _write_pointer(data_dir, version)
    return version


def _read_pointer(data_dir: Path) -> str | None:
    '''Read current.json, tolerating absence or corruption.'''
    pointer = data_dir / "current.json"
    if not pointer.is_file():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
        version = data.get("version")
        return version if isinstance(version, str) else None
    except (OSError, ValueError):
        return None


def _write_pointer(data_dir: Path, version: str) -> None:
    '''Flip current.json to the given version.'''
    data_dir.mkdir(parents=True, exist_ok=True)
    pointer = data_dir / "current.json"
    pointer.write_text(
        json.dumps({"version": version}, ensure_ascii=False), encoding="utf-8"
    )


def _load_chunks(path: Path) -> list[Chunk]:
    '''Load chunks.jsonl back into Chunk objects.'''
    chunks: list[Chunk] = []
    if not path.is_file():
        return chunks
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        data["section_path"] = data.get("section_path") or []
        chunks.append(Chunk(**data))
    return chunks


def _load_pages(path: Path) -> dict[tuple[str, int], str]:
    '''Load pages.jsonl into a (doc_id, page) → text map.'''
    pages: dict[tuple[str, int], str] = {}
    if not path.is_file():
        return pages
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        pages[(data["doc_id"], int(data["page_pdf"]))] = data.get("text", "")
    return pages


def _dump_jsonl(path: Path, records: list[dict]) -> None:
    '''Write records as UTF-8 JSONL.'''
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


__all__: list[str] = [
    "IndexManifest",
    "StoredIndex",
    "latest_version",
    "read_current",
    "write_version",
]
