'''
File:   conftest.py
Brief:  Shared fixtures: synthetic manuals, settings, built index.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

The copyrighted manuals are never used in tests — everything runs on
synthetic PDFs built on the fly (rag/tests/synth.py).
'''

from __future__ import annotations

from pathlib import Path

import pytest

from rag.config import RagSettings
from rag.index.store import read_current
from rag.ingest import run_ingest
from rag.knowledge.loader import Knowledge, load_knowledge
from rag.search import SearchEngine
from rag.tests.synth import write_manifest, write_manual

REPO_ROOT = Path(__file__).resolve().parents[2]


# Pages of the synthetic manual: cover, TOC, two content pages.
TEST_FILE = "test_manual.pdf"
MANIFEST_DOC: dict[str, str | list[str] | int] = {
    "doc_id": "TEST-1 РК",
    "file": TEST_FILE,
    "engines": ["Тест-236М2"],
    "kind": "repair_manual",
    "title": "Тестовое руководство TEST-1 РК",
    "pages": 4,
}

TOC_LINES = [
    "Раздел первый ......... 3",
    "Моменты затяжки ....... 3",
    "Другой раздел ......... 4",
    "И ещё раздел .......... 4",
    "Пятый раздел .......... 4",
    "Шестой раздел ......... 4",
    "Седьмой раздел ........ 4",
    "Восьмой раздел ........ 4",
    "Девятый раздел ........ 4",
]


@pytest.fixture()
def manuals_dir(tmp_path: Path) -> Path:
    '''A manuals directory with a manifest and one synthetic manual.'''
    path = tmp_path / "manuals"
    path.mkdir()
    write_manifest(path / "manifest.json", [MANIFEST_DOC])
    toc = [(50, 70 + i * 14) for i in range(len(TOC_LINES))]
    write_manual(
        path / TEST_FILE,
        [
            [((200, 400), "ТЕСТ-1.01 РК", 18)],
            [
                ((50, 70), "Содержание", 14),
                *[
                    ((toc[i][0], toc[i][1]), text, 11)
                    for i, text in enumerate(TOC_LINES)
                ],
            ],
            [
                ((60, 100), "Момент затяжки крышек коренных", 11),
                ((60, 115), "подшипников: вертикальные ***REMOVED*** ***REMOVED***,", 11),
                ((60, 130), "горизонтальные ***REMOVED*** ***REMOVED***.", 11),
                ((60, 200), "Раздел первый описывает регулировку клапанного", 11),
                ((60, 215), "механизма. Тепловые зазоры клапанов ***REMOVED*** мм.", 11),
                ((60, 700), "3", 9),
            ],
            [
                *[
                    (
                        (60, 80 + i * 12),
                        f"Строка номер {i} про электрическую цепь стартера и узлы.",
                        11,
                    )
                    for i in range(30)
                ],
                ((60, 700), "4", 9),
            ],
        ],
    )
    return path


@pytest.fixture()
def rag_settings(manuals_dir: Path, tmp_path: Path) -> RagSettings:
    '''Settings pointing at the synthetic manuals and a temp data dir.'''
    return RagSettings(
        _env_file=None,
        manuals_dir=manuals_dir,
        data_dir=tmp_path / "rag",
        eval_dir=tmp_path,
        embed_model="none",
    )


@pytest.fixture()
def built_index(rag_settings: RagSettings):
    '''The stored index built from the synthetic manual (BM25-only).'''
    run_ingest(
        pdf_dir=rag_settings.manuals_dir,
        data_dir=rag_settings.data_dir,
        use_embeddings=False,
        settings=rag_settings,
    )
    return read_current(rag_settings.data_dir)


@pytest.fixture()
def engine(built_index, rag_settings: RagSettings) -> SearchEngine:
    '''A BM25-only search engine over the synthetic index.'''
    knowledge: Knowledge = load_knowledge(REPO_ROOT / "rag" / "knowledge")
    return SearchEngine(built_index, knowledge, rag_settings, dense=None)
