'''
File:   test_guard.py
Brief:  Copyright guards: PDFs and indexes never enter the repository.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_gitignore_covers_manuals_and_rag() -> None:
    '''.gitignore must keep PDFs, extracted text and indexes out of git.'''
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/manuals/*.pdf" in ignored, "PDF manuals must be gitignored"
    assert "data/rag/" in ignored, "built indexes must be gitignored"


def test_knowledge_yaml_has_no_manual_text() -> None:
    '''hand-written dictionaries carry terms, not manual paragraphs.'''
    knowledge_dir = REPO_ROOT / "rag" / "knowledge"
    for yaml_file in knowledge_dir.glob("*.yaml"):
        content = yaml_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            # Long unbroken Russian strings would smell like copied text.
            if stripped.startswith("#") or not stripped:
                continue
            assert len(stripped) < 200, f"{yaml_file.name}: suspiciously long line"
