# RAG module (participant B) — manual search for Digital Mechanic

Standalone FastAPI service that turns the six issued engine manuals into a
search service for the agent: `POST /search` with strict per-engine
filtering and an honest "no instructions" signal, plus page retrieval.
Contract shapes come from `shared/models.py` (`SearchHit`, `SearchResponse`,
`PageContent`) — the backend (participant A) calls this service over HTTP
via `RAG_API_URL` and needs no code changes to switch from its mock.

**Copyright:** the PDF manuals are not part of this repository and must
never enter it (no files, no extracted text, no indexes). Everything built
from the PDFs lands in gitignored `data/rag/`; this is guarded by tests
(`rag/tests/test_guard.py`).

## One-command setup

Place the issued PDFs (any file names — the two Russian-named files from
the hackathon bundle are recognised too) into a directory, then:

```bash
python -m rag.setup --from "C:\\path\\to\\pdfs"
```

The command recognises every manual (manifest file name → documented alias
→ page count + cover fingerprint), places it under the manifest file name
in `MANUALS_DIR` (default `data/manuals`, shared with the backend so the
document panel can serve the PDFs), builds the search index and prints a
summary. Options: `--link` hard-link instead of copy, `--no-embed`
BM25-only index without the embedding model download (~2.3 GB), `--skip-ingest`
place files only.

Manual steps, if you prefer:

```bash
# files are already under data/manuals/ with manifest names, or set MANUALS_DIR
python -m rag.ingest                 # build the index (BM25 + embeddings)
python -m rag.ingest --no-embed      # BM25-only build
uvicorn rag.service:app --port 8003  # serve (RAG_API_URL in the backend .env)
python -m rag.eval --set all         # quality gate before every stage commit
```

Dependencies: `pip install -r rag/requirements.txt` (PyMuPDF, numpy/scipy,
PyStemmer, PyYAML; sentence-transformers for the dense part). fastapi,
uvicorn, pydantic, httpx and pytest come from the root project — do not
edit the root `pyproject.toml` (participant A owns it).

## Service contract (fixed, issue #1)

- `POST /search` `{query, engine_model, top_k=5}` →
  `{"results": [{doc_id, doc_title, page_pdf, section, text, score, tier}],
  "no_instruction"}`. Engine filtering happens BEFORE scoring; nothing
  above threshold → `{"results": [], "no_instruction": true}`.
- `GET /document/{doc_id}/page/{page_pdf}` → `PageContent` (page text +
  local `pdf_path`, may be null).
- `GET /health` → index version, mode (`hybrid` | `bm25`), per-doc stats.
- `doc_id` values are the manifest designations ("236.01.01 РК"), cited
  verbatim in chat and stored in tickets; pages are 1-based PDF pages.

The optional extension fields `fault_code` and `doc_id` are accepted but
never required — the backend's current client does not send them.

## How it works

```
PDFs ──► rag/ingest.py ──► data/rag/index/vNNN/  +  rag/knowledge/*.yaml
           extract: coordinate reading order (fixes the scrambled 236 RE
           tables), ruled tables → markdown, hyphen/soft-hyphen/range
           normalisation, corpus-dictionary glue for broken words
           ("по дшипнико в"), running-header removal, printed-TOC parsing
           with offset detection, module registry for 536 RK
           chunks: page-bounded, ≤700 chars, never cross a page
           index:  BM25 (Lucene formula, scipy CSR) + bge-m3 embeddings
                   with a text-hash cache; RRF fusion
           search: engine mask before scoring → query expansion (fault
                   terms F01–F14, mechanic slang) → BM25 ∥ dense → RRF →
                   tier (high/med/low over a comparable score) → honest
                   no_instruction (verified-none coverage cells, empty
                   results)
```

The knowledge dictionaries live in `rag/knowledge/*.yaml` (versioned with
the code): the doc passport with fingerprints and TOC hints, fault terms,
slang synonyms and the engine × fault coverage matrix whose `none` cells
drive the refusal behaviour the jury checks.

## Configuration (environment / .env)

| Variable | Default | Meaning |
|---|---|---|
| `MANUALS_DIR` | `data/manuals` | manifest + PDF files (shared with the backend) |
| `RAG_DATA_DIR` | `data/rag` | built artifacts (gitignored) |
| `RAG_EVAL_DIR` | `data/eval` | external question sets — not committed, point outside the repo |
| `RAG_EMBED_MODEL` | `BAAI/bge-m3` | `none` disables the dense part |
| `RAG_DEVICE` | `auto` | `cpu` or `cuda` |
| `RAG_TIER_HIGH` / `RAG_TIER_MED` | `0.70` / `0.55` | tier thresholds |
| `RAG_INDEX_VERSION` | latest | pin a specific version |

Without the embedding model the service degrades to BM25 (`/health` shows
`mode: bm25`); without any built index it answers 503 with a hint.

## Tests and quality gates

```bash
pytest rag/tests   # 41 tests on synthetic PDFs (no real manuals needed)
pytest             # the backend suite stays green (no A-owned file touched)
ruff check rag
python -m rag.eval --set all   # hit@1/hit@5 (+1 page), MRR, refusal rate
```

Eval sets live OUTSIDE the repository (set `RAG_EVAL_DIR`, e.g. the
sibling `../rag-eval` folder; see its README): golden values verified
against rendered page images, section-lookup questions with gold pages,
and must-refuse questions for the verified "no instructions" cells.
`golden.jsonl` quotes the manuals' exact values, so the sets are never
committed — same policy as the PDFs themselves.
