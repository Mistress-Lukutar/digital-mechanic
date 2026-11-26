'''
File:   wordforms.py
Brief:  Corpus word-form dictionary for gluing broken words.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

The 236 RE and 236 RK text layers split words mid-string, sometimes with a
full-width gap ("по дшипнико в", "динамометр ических"); zero-gap pieces are
already glued by layout. This module builds a word-form frequency table
from the corpus itself, and textnorm uses it to join adjacent fragments
when the fragments are not words but their sum is.

The dictionary is derived data and stays in gitignored data/rag/ — it is a
token list, not extracted manual text, but it lives next to the indexes
all the same.
'''

from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

# Minimum frequency for a form to count as a known word.
MIN_FREQUENCY = 3
# Simple word token: letters (any script) plus internal hyphens.
_WORD = re.compile(r"[а-яёa-z]{2,}(?:-[а-яёa-z]+)*", re.IGNORECASE)


def build_wordforms(pdf_paths: list[Path]) -> dict[str, int]:
    '''Count word forms across the corpus (fast raw-word scan).

    Args:
        pdf_paths: Paths of all manual PDFs.

    Returns:
        Lowercased word form → frequency (forms seen at least once).
    '''
    counts: dict[str, int] = {}
    for path in pdf_paths:
        try:
            with pymupdf.open(path) as doc:
                for page in doc:
                    for word in page.get_text("words"):
                        for token in _WORD.findall(word[4]):
                            lowered = token.lower().replace("ё", "е")
                            counts[lowered] = counts.get(lowered, 0) + 1
        except Exception as exc:  # noqa: BLE001 - skip unreadable files
            print(f"wordforms: skipping {path.name}: {exc}")
    return counts


def prune(counts: dict[str, int]) -> dict[str, int]:
    '''Keep only forms seen at least MIN_FREQUENCY times.

    Args:
        counts: Raw frequency table.

    Returns:
        Pruned dictionary.
    '''
    return {
        word: count
        for word, count in counts.items()
        if count >= MIN_FREQUENCY
    }


def fragments(counts: dict[str, int]) -> dict[str, int]:
    '''Keep forms that can be word FRAGMENTS (same threshold).

    A form that always appears broken ("ических" from
    "динамометрических") never reaches whole-word status; this view of
    the same table drives the fragment-merge rule.

    Args:
        counts: Raw frequency table.

    Returns:
        Frequent forms (fragments or words alike).
    '''
    return prune(counts)


def save(counts: dict[str, int], path: Path) -> None:
    '''Write the dictionary as JSON.

    Args:
        counts: Pruned frequency table.
        path: Output path (gitignored data/rag).
    '''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(counts, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def load(path: Path) -> dict[str, int]:
    '''Load the dictionary; missing file means "no glue".

    Args:
        path: Dictionary path.

    Returns:
        Frequency table, empty when absent.
    '''
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in data.items()}
    except (OSError, ValueError):
        return {}


__all__: list[str] = [
    "MIN_FREQUENCY",
    "build_wordforms",
    "load",
    "prune",
    "save",
]
