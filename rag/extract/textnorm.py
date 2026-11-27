'''
File:   textnorm.py
Brief:  Text normalisation: hyphens, broken words, ranges, letter spacing.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Cleans assembled page text without touching meaning: glues hyphenated line
breaks, joins letter-spaced headings ("Р Е З Ь Б О В Ы Х"), normalises number
ranges to one form ("95- 110" → "95-110") and keeps model prefixes
("ЯМЗ-\n5362") intact.
'''

from __future__ import annotations

import re

# lower/upper Cyrillic letter + hyphen + letter across a line break → join.
_HYPHEN_LOWER = re.compile(r"(?<=[а-яё])-(?:\s+)(?=[а-яё])")
_HYPHEN_UPPER = re.compile(r"(?<=[А-ЯЁ])-(?:\s+)(?=[А-ЯЁ])")
# Model prefix before a break ("ЯМЗ-", "5362-"): keep the hyphen, drop the break.
_PREFIX_BREAK = re.compile(r"(?<=[А-ЯЁ0-9]{2})-(?:\s+)(?=[А-ЯЁ0-9])")
# Ranges split by spaces or written with en/em dashes: "95- 110", "12…15,7".
_RANGE_SPACES = re.compile(r"(?<=[0-9]) +[-–—] +(?=[0-9])")
_RANGE_DASH = re.compile(r"(?<=[0-9])[–—](?=[0-9])")
# En/em dash between numbers without spaces ("415–455").
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


def glue_broken_words(
    text: str,
    wordforms: dict[str, int] | None = None,
    fragment_forms: dict[str, int] | None = None,
) -> str:
    '''Join space-broken word fragments using the corpus dictionary.

    The layer splits words mid-string with real spaces ("по дшипнико в").
    Adjacent tokens are merged when their concatenation is a known word
    form and the right-hand fragment is not one itself (or is a stub of
    one or two letters). Sums of two and three fragments are tried, per
    plan-B rule 5.3. Words that are ALWAYS broken ("динамометр ических"
    — the whole form never appears) merge instead when the right-hand
    piece is a frequent fragment and not a word.

    Args:
        text: Page text with ``\\n`` line breaks.
        wordforms: Corpus word-form dictionary; None disables the glue.
        fragment_forms: Frequent fragment table for the always-broken rule.

    Returns:
        Text with broken words joined.
    '''
    if not wordforms and not fragment_forms:
        return text
    out_lines: list[str] = []
    for line in text.split("\n"):
        tokens = line.split()
        if len(tokens) >= 2:
            merged: list[str] = []
            i = 0
            while i < len(tokens):
                joined = _try_merge(
                    tokens, i, wordforms or {}, fragment_forms or {}
                )
                if joined is not None:
                    word, consumed = joined
                    merged.append(word)
                    i += consumed
                else:
                    merged.append(tokens[i])
                    i += 1
            line = " ".join(merged)
        out_lines.append(line)
    return "\n".join(out_lines)


def _try_merge(
    tokens: list[str],
    start: int,
    wordforms: dict[str, int],
    fragment_forms: dict[str, int],
) -> tuple[str, int] | None:
    '''Return (merged word, fragments consumed) when 2-3 fragments form one.

    Args:
        tokens: Line tokens.
        start: Index of the first fragment.
        wordforms: Whole-word dictionary.
        fragment_forms: Frequent-fragment table.

    Returns:
        (merged token including trailing punctuation, tokens consumed),
        or None.
    '''
    for take in (3, 2):
        if start + take > len(tokens):
            continue
        parts = tokens[start : start + take]
        cores = [_strip_tail(p) for p in parts]
        if any(not core for core in cores):
            continue
        # The right-hand fragments must not be full words themselves,
        # unless they are tiny stubs ("в", "ко").
        for core in cores[1:]:
            if len(core) > 2 and core in wordforms:
                break
        else:
            candidate = "".join(cores)
            if len(candidate) <= 30 and _strip_tail(candidate) in wordforms:
                _head, tail = _split_tail(parts[-1])
                return candidate + tail, take
            # Always-broken words: the right piece is a frequent fragment
            # but never a whole word ("динамометр ических"), both pieces
            # are substantial.
            if take == 2 and fragment_forms:
                left, right = cores
                if (
                    len(left) >= 4
                    and len(right) >= 4
                    and right not in wordforms
                    and right in fragment_forms
                    and left in fragment_forms
                ):
                    _head, tail = _split_tail(parts[-1])
                    return candidate + tail, take
    return None


def _strip_tail(token: str) -> str:
    '''Strip trailing punctuation from a token (":", ",", ".").'''
    return token.rstrip(".,:;!)(")


def _split_tail(token: str) -> tuple[str, str]:
    '''Split a token into (head without trailing punctuation, punctuation).'''
    stripped = token.rstrip(".,:;!)(")
    return stripped, token[len(stripped) :]


def normalize_page_text(
    text: str,
    wordforms: dict[str, int] | None = None,
    fragment_forms: dict[str, int] | None = None,
) -> str:
    '''Apply all line-break and range normalisations to page text.

    Args:
        text: Page text with ``\\n`` line breaks, as assembled by layout.
        wordforms: Optional corpus dictionary for the broken-word glue.
        fragment_forms: Optional frequent-fragment table (always-broken
            words).

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
    # Broken-word glue needs the dictionary; cheap no-op without it.
    text = glue_broken_words(text, wordforms, fragment_forms)
    # Range normalisation: one canonical form "415-455", "12…15,7".
    text = _RANGE_SPACES.sub("-", text)
    text = _RANGE_DASH.sub("-", text)
    return text


__all__: list[str] = ["normalize_page_text"]
