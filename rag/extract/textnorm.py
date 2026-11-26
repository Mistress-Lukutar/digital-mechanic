'''
File:   textnorm.py
Brief:  Text normalisation: hyphens, broken words, ranges, letter spacing.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Cleans assembled page text without touching meaning: glues hyphenated line
breaks, joins letter-spaced headings ("Р Е З Ь Б О В Ы Х"), normalises number
ranges to one form ("***REMOVED***" → "***REMOVED***") and keeps model prefixes
("ЯМЗ-\n5362") intact.
'''

from __future__ import annotations

import re

# lower/upper Cyrillic letter + hyphen + letter across a line break → join.
_HYPHEN_LOWER = re.compile(r"(?<=[а-яё])-(?:\s+)(?=[а-яё])")
_HYPHEN_UPPER = re.compile(r"(?<=[А-ЯЁ])-(?:\s+)(?=[А-ЯЁ])")
# Model prefix before a break ("ЯМЗ-", "5362-"): keep the hyphen, drop the break.
_PREFIX_BREAK = re.compile(r"(?<=[А-ЯЁ0-9]{2})-(?:\s+)(?=[А-ЯЁ0-9])")
# Ranges split by spaces or written with en/em dashes: "***REMOVED***", "***REMOVED***".
_RANGE_SPACES = re.compile(r"(?<=[0-9]) +[-–—] +(?=[0-9])")
_RANGE_DASH = re.compile(r"(?<=[0-9])[–—](?=[0-9])")
# En/em dash between numbers without spaces ("430–470").
# (kept distinct from _RANGE_SPACES for readability of the rules)

# A line where most space-separated tokens are single Cyrillic letters is a
# letter-spaced heading; its tokens are joined into one word.
_SINGLETON = re.compile(r"^[А-ЯЁа-яё]$")


def _join_spaced(line: str) -> str:
    '''Join letter-spaced tokens of one line into words.

    Runs of single-letter tokens are merged ("Р Е З Ь Б О В Ы Х" →
    "РЕЗЬБОВЫХ"); anything longer than one letter is left untouched, so
    "М10" or ordinary text pass through.

    Args:
        line: One line of page text.

    Returns:
        Line with letter-spaced runs collapsed.
    '''
    tokens = line.split()
    if not tokens:
        return line
    out: list[str] = []
    run: list[str] = []
    runs = 0
    for token in tokens:
        if _SINGLETON.match(token):
            run.append(token)
            continue
        if run:
            if len(run) >= 3:
                out.append("".join(run))
                runs += 1
            else:
                out.extend(run)
            run = []
        out.append(token)
    if run:
        if len(run) >= 3:
            out.append("".join(run))
            runs += 1
        else:
            out.extend(run)
    if not runs:
        return line
    return " ".join(out)


def normalize_page_text(text: str) -> str:
    '''Apply all line-break and range normalisations to page text.

    Args:
        text: Page text with ``\\n`` line breaks, as assembled by layout.

    Returns:
        Normalised text with the same line structure.
    '''
    # Soft hyphens appear in extracted runs of some fonts; treat them as
    # real hyphens so the range and glue rules see them.
    text = text.replace("\u00ad", "-")
    # Hyphen rules run on the whole page so breaks between lines are seen;
    # spaces around the hyphen appear when layout put the halves on
    # separate visual lines with an indent between them.
    text = _HYPHEN_LOWER.sub("", text)
    text = _HYPHEN_UPPER.sub("", text)
    text = _PREFIX_BREAK.sub("-", text)
    # Letter spacing is a per-line property.
    lines = [_join_spaced(line) for line in text.split("\n")]
    text = "\n".join(lines)
    # Range normalisation: one canonical form "***REMOVED***", "***REMOVED***".
    text = _RANGE_SPACES.sub("-", text)
    text = _RANGE_DASH.sub("-", text)
    return text


__all__: list[str] = ["normalize_page_text"]
