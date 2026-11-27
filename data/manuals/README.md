# Engine manuals — not distributed with the repository

Factory repair and operation manuals are copyrighted works, so **the PDF files
and any text extracted from them are not included in this repository** (and must
never enter its history). They are fetched and built **outside git** at deploy
time: the documents land in `MANUALS_DIR` (external directory by configuration),
the extracted text and the search index are cached in the gitignored
`RAG_DATA_DIR` (default `data/rag/`).

## Deploy bootstrap (recommended)

One command does everything — download what is missing, recognise the
manuals, build the embeddings index, cache it:

    scripts\bootstrap.bat            # Windows
    scripts/bootstrap.sh             # Linux/macOS
    python scripts/bootstrap.py      # directly

The link to the shared storage folder comes from the gitignored `.env`
(the link itself must never be committed — this is checked by a guard
test):

    MANUALS_DOWNLOAD_URL=https://...   # your .env, not .env.example

The bootstrap is idempotent: already-downloaded files are skipped by
size, and a built index is reused instead of rebuilt (`--force-index`
rebuilds; `--no-embed` builds a BM25-only index without the ~2.3 GB
embedding model download).

## Manual fallback

Without the shared link, obtain the six issued manuals from the
hackathon materials and place them (original names are fine — `rag.setup`
recognises documented aliases) into the directory `MANUALS_DIR` points
to, then run the same bootstrap. Expected file names per `manifest.json`:

| doc_id (specification §3) | Expected file name | Engines |
|---|---|---|
| `236-3902150-Б РЭ` | `yamz-236_re_2010.pdf` | ЯМЗ-236М2 |
| `236.01.01 РК` | `yamz-236_rk_2014.pdf` | ЯМЗ-236М2 |
| `536.3902150 РЭ` | `yamz-536_re_2016.pdf` | ЯМЗ-536 |
| `536.01.02 РК` | `yamz-536_rk_2013.pdf` | ЯМЗ-536 |
| `ЗМЗ-5234.10 РК` | `zmz-5234_rk_2025.pdf` | ЗМЗ-5234.10 |
| `ЗМЗ-409 РЭТОиР` | `zmz-40904-40905_rk_2025.pdf` | ЗМЗ-40904.10, ЗМЗ-40905.10 |

Under the default configuration `MANUALS_DIR=data/manuals` inside the
repository tree; the folder is gitignored for PDFs, but an **external**
directory via `MANUALS_DIR` in `.env` keeps even the local copies out of
the repository tree and is the recommended setup.

With no manuals available the application still runs: diagnostics, fleet views
and ticketing work; the document panel and manual search degrade to an explicit
"manual files unavailable" answer instead of invented content.
