'''
File:   expand.py
Brief:  Query expansion: slang replacement and fault-topic detection.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Fault codes F01–F14 exist only in the mock fleet data; the manuals never
contain them. The bridge is lexical: the mechanic's words are rewritten
into manual terminology (synonyms.yaml) and, when the query is clearly
about one fault type, the fault's own search formulations join the query.
The same detection decides whether a "no instructions" coverage cell
must refuse the query outright.
'''

from __future__ import annotations

import re

from rag.index.tokenizer import normalize_text
from rag.knowledge.loader import CoverageStatus, Knowledge, Synonym

# Maximum fault formulation queries added per request.
MAX_FAULT_QUERIES = 3


def _slang_pattern(slang: str) -> re.Pattern[str]:
    '''Compile a word-boundary pattern for one slang term.'''
    escaped = re.escape(slang)
    return re.compile(
        r"(?<![а-яёa-z0-9])" + escaped + r"(?![а-яёa-z0-9])", re.IGNORECASE
    )


def replace_slang(query: str, synonyms: list[Synonym]) -> str:
    '''Rewrite mechanic slang into manual terminology.

    Args:
        query: Raw query text.
        synonyms: Slang → term list.

    Returns:
        Query with slang replaced (both forms kept by the caller).
    '''
    result = query
    for synonym in synonyms:
        for slang in synonym.slang:
            result = _slang_pattern(slang).sub(synonym.term, result)
    return result


def detect_fault(
    query: str,
    knowledge: Knowledge,
    fault_code: str | None = None,
) -> str | None:
    '''Detect the fault topic of a query, or honour an explicit code.

    With an explicit *fault_code* it is returned as-is. Otherwise the query
    is matched against the per-code detection terms; the code whose term
    matched longest wins. Detection terms are specific ("цепь грм", not
    bare "цепь") so electrical-circuit queries never trigger the F14
    "no instructions" refusal.

    Args:
        query: Raw query text.
        knowledge: Loaded knowledge dictionaries.
        fault_code: Optional explicit fault code (F01…F14).

    Returns:
        Fault code or None.
    '''
    if fault_code is not None:
        return fault_code if fault_code in knowledge.faults else None
    normalized = normalize_text(query)
    best_code: str | None = None
    best_len = 0
    for code, info in knowledge.faults.items():
        for term in info.match:
            normalized_term = normalize_text(term)
            if normalized_term and normalized_term in normalized:
                if len(normalized_term) > best_len:
                    best_code, best_len = code, len(normalized_term)
    return best_code


def coverage_for(
    engine_model: str,
    fault_code: str | None,
    knowledge: Knowledge,
) -> tuple[str, CoverageStatus | None]:
    '''Look up the coverage cell for an engine × fault pair.

    Args:
        engine_model: Normalized engine model.
        fault_code: Detected or explicit fault code (may be None).
        knowledge: Loaded knowledge.

    Returns:
        (status, cell) where status is "unknown" and cell None when the
        pair is not in the matrix or no fault code applies.
    '''
    if fault_code is None:
        return "unknown", None
    row = knowledge.coverage.get(engine_model, {})
    cell = row.get(fault_code)
    if cell is None:
        return knowledge.coverage_default, None
    return cell.status, cell


def expand_query(
    query: str,
    fault_code: str | None,
    knowledge: Knowledge,
) -> list[str]:
    '''Build the list of queries to run against the index.

    The original query comes first (slang-replaced copy appended), then up
    to three manual-terminology formulations of the detected fault. Fault
    formulations are NOT added for "none" cells: those queries are refused
    before scoring, so the effort would be wasted. Moment-torque queries
    ("затягиваются болты...") gain the appendix-table wording ("момент
    затяжки") the same way — assembly prose otherwise outranks the norm
    tables (issue: golden g10).

    Args:
        query: Raw query text.
        fault_code: Detected or explicit fault code (may be None).
        knowledge: Loaded knowledge.

    Returns:
        Query variants, best-first.
    '''
    queries: list[str] = [query]
    rewritten = replace_slang(query, knowledge.synonyms)
    if rewritten.strip() and rewritten.strip() != query.strip():
        queries.append(rewritten)
    info = knowledge.faults.get(fault_code) if fault_code else None
    if info is not None:
        for formulation in info.queries[:MAX_FAULT_QUERIES]:
            if formulation not in queries:
                queries.append(formulation)
    queries.extend(_moment_formulations(query, knowledge, queries))
    return queries


def _moment_formulations(
    query: str,
    knowledge: Knowledge,
    existing: list[str],
) -> list[str]:
    '''Extra formulations for moment-torque queries.

    Assembly instructions say «затягиваются болты крепления…» while the
    norm appendix tables are titled «Моменты затяжки…»: a query about
    tightening gets the table wording as an additional variant, so the
    appendix competes with the prose it should outrank. Skipped when the
    query already carries the formulation phrase (no redundant variants).

    Args:
        query: Original query text.
        knowledge: Loaded knowledge (moment match terms and queries).
        existing: Query variants gathered so far (for deduplication).

    Returns:
        Formulations to append (deduplicated against *existing*).
    '''
    moment = knowledge.moment
    if not moment.queries or not moment.match:
        return []
    normalized = normalize_text(query)
    triggered = any(normalize_text(term) in normalized for term in moment.match)
    if not triggered:
        return []
    if any(normalize_text(f) in normalized for f in moment.queries):
        return []
    return [f for f in moment.queries if f not in existing]


__all__: list[str] = [
    "MAX_FAULT_QUERIES",
    "coverage_for",
    "detect_fault",
    "expand_query",
    "replace_slang",
]
