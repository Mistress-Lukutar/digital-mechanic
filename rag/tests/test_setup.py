'''
File:   test_setup.py
Brief:  Manual recognition by name, alias and fingerprint.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

import json
from pathlib import Path

from rag.extract.passport import measure
from rag.knowledge.loader import DocInfo, load_knowledge
from rag.setup import place, recognise
from rag.tests.synth import write_manifest, write_manual

REPO_ROOT = Path(__file__).resolve().parents[2]


def _mini_pdf(path: Path, pages: int, designation: str) -> None:
    '''A minimal synthetic manual with the designation on the cover.'''
    cover = [
        ((100.0, 200.0), designation, 16.0),
        *[
            ((60.0, 300.0 + i * 12.0), f"наполнитель страницы {i}", 10.0)
            for i in range(5)
        ],
    ]
    body = [
        ((60.0, 100.0 + i * 12.0), f"страница {i} текст", 10.0) for i in range(8)
    ]
    write_manual(path, [cover] + [body] * (pages - 1))


def test_recognition_by_alias_and_fingerprint(tmp_path: Path) -> None:
    '''files with Russian names are recognised by alias and fingerprint.'''
    manuals = tmp_path / "manuals"
    manuals.mkdir()
    source = tmp_path / "bundle"
    source.mkdir()
    write_manifest(
        manuals / "manifest.json",
        [
            {
                "doc_id": "X-1 РК",
                "file": "x1_rk.pdf",
                "engines": ["Тест"],
                "kind": "repair_manual",
                "title": "X-1",
                "pages": 2,
            }
        ],
    )
    knowledge = load_knowledge(REPO_ROOT / "rag" / "knowledge")
    # Emulate docs.yaml entry for the alias + fingerprint.
    knowledge.docs["X-1 РК"] = DocInfo(
        doc_id="X-1 РК",
        file="x1_rk.pdf",
        aliases=["Руководство Х-1.pdf"],
        fingerprint="Х-?1\\.01",
    )

    _mini_pdf(source / "Руководство Х-1.pdf", pages=2, designation="Х-1.01 РК")
    found, problems = recognise(source, json.loads(
        (manuals / "manifest.json").read_text(encoding="utf-8")
    )["documents"], knowledge.docs)
    assert not problems
    assert found["X-1 РК"].name == "Руководство Х-1.pdf"


def test_page_count_mismatch_rejected(tmp_path: Path) -> None:
    '''a file with the right name but wrong page count is not accepted.'''
    manuals = tmp_path / "manuals"
    manuals.mkdir()
    source = tmp_path / "bundle"
    source.mkdir()
    manifest_docs = [
        {
            "doc_id": "X-1 РК",
            "file": "x1_rk.pdf",
            "engines": ["Тест"],
            "kind": "repair_manual",
            "title": "X-1",
            "pages": 3,
        }
    ]
    write_manifest(manuals / "manifest.json", manifest_docs)
    _mini_pdf(source / "x1_rk.pdf", pages=2, designation="Х-1.01")
    knowledge = load_knowledge(REPO_ROOT / "rag" / "knowledge")
    found, problems = recognise(source, manifest_docs, knowledge.docs)
    assert not found
    assert problems and "not recognised" in problems[0]


def test_place_copies_under_manifest_name(tmp_path: Path) -> None:
    '''placed files land with the manifest file name and content.'''
    manuals = tmp_path / "manuals"
    manuals.mkdir()
    source = tmp_path / "bundle"
    source.mkdir()
    _mini_pdf(source / "x1_rk.pdf", pages=2, designation="Х-1.01")
    manifest_docs = [
        {
            "doc_id": "X-1 РК",
            "file": "x1_rk.pdf",
            "engines": ["Тест"],
            "kind": "repair_manual",
            "title": "X-1",
            "pages": 2,
        }
    ]
    actions = place({"X-1 РК": source / "x1_rk.pdf"}, manuals, manifest_docs)
    assert actions == [("X-1 РК", "copied")]
    target = manuals / "x1_rk.pdf"
    assert target.is_file()
    assert measure(str(target)).pages == 2
    # Second run reports already-placed.
    actions = place({"X-1 РК": source / "x1_rk.pdf"}, manuals, manifest_docs)
    assert actions == [("X-1 РК", "already-placed")]
