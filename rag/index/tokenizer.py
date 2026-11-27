'''
File:   tokenizer.py
Brief:  Shared tokenisation for documents and queries.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Tokens keep designation- and value-like strings intact ("ямз-536",
"0,26-0,32", "536.01.02") and expand them: ranges are indexed both whole
and by their boundaries, model designations also yield the prefix and the
number. Alphabetic tokens are stemmed with the Russian Snowball stemmer.
Known layer typos ("ЯМ3") are fixed before stemming.
'''

from __future__ import annotations

import re
from functools import lru_cache

from Stemmer import Stemmer

# Letters/digits with internal punctuation, both sides alphanumeric:
# "ямз-536", "0,26-0,32", "536.01.02", "12…15,7".
_TOKEN = re.compile(
    r"[a-zа-яё0-9]+(?:[-.,…/+][a-zа-яё0-9]+)*", re.IGNORECASE
)
_RANGE = re.compile(r"^(\d+[,.]?\d*)[-–—](\d+[,.]?\d*)$")
_MODEL = re.compile(r"^([a-zа-яё]+)[-.](\d{2,6}[a-zа-яё]*)$", re.IGNORECASE)
_ALPHA = re.compile(r"^[a-zа-яё]+$")
_TYPO_YAM3 = re.compile(r"\bям3\b")

# Small Russian stopword list; everything here is noise in queries.
STOPWORDS: frozenset[str] = frozenset(
    {
        "и", "в", "во", "не", "на", "с", "со", "по", "для", "или", "к", "у",
        "из", "от", "до", "при", "это", "как", "что", "то", "же", "за", "the",
    }
)

_stemmer: Stemmer | None = None


def _get_stemmer() -> Stemmer:
    '''Return the cached Russian Snowball stemmer.'''
    global _stemmer
    if _stemmer is None:
        _stemmer = Stemmer("russian")
    return _stemmer


def normalize_text(text: str) -> str:
    '''Lowercase, map ё→е and fix the known "ЯМ3" layer typo.

    Args:
        text: Arbitrary text.

    Returns:
        Normalized text used for both indexing and queries.
    '''
    lowered = text.lower().replace("ё", "е")
    return _TYPO_YAM3.sub("ямз", lowered)


@lru_cache(maxsize=4096)
def _stem(token: str) -> str:
    '''Stem one alphabetic token (cached).'''
    return _get_stemmer().stemWord(token)


def _variants(token: str) -> list[str]:
    '''Expand one raw token into its indexed forms.

    Args:
        token: Lowercase raw token.

    Returns:
        All forms stored in the index for this token.
    '''
    variants: list[str] = []
    if _ALPHA.match(token):
        variants.append(_stem(token))
        return variants
    # Token with digits or internal punctuation: keep as-is, plus expansions.
    variants.append(token)
    range_match = _RANGE.match(token)
    if range_match:
        variants.append(range_match.group(1))
        variants.append(range_match.group(2))
        return variants
    model_match = _MODEL.match(token)
    if model_match:
        prefix, number = model_match.groups()
        variants.append(prefix)
        variants.append(number)
    return variants


def tokenize(text: str) -> list[str]:
    '''Tokenise text for BM25, sharing one vocabulary with queries.

    Args:
        text: Document chunk or query text (raw case, ё allowed).

    Returns:
        Token list (stems and expansions), stopwords removed.
    '''
    normalized = normalize_text(text)
    tokens: list[str] = []
    for raw in _TOKEN.findall(normalized):
        for variant in _variants(raw):
            if variant in STOPWORDS or len(variant) <= 1 and not variant.isdigit():
                continue
            tokens.append(variant)
    return tokens


__all__: list[str] = ["STOPWORDS", "normalize_text", "tokenize"]
