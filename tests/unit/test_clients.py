'''
File:   test_clients.py
Brief:  Unit tests for MlClient, ToirClient and RagClient using
        httpx.MockTransport and async fixtures.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from shared.models import (
    DiagnosticResult,
    PageContent,
    SearchResponse,
    TicketPayload,
    TicketResult,
)

from mechanic.errors import MockApiError, RagUnavailableError
from mechanic.services.ml_client import MlClient
from mechanic.services.rag_client import RagClient, normalize_doc_id
from mechanic.services.toir_client import ToirClient

# ======================================================================
# Helper: a single mock transport that dispatches on URL path.
# ======================================================================


def _ml_handler(request: httpx.Request) -> httpx.Response:
    """Mock handler for ML / TOiR endpoints."""
    if request.url.path == "/diagnose":
        return httpx.Response(200, json={
            "vehicle_id": "M333YK47",
            "session_id": "S-0005",
            "status": "anomaly",
            "anomaly_type": "F08",
            "anomaly_title": "Дизельная топливоподача",
            "anomaly_score": 0.76,
            "confidence": 0.73,
            "signal_quality": "good",
            "description": "Жёсткая работа с резким стуком в цилиндрах, дымный выхлоп",
            "model_version": "mock-v1",
        })
    if request.url.path == "/tickets":
        return httpx.Response(201, json={
            "ticket_id": "TKT-0001",
            "status": "created",
        })
    if request.url.path == "/search":
        return httpx.Response(200, json={
            "results": [],
            "no_instruction": False,
        })
    if request.url.path.startswith("/document/"):
        return httpx.Response(200, json={
            "doc_id": "236.01.01 РК",
            "doc_title": "ЯМЗ-236. Руководство по ремонту 236.01.01 РК (2014)",
            "page_pdf": 1,
            "text": "Page content here.",
            "pdf_path": "/data/manuals/yamz-236_rk_2014.pdf",
        })
    return httpx.Response(500, text="unknown path")


# ======================================================================
# ML client tests
# ======================================================================


@pytest.fixture()
def ml_http():
    """httpx.AsyncClient using the shared mock transport."""
    transport = httpx.MockTransport(_ml_handler)
    client = httpx.AsyncClient(transport=transport)
    return client


async def test_ml_client_parses_result(ml_http: httpx.AsyncClient) -> None:
    """MlClient.diagnose() returns a valid DiagnosticResult from 200 response."""
    client = MlClient(base_url="http://mock-ml", http=ml_http)
    try:
        result = await client.diagnose("M333YK47", "S-0005")
        assert isinstance(result, DiagnosticResult)
        assert result.vehicle_id == "M333YK47"
        assert result.session_id == "S-0005"
        assert result.status == "anomaly"
        assert result.anomaly_type == "F08"
        assert result.anomaly_score == 0.76
    finally:
        await ml_http.aclose()


async def test_ml_client_maps_404(ml_http: httpx.AsyncClient) -> None:
    """MlClient.diagnose() raises MockApiError on non-200 with detail field."""
    # Override the handler to return 404.
    def _handler_404(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/diagnose":
            return httpx.Response(404, json={"detail": "vehicle_id not found"})
        return httpx.Response(500, text="unknown")

    transport = httpx.MockTransport(_handler_404)
    client_obj = httpx.AsyncClient(transport=transport)
    try:
        ml = MlClient(base_url="http://mock-ml", http=client_obj)
        with pytest.raises(MockApiError) as exc_info:
            await ml.diagnose("M333YK47", "S-0005")
        assert exc_info.value.status_code == 404
        assert "vehicle" in str(exc_info.value).lower()
    finally:
        await client_obj.aclose()


async def test_ml_client_unreachable(ml_http: httpx.AsyncClient) -> None:
    """MlClient.diagnose() raises MockApiError(503) on connection error."""
    def _handler_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(_handler_connect_error)
    client_obj = httpx.AsyncClient(transport=transport)
    try:
        ml = MlClient(base_url="http://mock-ml", http=client_obj)
        with pytest.raises(MockApiError) as exc_info:
            await ml.diagnose("M333YK47", "S-0005")
        assert exc_info.value.status_code == 503
    finally:
        await client_obj.aclose()


# ======================================================================
# TOiR client tests
# ======================================================================


async def test_toir_client_created(ml_http: httpx.AsyncClient) -> None:
    """ToirClient.submit_ticket() returns TicketResult from 201 response."""
    payload = TicketPayload(
        vehicle_id="M333YK47",
        session_id="S-0005",
        anomaly_type="F08",
        conclusion="Дизельная топливоподача — требуется замена форсунок",
        urgency="high",
        operations=["Проверка топливной системы", "Замена ТНВД"],
        spare_parts=["Форсунка 1", "Форсунка 4"],
        references=[{"manual": "236.01.01 РК", "pdf_page": 1}],
    )

    client = ToirClient(base_url="http://mock-toir", http=ml_http)
    try:
        result = await client.submit_ticket(payload)
        assert isinstance(result, TicketResult)
        assert result.ticket_id == "TKT-0001"
        assert result.status == "created"
    finally:
        await ml_http.aclose()


async def test_toir_client_maps_422(ml_http: httpx.AsyncClient) -> None:
    """ToirClient.submit_ticket() raises MockApiError on non-201."""
    def _handler_422(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tickets":
            return httpx.Response(422, json={"detail": "validation error"})
        return httpx.Response(500, text="unknown")

    transport = httpx.MockTransport(_handler_422)
    client_obj = httpx.AsyncClient(transport=transport)
    try:
        tc = ToirClient(base_url="http://mock-toir", http=client_obj)
        with pytest.raises(MockApiError) as exc_info:
            await tc.submit_ticket(TicketPayload(
                vehicle_id="M333YK47",
                session_id="S-0005",
                anomaly_type="F08",
                conclusion="test",
                urgency="high",
                operations=["op1"],
                references=[{"manual": "236.01.01 РК", "pdf_page": 1}],
            ))
        assert exc_info.value.status_code == 422
    finally:
        await client_obj.aclose()


# ======================================================================
# RAG client tests
# ======================================================================


async def test_rag_search_no_chunks_file(ml_http: httpx.AsyncClient) -> None:
    """RagClient.search() with no chunks file returns empty on service down."""

    def _handler_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(_handler_connect_error)
    client_obj = httpx.AsyncClient(transport=transport)
    try:
        rag = RagClient(
            base_url="http://rag.invalid",
            mock_chunks_path=None,
            manuals_dir=Path("data/manuals"),
            http=client_obj,
        )
        result = await rag.search("момент затяжки", "ЯМЗ-236М2")
        assert isinstance(result, SearchResponse)
        assert result.no_instruction is True
        assert len(result.results) == 0
    finally:
        await client_obj.aclose()


async def test_rag_search_mock_chunks(tmp_path: Path) -> None:
    """RagClient.search() falls back to mock JSONL chunks when service is down."""
    # Write a mock chunks file with two entries.
    chunks_data = [
        {
            "doc_id": "236.01.01 РК",
            "doc_title": "ЯМЗ-236. Руководство по ремонту 236.01.01 РК (2014)",
            "engine": "ЯМЗ-236М2",
            "page_pdf": 42,
            "section": "Топливная система",
            "text": "Момент затяжки болтов головки цилиндра 205 Нм",
        },
        {
            "doc_id": "536.3902150 РЭ",
            "doc_title": "ЯМЗ-536. Руководство по эксплуатации 536.3902150 РЭ (2016)",
            "engine": "ЯМЗ-536",
            "page_pdf": 10,
            "section": "Двигатель",
            "text": "Техническое обслуживание двигателя",
        },
    ]

    mock_chunks = tmp_path / "mock_chunks.jsonl"
    with open(mock_chunks, "w", encoding="utf-8") as f:
        for chunk in chunks_data:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    def _handler_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(_handler_connect_error)
    client_obj = httpx.AsyncClient(transport=transport)
    try:
        rag = RagClient(
            base_url="http://rag.invalid",
            mock_chunks_path=mock_chunks,
            manuals_dir=Path("data/manuals"),
            http=client_obj,
        )

        # Search for "момент затяжки" on engine ЯМЗ-236М2.
        result = await rag.search("момент затяжки", "ЯМЗ-236М2")
        assert isinstance(result, SearchResponse)
        assert result.no_instruction is False
        assert len(result.results) == 1
        hit = result.results[0]
        assert hit.doc_id == "236.01.01 РК"
        assert hit.tier is not None

        # Search for "момент затяжки" on engine ЯМЗ-536 → no match.
        result2 = await rag.search("момент затяжки", "ЯМЗ-536")
        assert isinstance(result2, SearchResponse)
        assert result2.no_instruction is True
        assert len(result2.results) == 0
    finally:
        await client_obj.aclose()


async def test_rag_get_page_local_fallback(
    ml_http: httpx.AsyncClient, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """RagClient.get_page() falls back to local manifest when service is down."""

    def _handler_connect_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    transport = httpx.MockTransport(_handler_connect_error)
    client_obj = httpx.AsyncClient(transport=transport)
    try:
        # "236.01.01 РК" is in manifest but PDF absent on disk (temp dir).
        temp_manuals = tmp_path_factory.getbasetemp() / "manuals_test"
        temp_manifest = temp_manuals / "manifest.json"
        temp_manifest.parent.mkdir(parents=True, exist_ok=True)

        # Copy just the manifest without PDFs.
        import shutil
        src_manifest = Path("data/manuals/manifest.json")
        shutil.copy(src_manifest, temp_manifest)

        rag2 = RagClient(
            base_url="http://rag.invalid",
            mock_chunks_path=None,
            manuals_dir=temp_manuals,
            http=client_obj,
        )

        # "236.01.01 РК" is in manifest but PDF absent on disk
        with pytest.raises(RagUnavailableError) as exc_info:
            await rag2.get_page("236.01.01 РК", 1)
        assert "not available on this server" in str(exc_info.value)

        # "NOT-REAL" is not in manifest → RagUnavailableError
        with pytest.raises(RagUnavailableError) as exc_info:
            await rag2.get_page("NOT-REAL", 1)
        assert "not in the manuals manifest" in str(exc_info.value)
    finally:
        await client_obj.aclose()


async def test_rag_get_page_from_service(ml_http: httpx.AsyncClient) -> None:
    """RagClient.get_page() returns PageContent from 200 service response."""
    rag = RagClient(
        base_url="http://rag-service",
        mock_chunks_path=None,
        manuals_dir=Path("data/manuals"),
        http=ml_http,
    )
    try:
        result = await rag.get_page("236.01.01 РК", 1)
        assert isinstance(result, PageContent)
        assert result.doc_id == "236.01.01 РК"
        assert result.page_pdf == 1
        assert result.text == "Page content here."
    finally:
        await ml_http.aclose()


# ======================================================================
# normalize_doc_id unit tests
# ======================================================================


def test_normalize_doc_id_strips_guillemets() -> None:
    """normalize_doc_id removes « and » characters."""
    assert normalize_doc_id("«ЗМЗ-409 РЭТОиР»") == "ЗМЗ-409 РЭТОиР"


def test_normalize_doc_id_collapses_whitespace() -> None:
    """normalize_doc_id collapses internal whitespace runs to a single space."""
    assert normalize_doc_id(" 236.01.01  РК ") == "236.01.01 РК"


def test_normalize_doc_id_clean_unchanged() -> None:
    """normalize_doc_id returns clean ids unchanged."""
    assert normalize_doc_id("236.01.01 РК") == "236.01.01 РК"


# ======================================================================
# get_page guillemets regression test
# ======================================================================


async def test_rag_get_page_clean_url_with_guillemets(
    ml_http: httpx.AsyncClient,
) -> None:
    """RagClient.get_page() with «» in doc_id requests the clean URL."""
    captured_path: list[str] = []

    def _handler_capture(request: httpx.Request) -> httpx.Response:
        captured_path.append(request.url.path)
        return httpx.Response(200, json={
            "doc_id": "236.01.01 РК",
            "doc_title": "ЯМЗ-236. Руководство по ремонту 236.01.01 РК (2014)",
            "page_pdf": 1,
            "text": "Page content here.",
            "pdf_path": "/data/manuals/yamz-236_rk_2014.pdf",
        })

    transport = httpx.MockTransport(_handler_capture)
    client_obj = httpx.AsyncClient(transport=transport)
    try:
        rag = RagClient(
            base_url="http://rag-service",
            mock_chunks_path=None,
            manuals_dir=Path("data/manuals"),
            http=client_obj,
        )
        await rag.get_page("«236.01.01 РК»", 1)
        # The path should contain the cleaned doc_id, not «236.01.01 РК»
        assert len(captured_path) == 1
        assert "/document/236.01.01 РК/page/1" in captured_path[0]
    finally:
        await client_obj.aclose()
