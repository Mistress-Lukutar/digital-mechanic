'''
File:   test_guard.py
Brief:  Copyright guards: PDFs, indexes, eval quotes and prompt excerpts
        never enter the repository.
Author: Demetrius242
Date:   2026-11-26
Version: v0.2.0
'''

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_gitignore_covers_manuals_and_rag() -> None:
    '''.gitignore must keep PDFs, extracted text and indexes out of git.'''
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/manuals/*.pdf" in ignored, "PDF manuals must be gitignored"
    assert "data/rag/" in ignored, "built indexes must be gitignored"


def test_no_eval_sets_committed() -> None:
    '''eval question sets live outside the repository: golden.jsonl quotes
    exact values from the manuals, so data/eval must not carry them.'''
    eval_dir = REPO_ROOT / "data" / "eval"
    committed = sorted(eval_dir.glob("*.jsonl")) if eval_dir.is_dir() else []
    assert committed == [], (
        "eval question sets must be connected via RAG_EVAL_DIR from a "
        "directory external to the repository, not committed"
    )


def test_system_prompt_skeleton_has_no_quoted_values() -> None:
    '''the committed prompt skeleton stays quote-free; the manual-specific
    block (manual map and examples quoting the manuals) is inserted at
    runtime from PROMPT_MANUAL_FILE.'''
    prompt_file = REPO_ROOT / "prompts" / "system.md"
    content = prompt_file.read_text(encoding="utf-8")
    # Torque/clearance units only ever appeared inside quoted examples.
    assert "Н·м" not in content, "quoted manual values must stay external"
    assert "кгс·м" not in content, "quoted manual values must stay external"


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
