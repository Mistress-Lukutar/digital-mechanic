'''
File:   test_api.py
Brief:  HTTP contract via TestClient (shapes from shared/models.py).
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from fastapi.testclient import TestClient

from rag.config import get_settings
from rag.service import app


def _client(monkeypatch, rag_settings) -> TestClient:
    '''A TestClient over the service pointed at the synthetic index.'''
    monkeypatch.setenv("MANUALS_DIR", str(rag_settings.manuals_dir))
    monkeypatch.setenv("RAG_DATA_DIR", str(rag_settings.data_dir))
    monkeypatch.setenv("RAG_EVAL_DIR", str(rag_settings.eval_dir))
    monkeypatch.setenv("RAG_EMBED_MODEL", "none")
    get_settings.cache_clear()
    return TestClient(app)


def test_search_contract(monkeypatch, built_index, rag_settings) -> None:
    '''POST /search returns the exact contract shape.'''
    with _client(monkeypatch, rag_settings) as client:
        response = client.post(
            "/search",
            json={
                "query": "момент затяжки крышек коренных подшипников",
                "engine_model": "Тест-236М2",
                "top_k": 5,
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"results", "no_instruction"}
    assert isinstance(data["no_instruction"], bool)
    for hit in data["results"]:
        assert set(hit) == {
            "doc_id", "doc_title", "page_pdf", "section", "text", "score", "tier",
        }
        assert hit["page_pdf"] >= 1
        assert hit["tier"] in ("high", "med", "low", None)


def test_search_filters_foreign_engine(monkeypatch, built_index, rag_settings) -> None:
    '''a query with an unknown engine is refused, not answered loosely.'''
    with _client(monkeypatch, rag_settings) as client:
        response = client.post(
            "/search",
            json={"query": "момент затяжки", "engine_model": "Небыл-ДВС"},
        )
    assert response.status_code == 200
    assert response.json() == {"results": [], "no_instruction": True}


def test_search_validates_input(monkeypatch, built_index, rag_settings) -> None:
    '''blank queries and bad top_k are 422; unknown fault_code too.'''
    with _client(monkeypatch, rag_settings) as client:
        blank = client.post(
            "/search", json={"query": "   ", "engine_model": "Тест-236М2"}
        )
        bad_top_k = client.post(
            "/search",
            json={"query": "зазор", "engine_model": "Тест-236М2", "top_k": 99},
        )
        bad_fault = client.post(
            "/search",
            json={
                "query": "зазор",
                "engine_model": "Тест-236М2",
                "fault_code": "F99",
            },
        )
    assert blank.status_code == 422
    assert bad_top_k.status_code == 422
    assert bad_fault.status_code == 422


def test_document_page(monkeypatch, built_index, rag_settings) -> None:
    '''GET /document returns page text and the PDF path; 404 for missing.'''
    with _client(monkeypatch, rag_settings) as client:
        from urllib.parse import quote

        doc_id = quote("TEST-1 РК", safe="")
        ok = client.get(f"/document/{doc_id}/page/3")
        missing = client.get(f"/document/{doc_id}/page/999")
        unknown = client.get(f"/document/{quote('NOPE', safe='')}/page/1")
    assert ok.status_code == 200
    page = ok.json()
    assert page["doc_id"] == "TEST-1 РК"
    assert page["page_pdf"] == 3
    assert "Момент затяжки" in page["text"]
    assert page["pdf_path"] and page["pdf_path"].endswith("test_manual.pdf")
    assert missing.status_code == 404
    assert unknown.status_code == 404


def test_health_and_no_index(monkeypatch, rag_settings, tmp_path) -> None:
    '''/health reports the loaded index; a fresh dir gives 503 on /search.'''
    monkeypatch.setenv("MANUALS_DIR", str(rag_settings.manuals_dir))
    monkeypatch.setenv("RAG_DATA_DIR", str(tmp_path / "empty"))  # nothing built
    monkeypatch.setenv("RAG_EMBED_MODEL", "none")
    get_settings.cache_clear()
    with TestClient(app) as client:
        health = client.get("/health")
        refused = client.post(
            "/search", json={"query": "зазор", "engine_model": "Тест-236М2"}
        )
    assert health.status_code == 200
    assert health.json()["status"] == "no_index"
    assert refused.status_code == 503
    assert "python -m rag.ingest" in refused.json()["detail"]
