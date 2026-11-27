"""
File:   test_agent_tools.py
Brief:  Tests for agent tools (diagnostics, manuals, vehicles, tickets, documents)
        and the prompt builder.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Builds a ServiceHub manually from real data files, uses httpx.MockTransport
for ML/RAG clients, and verifies tool executors produce the expected outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from shared.models import (
    Reference,
    TicketPayload,
    TicketResult,
)

from mechanic.agent.tools_base import (
    ToolContext,
    ToolError,
    ToolOutcome,
)
from mechanic.config import Settings
from mechanic.services.auth import AuthService
from mechanic.services.chats import ChatStore
from mechanic.services.fleet import FleetStore
from mechanic.services.hub import ServiceHub
from mechanic.services.ml_client import MlClient
from mechanic.services.rag_client import ManualManifest, RagClient
from mechanic.services.ticket_log import TicketLog
from mechanic.services.toir_client import ToirClient
from mechanic.services.usage import UsageLog

# ---------------------------------------------------------------------------
# Paths relative to the repo root.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def _mock_ml_handler(request: httpx.Request) -> httpx.Response:
    """Handle ML diagnose requests in tests."""
    body = json.loads(request.content.decode())
    vid = body.get("vehicle_id", "")
    sid = body.get("session_id", "")

    # Known good session.
    if vid == "M333YK47" and sid == "S-0005":
        payload = {
            "vehicle_id": "M333YK47",
            "session_id": "S-0005",
            "status": "anomaly",
            "anomaly_type": "F08",
            "anomaly_title": "Дизельная топливоподача",
            "anomaly_score": 0.76,
            "confidence": 0.73,
            "signal_quality": "good",
            "description": "Жёсткая работа с резким стуком в цилиндрах",
            "model_version": "mock-v1",
        }
        return httpx.Response(200, json=payload)

    # Unknown session → 404.
    if vid == "M333YK47" and sid == "S-9999":
        return httpx.Response(404, json={"detail": "session not found"})

    # Default: some other result.
    payload = {
        "vehicle_id": vid,
        "session_id": sid,
        "status": "anomaly",
        "anomaly_type": "F08",
        "anomaly_title": "Дизельная топливоподача",
        "anomaly_score": 0.76,
        "confidence": 0.73,
        "signal_quality": "good",
        "description": "Test",
        "model_version": "mock-v1",
    }
    return httpx.Response(200, json=payload)


def _mock_rag_search_handler(request: httpx.Request) -> httpx.Response:
    """Handle RAG search requests in tests."""
    body = json.loads(request.content.decode())
    query = body.get("query", "")
    engine = body.get("engine_model", "")

    if "топливо" in query.lower() and engine == "ЯМЗ-236М2":
        hits = [
            {
                "doc_id": "236.01.01 РК",
                "doc_title": "ЯМЗ-236. Руководство по ремонту",
                "page_pdf": 112,
                "section": "Топливная система",
                "text": "Проверьте форсунки на герметичность и корректность впрыска.",
                "score": 0.85,
                "tier": "high",
            }
        ]
        return httpx.Response(200, json={"results": hits, "no_instruction": False})

    return httpx.Response(200, json={"results": [], "no_instruction": True})


def _mock_rag_page_handler(request: httpx.Request) -> httpx.Response:
    """Handle RAG get_page requests in tests."""
    path = request.url.path
    parts = path.split("/")
    try:
        doc_id_idx = parts.index("document") + 1
        page_idx = parts.index("page") + 1
        doc_id = parts[doc_id_idx]
        page_num = int(parts[page_idx])
    except (ValueError, IndexError):
        return httpx.Response(404, json={"detail": "not found"})

    payload = {
        "doc_id": doc_id,
        "doc_title": "ЯМЗ-236. Руководство по ремонту",
        "page_pdf": page_num,
        "text": f"Текст страницы {page_num} документа {doc_id}.",
        "pdf_path": "/data/manuals/yamz-236_rk_2014.pdf",
    }
    return httpx.Response(200, json=payload)


# ---------------------------------------------------------------------------
# Hub builder for tests.
# ---------------------------------------------------------------------------


class _CombinedTransport(httpx.AsyncBaseTransport):
    """Routes /search to one mock and everything else to another."""

    def __init__(
        self, search_transport: httpx.MockTransport, page_transport: httpx.MockTransport
    ) -> None:
        self._search = search_transport
        self._page = page_transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if "/search" in str(request.url.path):
            return await self._search.handle_async_request(request)
        return await self._page.handle_async_request(request)


def _build_test_hub(
    ml_transport: httpx.MockTransport | None = None,
    rag_search_transport: httpx.MockTransport | None = None,
    rag_page_transport: httpx.MockTransport | None = None,
    mock_chunks_path: Path | None = None,
) -> ServiceHub:
    """Construct a ServiceHub for testing.

    Args:
        ml_transport: Optional MockTransport for MlClient.
        rag_search_transport: Optional MockTransport for RAG search.
        rag_page_transport: Optional MockTransport for RAG get_page.
        mock_chunks_path: Optional path to a mock chunks JSONL file.

    Returns:
        A fully wired ServiceHub ready for tool testing.
    """
    settings = Settings(_env_file=None, app_data_dir=DATA_DIR)

    # ML client.
    if ml_transport is not None:
        ml = MlClient(
            settings.ml_api_url,
            http=httpx.AsyncClient(transport=ml_transport),
        )
    else:
        ml = MlClient(settings.ml_api_url)

    # RAG client.
    rag_base = settings.rag_api_url
    if rag_search_transport is not None and rag_page_transport is not None:
        combined = _CombinedTransport(rag_search_transport, rag_page_transport)
        rag = RagClient(
            base_url=rag_base,
            mock_chunks_path=mock_chunks_path,
            manuals_dir=settings.manuals_dir,
            http=httpx.AsyncClient(transport=combined),
        )
    else:
        rag = RagClient(
            base_url=rag_base,
            mock_chunks_path=mock_chunks_path,
            manuals_dir=settings.manuals_dir,
        )

    hub = ServiceHub(
        settings=settings,
        fleet=FleetStore(DATA_DIR),
        ml=ml,
        toir=ToirClient(settings.toir_api_url),
        rag=rag,
        manifest=ManualManifest(settings.manuals_dir),
        ticket_log=TicketLog(DATA_DIR / "test_tickets.db"),
        chats=ChatStore(DATA_DIR / "test_chats.db"),
        usage=UsageLog(DATA_DIR / "test_usage.db"),
        auth=AuthService(DATA_DIR / "test_auth.db"),
    )
    return hub


def ctx(
    vehicle_id: str = "M333YK47",
    session_id: str | None = "S-0005",
    hub: ServiceHub | None = None,
) -> ToolContext:
    """Build a ToolContext for testing.

    Args:
        vehicle_id: Selected vehicle ID.
        session_id: Selected session ID.
        hub: Optional pre-built ServiceHub; creates one if omitted.

    Returns:
        A ToolContext with the given parameters and services wired.
    """
    if hub is None:
        hub = _build_test_hub()
    return ToolContext(
        vehicle_id=vehicle_id,
        session_id=session_id,
        username="mechanic",
        services=hub,
    )


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


class TestGetDiagnosticResult:
    """Tests for get_diagnostic_result tool."""

    @pytest.mark.asyncio
    async def test_get_diagnostic_result_content(self) -> None:
        """ML 200 → content contains 'F08' and 'S-0005'."""
        transport = httpx.MockTransport(_mock_ml_handler)
        hub = _build_test_hub(ml_transport=transport)
        context = ctx(vehicle_id="M333YK47", session_id="S-0005", hub=hub)

        from mechanic.agent.tools_impl.diagnostics import (
            make_get_diagnostic_result_tool,
        )

        tool_def = make_get_diagnostic_result_tool()(hub)
        result = await tool_def.executor({}, context)

        assert isinstance(result, str)
        assert "F08" in result
        assert "S-0005" in result

    @pytest.mark.asyncio
    async def test_get_diagnostic_result_unknown_session(self) -> None:
        """ML 404 → ToolError with 'ML-сервис'."""
        transport = httpx.MockTransport(_mock_ml_handler)
        hub = _build_test_hub(ml_transport=transport)
        context = ctx(vehicle_id="M333YK47", session_id="S-9999", hub=hub)

        from mechanic.agent.tools_impl.diagnostics import (
            make_get_diagnostic_result_tool,
        )

        tool_def = make_get_diagnostic_result_tool()(hub)
        with pytest.raises(ToolError) as exc_info:
            await tool_def.executor({}, context)

        assert "ML-сервис" in str(exc_info.value)


class TestSearchManuals:
    """Tests for search_manuals tool."""

    @pytest.mark.asyncio
    async def test_search_manuals_no_instruction(
        self, tmp_path: Path
    ) -> None:
        """RAG connection error + no chunks → NO_INSTRUCTION, not error."""

        def _failing_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        chunks_file = tmp_path / "mock_chunks.jsonl"
        chunks_file.write_text("")  # empty file.

        hub = _build_test_hub(
            rag_search_transport=httpx.MockTransport(_failing_handler),
            rag_page_transport=httpx.MockTransport(_mock_rag_page_handler),
            mock_chunks_path=chunks_file,
        )
        context = ctx(vehicle_id="M333YK47", hub=hub)

        from mechanic.agent.tools_impl.manuals import make_search_manuals_tool

        tool_def = make_search_manuals_tool()(hub)
        result = await tool_def.executor({"query": "топливо"}, context)

        assert isinstance(result, ToolOutcome)
        assert "NO_INSTRUCTION" in result.content
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_search_manuals_hits(self, tmp_path: Path) -> None:
        """RAG 200 with matching chunk → content contains hit citation."""
        chunks_file = tmp_path / "mock_chunks.jsonl"
        chunk_data = {
            "doc_id": "236.01.01 РК",
            "doc_title": "ЯМЗ-236. Руководство по ремонту",
            "page_pdf": 112,
            "section": "Топливная система",
            "text": "Проверьте форсунки на герметичность.",
            "engine": "ЯМЗ-236М2",
        }
        chunks_file.write_text(json.dumps(chunk_data) + "\n")

        hub = _build_test_hub(
            rag_search_transport=httpx.MockTransport(_mock_rag_search_handler),
            rag_page_transport=httpx.MockTransport(_mock_rag_page_handler),
            mock_chunks_path=chunks_file,
        )
        context = ctx(vehicle_id="M333YK47", hub=hub)

        from mechanic.agent.tools_impl.manuals import make_search_manuals_tool

        tool_def = make_search_manuals_tool()(hub)
        result = await tool_def.executor({"query": "топливо"}, context)

        assert isinstance(result, str)
        assert "[236.01.01 РК, стр. 112]" in result


class TestGetVehicleInfo:
    """Tests for get_vehicle_info tool."""

    @pytest.mark.asyncio
    async def test_get_vehicle_info_lists_history_and_tickets(
        self, tmp_path: Path
    ) -> None:
        """Empty log → 'Прошлых заявок нет'; after add → contains ticket ID."""
        db = tmp_path / "test_vehicle_info.db"
        hub = _build_test_hub()
        hub.ticket_log = TicketLog(db)

        context = ctx(vehicle_id="M333YK47", hub=hub)

        from mechanic.agent.tools_impl.vehicles import make_get_vehicle_info_tool

        tool_def = make_get_vehicle_info_tool()(hub)
        result = await tool_def.executor({}, context)

        assert isinstance(result, str)
        assert "ЯМЗ-236М2" in result
        assert "S-0005" in result
        assert "Прошлых заявок нет" in result

        # Add a ticket.
        payload = TicketPayload(
            vehicle_id="M333YK47",
            session_id="S-0005",
            anomaly_type="F08",
            conclusion="Неисправность топливной системы, требуется замена форсунок.",
            urgency="high",
            operations=["Проверить форсунки"],
            references=[Reference(manual="236.01.01 РК", pdf_page=112)],
        )
        hub.ticket_log.add(
            TicketResult(ticket_id="TKT-0001", status="created"),
            payload,
            "admin",
        )

        result2 = await tool_def.executor({}, context)
        assert isinstance(result2, str)
        assert "TKT-0001" in result2


class TestCreateTicket:
    """Tests for create_ticket tool."""

    @pytest.mark.asyncio
    async def test_create_ticket_draft_event(self) -> None:
        """F08 ticket → event name 'ticket_draft', urgency high, rules source."""
        context = ctx(vehicle_id="M333YK47", hub=_build_test_hub())

        from mechanic.agent.tools_impl.tickets import make_create_ticket_tool

        tool_def = make_create_ticket_tool()(context.services)  # type: ignore[arg-type]
        args = {
            "anomaly_type": "F08",
            "conclusion": "Неисправность топливной системы, требуется дефектовка.",
            "operations": ["Проверить форсунки"],
            "references": [
                {"manual": "236.01.01 РК", "pdf_page": 112}
            ],
        }

        result = await tool_def.executor(args, context)

        assert isinstance(result, ToolOutcome)
        assert result.event is not None
        assert result.event[0] == "ticket_draft"
        event_payload = result.event[1]
        payload_data = event_payload["payload"]
        # F08 with score 0.76 → urgency high (rule 1).
        assert payload_data["urgency"] == "high"
        assert event_payload["priority_rationale"] != ""
        assert event_payload["urgency_source"] == "rules"

    @pytest.mark.asyncio
    async def test_create_ticket_agent_urgency_wins(self) -> None:
        """Agent urgency 'low' wins over rules."""
        context = ctx(vehicle_id="M333YK47", hub=_build_test_hub())

        from mechanic.agent.tools_impl.tickets import make_create_ticket_tool

        tool_def = make_create_ticket_tool()(context.services)  # type: ignore[arg-type]
        args = {
            "anomaly_type": "F08",
            "conclusion": "Неисправность топливной системы.",
            "urgency": "low",
            "priority_rationale": "механик сказал низкий",
            "operations": ["Проверить форсунки"],
            "references": [
                {"manual": "236.01.01 РК", "pdf_page": 112}
            ],
        }

        result = await tool_def.executor(args, context)

        assert isinstance(result, ToolOutcome)
        assert result.event is not None
        payload_data = result.event[1]["payload"]
        assert payload_data["urgency"] == "low"
        assert result.event[1]["priority_rationale"] == "механик сказал низкий"
        assert result.event[1]["urgency_source"] == "agent"

    @pytest.mark.asyncio
    async def test_create_ticket_missing_operations(self) -> None:
        """operations=[] → ToolError mentioning operations."""
        context = ctx(vehicle_id="M333YK47", hub=_build_test_hub())

        from mechanic.agent.tools_impl.tickets import make_create_ticket_tool

        tool_def = make_create_ticket_tool()(context.services)  # type: ignore[arg-type]
        args = {
            "anomaly_type": "F08",
            "conclusion": "Тест.",
            "operations": [],
            "references": [
                {"manual": "236.01.01 РК", "pdf_page": 112}
            ],
        }

        with pytest.raises(ToolError) as exc_info:
            await tool_def.executor(args, context)

        assert "operations" in str(exc_info.value).lower()


class TestShowDocument:
    """Tests for show_document tool."""

    @pytest.mark.asyncio
    async def test_show_document_event_and_error(self) -> None:
        """RAG 200 → document event with has_text True; RAG down + no PDF → error."""

        # (a) RAG 200 with mock transport that returns text content.
        hub_a = _build_test_hub(
            rag_search_transport=httpx.MockTransport(_mock_rag_search_handler),
            rag_page_transport=httpx.MockTransport(_mock_rag_page_handler),
        )
        context_a = ctx(vehicle_id="M333YK47", hub=hub_a)

        from mechanic.agent.tools_impl.documents import make_show_document_tool

        tool_def_a = make_show_document_tool()(hub_a)

        result = await tool_def_a.executor(
            {"doc_id": "236.01.01 РК", "page_pdf": 112}, context_a
        )
        assert isinstance(result, ToolOutcome)
        assert result.event is not None
        assert result.event[0] == "document"
        assert result.event[1]["has_text"] is True

        # (b) RAG down + doc_id whose PDF is absent.
        class _NoPdfPageTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(
                self, request: httpx.Request
            ) -> httpx.Response:
                raise httpx.ConnectError("rag service unavailable")

        hub_b = _build_test_hub()
        hub_b.rag = RagClient(
            base_url="http://127.0.0.1:8003",
            mock_chunks_path=None,
            manuals_dir=DATA_DIR / "manuals",
            http=httpx.AsyncClient(transport=_NoPdfPageTransport()),
        )

        context_b = ctx(vehicle_id="M333YK47", hub=hub_b)
        tool_def_b = make_show_document_tool()(hub_b)

        with pytest.raises(ToolError) as exc_info:
            await tool_def_b.executor(
                {"doc_id": "NONEXISTENT", "page_pdf": 1}, context_b
            )

        assert "недоступен" in str(exc_info.value)


class TestBuildRegistry:
    """Tests for build_registry."""

    def test_build_registry_names(self) -> None:
        """build_registry returns tools in the documented order."""
        hub = _build_test_hub()
        from mechanic.agent.tools_impl import build_registry

        reg = build_registry(hub)
        names = reg.names()
        assert names == [
            "get_diagnostic_result",
            "search_manuals",
            "get_vehicle_info",
            "create_ticket",
            "show_document",
        ]


class TestPromptBuilder:
    """Tests for build_system_prompt."""

    def test_prompt_builder_real_template(self, monkeypatch: Any) -> None:
        """Monkeypatch to real prompts dir → contains vehicle data."""
        monkeypatch.setattr(
            "mechanic.agent.prompt.PROMPTS_DIR", REPO_ROOT / "prompts"
        )

        hub = _build_test_hub()
        from mechanic.agent.prompt import build_system_prompt

        result = build_system_prompt(hub, "M333YK47")

        assert "ЯМЗ-236М2" in result
        assert "M333YK47" in result
        assert "\u00ab236.01.01 РК\u00bb" in result
        assert "\u00ab236-3902150-\u0411 \u0420\u042d\u00bb" in result
        assert "{vehicle_block}" not in result
        assert "{docs_block}" not in result

    def test_prompt_builder_fallback(
        self, monkeypatch: Any, tmp_path: Path
    ) -> None:
        """No system.md → fallback template still fills vehicle ID and tool name."""
        monkeypatch.setattr("mechanic.agent.prompt.PROMPTS_DIR", tmp_path)

        hub = _build_test_hub()
        from mechanic.agent.prompt import build_system_prompt

        result = build_system_prompt(hub, "M333YK47")

        assert "M333YK47" in result
        assert "search_manuals" in result


# ---------------------------------------------------------------------------
# Additional document error test (RAG down + PDF absent).
# ---------------------------------------------------------------------------


class TestShowDocumentPDFMissing:
    """Edge case: RAG down and PDF file missing from manifests dir."""

    @pytest.mark.asyncio
    async def test_show_document_pdf_missing(self) -> None:
        """RAG unreachable + no PDF → ToolError with 'недоступен'."""
        hub = _build_test_hub()

        class _NoPdfPageTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(
                self, request: httpx.Request
            ) -> httpx.Response:
                raise httpx.ConnectError("rag service unavailable")

        hub.rag = RagClient(
            base_url="http://127.0.0.1:8003",
            mock_chunks_path=None,
            manuals_dir=DATA_DIR / "manuals",
            http=httpx.AsyncClient(transport=_NoPdfPageTransport()),
        )

        context = ctx(vehicle_id="M333YK47", hub=hub)

        from mechanic.agent.tools_impl.documents import make_show_document_tool

        tool_def = make_show_document_tool()(hub)

        # Use a doc_id whose PDF does NOT exist in the manifests dir.
        with pytest.raises(ToolError) as exc_info:
            await tool_def.executor(
                {"doc_id": "NONEXISTENT", "page_pdf": 1}, context
            )

        assert "недоступен" in str(exc_info.value)
