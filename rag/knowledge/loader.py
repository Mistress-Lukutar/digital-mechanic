'''
File:   loader.py
Brief:  Reading and validating the hand-written knowledge YAML files.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

The dictionaries (docs passport, fault terms, mechanic slang, coverage
matrix) live in rag/knowledge/*.yaml, versioned with the code. Built
artefacts stay in data/rag/ which is gitignored — extracted manual text
never enters the repository.
'''

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass
class DocInfo:
    '''B-side facts about one manual (id/title/engines come from the manifest).'''

    doc_id: str
    file: str
    aliases: list[str] = field(default_factory=list)
    fingerprint: str | None = None  # regex over the first pages
    toc_source: str = "auto"  # auto | printed | modules
    toc_pages: list[int] = field(default_factory=list)
    toc_offset: int | None = None  # None → auto-detect
    fallback_sections: list[dict] = field(default_factory=list)


@dataclass
class FaultInfo:
    '''Search formulations and detection terms for one fault code.'''

    code: str
    title: str
    queries: list[str] = field(default_factory=list)
    match: list[str] = field(default_factory=list)


@dataclass
class Synonym:
    '''Mechanic slang → manual term.'''

    slang: list[str]
    term: str


@dataclass
class CoverageStatus:
    '''One engine × fault-code cell.'''

    status: str  # covered | partial | none | unknown
    note: str | None = None


@dataclass
class MomentInfo:
    '''Moment-torque wording bridge (assembly prose → appendix tables).'''

    match: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)


@dataclass
class Knowledge:
    '''Everything loaded from rag/knowledge.'''

    docs: dict[str, DocInfo] = field(default_factory=dict)
    faults: dict[str, FaultInfo] = field(default_factory=dict)
    synonyms: list[Synonym] = field(default_factory=list)
    moment: MomentInfo = field(default_factory=MomentInfo)
    coverage: dict[str, dict[str, CoverageStatus]] = field(default_factory=dict)
    coverage_default: str = "unknown"


def load_knowledge(directory: Path) -> Knowledge:
    '''Load and validate all YAML files from *directory*.

    Args:
        directory: rag/knowledge directory.

    Returns:
        Parsed knowledge.

    Raises:
        FileNotFoundError: When a required YAML file is missing.
        ValueError: When a file has an invalid structure.
    '''
    knowledge = Knowledge()
    knowledge.docs = _load_docs(directory / "docs.yaml")
    knowledge.faults = _load_faults(directory / "faults.yaml")
    knowledge.synonyms, knowledge.moment = _load_synonyms(
        directory / "synonyms.yaml"
    )
    knowledge.coverage, knowledge.coverage_default = _load_coverage(
        directory / "coverage.yaml"
    )
    return knowledge


def _read_yaml(path: Path) -> dict:
    '''Read one YAML file, raising clear errors.'''
    if not path.is_file():
        raise FileNotFoundError(f"knowledge file not found: {path}")
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a mapping at the top level")
    return data


def _load_docs(path: Path) -> dict[str, DocInfo]:
    '''Parse docs.yaml.'''
    data = _read_yaml(path)
    docs: dict[str, DocInfo] = {}
    for doc_id, raw in (data.get("docs") or {}).items():
        if not isinstance(raw, dict) or "file" not in raw:
            raise ValueError(f"{path.name}: doc {doc_id!r} needs a 'file' field")
        docs[doc_id] = DocInfo(
            doc_id=str(doc_id),
            file=str(raw["file"]),
            aliases=[str(a) for a in raw.get("aliases", [])],
            fingerprint=raw.get("fingerprint"),
            toc_source=str(raw.get("toc", {}).get("source", "auto")),
            toc_pages=[int(p) for p in raw.get("toc", {}).get("pages", [])],
            toc_offset=raw.get("toc", {}).get("offset"),
            fallback_sections=list(raw.get("fallback_sections", [])),
        )
    return docs


def _load_faults(path: Path) -> dict[str, FaultInfo]:
    '''Parse faults.yaml.'''
    data = _read_yaml(path)
    faults: dict[str, FaultInfo] = {}
    for code, raw in (data.get("faults") or {}).items():
        faults[str(code)] = FaultInfo(
            code=str(code),
            title=str(raw.get("title", code)),
            queries=[str(q) for q in raw.get("queries", [])],
            match=[str(m) for m in raw.get("match", [])],
        )
    return faults


def _load_synonyms(path: Path) -> tuple[list[Synonym], MomentInfo]:
    '''Parse synonyms.yaml (slang terms + the moment-wording bridge).'''
    data = _read_yaml(path)
    result: list[Synonym] = []
    for item in data.get("synonyms", []):
        slang = [str(s) for s in item.get("slang", [])]
        term = str(item.get("term", ""))
        if slang and term:
            result.append(Synonym(slang=slang, term=term))
    raw_moment = data.get("moment") or {}
    moment = MomentInfo(
        match=[str(m) for m in raw_moment.get("match", [])],
        queries=[str(q) for q in raw_moment.get("queries", [])],
    )
    return result, moment


def _load_coverage(
    path: Path,
) -> tuple[dict[str, dict[str, CoverageStatus]], str]:
    '''Parse coverage.yaml.'''
    data = _read_yaml(path)
    default = str(data.get("default", "unknown"))
    cells: dict[str, dict[str, CoverageStatus]] = {}
    for engine, codes in (data.get("cells") or {}).items():
        row: dict[str, CoverageStatus] = {}
        for code, raw in (codes or {}).items():
            if isinstance(raw, str):
                row[str(code)] = CoverageStatus(status=raw)
            elif isinstance(raw, dict):
                row[str(code)] = CoverageStatus(
                    status=str(raw.get("status", "unknown")),
                    note=raw.get("note"),
                )
        cells[str(engine)] = row
    return cells, default


@lru_cache(maxsize=4)
def _cached_load(directory: str) -> Knowledge:
    '''Cache wrapper around load_knowledge (paths are hashable strings).'''
    return load_knowledge(Path(directory))


def load_knowledge_cached(directory: Path) -> Knowledge:
    '''Load knowledge with a small process cache (service startup path).'''
    return _cached_load(str(directory))


__all__: list[str] = [
    "CoverageStatus",
    "DocInfo",
    "FaultInfo",
    "Knowledge",
    "MomentInfo",
    "Synonym",
    "load_knowledge",
    "load_knowledge_cached",
]
