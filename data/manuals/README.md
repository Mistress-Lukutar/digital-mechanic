# Engine manuals — not distributed with the repository

Factory repair and operation manuals are copyrighted works, so **the PDF files
and any text extracted from them are not included in this repository** (and must
never enter its history).

To run the knowledge-base features locally, obtain the six issued manuals from
the hackathon materials and place the files in this folder using exactly the
file names from `manifest.json`:

| doc_id (specification §3) | Expected file name | Engines |
|---|---|---|
| `236-3902150-Б РЭ` | `yamz-236_re_2010.pdf` | ЯМЗ-236М2 |
| `236.01.01 РК` | `yamz-236_rk_2014.pdf` | ЯМЗ-236М2 |
| `536.3902150 РЭ` | `yamz-536_re_2016.pdf` | ЯМЗ-536 |
| `536.01.02 РК` | `yamz-536_rk_2013.pdf` | ЯМЗ-536 |
| `ЗМЗ-5234.10 РК` | `zmz-5234_rk_2025.pdf` | ЗМЗ-5234.10 |
| `ЗМЗ-409 РЭТОиР` | `zmz-40904-40905_rk_2025.pdf` | ЗМЗ-40904.10, ЗМЗ-40905.10 |

Alternatively, point the application at an external, access-controlled location
via the `MANUALS_DIR` variable in `.env` — the external knowledge base is
connected through configuration, not committed to Git.

## Fetching at deploy time

At deploy time the documents can be pulled from the shared storage folder
automatically. Put the shared link into the gitignored `.env` (the link
itself must never be committed — this is checked by a guard test):

    MANUALS_DOWNLOAD_URL=https://...   # your .env, not .env.example

then run one of:

    scripts\fetch_manuals.bat            # Windows
    scripts/fetch_manuals.sh             # Linux/macOS
    python scripts/fetch_manuals.py      # directly

The script downloads the PDFs (and case DOCX files, if wanted — see
`--ext`) into `MANUALS_DIR`, skips files already present with the same
size and tolerates flaky networks by retrying. After it finishes,
recognise/rename the files and build the index:

    python -m rag.setup --from <MANUALS_DIR>

With no manuals available the application still runs: diagnostics, fleet views
and ticketing work; the document panel and manual search degrade to an explicit
"manual files unavailable" answer instead of invented content.
