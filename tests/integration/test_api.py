'''
File:   test_api.py
Brief:  Integration tests for the FastAPI application.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.1

End-to-end tests against ``create_app()`` using ``httpx.AsyncClient`` with
``ASGITransport``. The service hub is initialised directly with test
settings (DB in tmp_path) and external clients use mock transports for
ML / TOiR services; RAG points at an unroutable URL to exercise the
honest fallback paths.
'''

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest
from httpx import ASGITransport

from mechanic.llm import StopReason, TextDelta, TurnComplete
from mechanic.llm.types import ChatRequest, ToolCall, ToolCallsReady

# ---------------------------------------------------------------------------
# Paths and constants.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fake LLM client for SSE chat tests.
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """Minimal fake that yields token + turn_done events."""

    async def stream_chat(
        self, request: ChatRequest
    ) -> AsyncIterator[TextDelta | TurnComplete]:
        """Yield a text delta followed by turn_complete with usage."""
        yield TextDelta("ответ")
        yield TurnComplete(
            stop_reason=StopReason.END_TURN,
            input_tokens=10,
            output_tokens=5,
        )

    async def fetch_models(self, base_url: str, api_key: str) -> list:
        return []


# ---------------------------------------------------------------------------
# Fixture: isolated app with overridden hub.
# ---------------------------------------------------------------------------


@pytest.fixture()
async def app_client(tmp_path: Path) -> httpx.AsyncClient:
    """Build the app with an isolated hub.

    The DB lives in *tmp_path* (``db_file`` override), fleet data is read
    from the committed repo data dir, and the ML/TOiR clients are replaced
    with MockTransport-backed ones. The lifespan is bypassed: singletons
    are initialised directly, and the bootstrap admin is created here.
    """
    from mechanic.api import deps as api_deps
    from mechanic.config import Settings
    from mechanic.main import create_app
    from mechanic.services.ml_client import MlClient
    from mechanic.services.rag_client import RagClient
    from mechanic.services.toir_client import ToirClient

    api_deps._hub = None
    api_deps._app_settings = None
    api_deps._conversations = None

    settings = Settings(
        _env_file=None,
        app_data_dir=REPO_ROOT / "data",
        manuals_dir=REPO_ROOT / "data" / "manuals",
        db_file=tmp_path / "app.db",
        ml_api_url="http://ml.test",
        toir_api_url="http://toir.test",
        rag_api_url="http://rag.test",
    )
    hub = api_deps.init_hub(settings)
    api_deps.init_app_settings(settings)
    hub.auth.bootstrap_admin()

    def _ml_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        vid = body.get("vehicle_id", "") if isinstance(body, dict) else ""
        if vid == "M333YK47":
            return httpx.Response(
                200,
                json={
                    "vehicle_id": "M333YK47",
                    "session_id": "S-0005",
                    "status": "anomaly",
                    "anomaly_type": "F08",
                    "anomaly_title": "Дизельная топливоподача",
                    "anomaly_score": 0.76,
                    "confidence": 0.73,
                    "signal_quality": "good",
                    "description": "Жёсткая работа с резким стуком",
                    "model_version": "mock-v1",
                },
            )
        if vid == "P854BT78":
            return httpx.Response(
                200,
                json={
                    "vehicle_id": "P854BT78",
                    "session_id": "S-0021",
                    "status": "anomaly",
                    "anomaly_type": "F09",
                    "anomaly_title": "Турбокомпрессор",
                    "anomaly_score": 0.72,
                    "confidence": 0.66,
                    "signal_quality": "warning",
                    "description": "Стук в турбине",
                    "model_version": "mock-v1",
                },
            )
        if vid == "M739BA198":
            return httpx.Response(
                200,
                json={
                    "vehicle_id": "M739BA198",
                    "session_id": "S-0103",
                    "status": "anomaly",
                    "anomaly_type": "F02",
                    "anomaly_title": "Давление масла",
                    "anomaly_score": 0.74,
                    "confidence": 0.48,
                    "signal_quality": "warning",
                    "description": "Низкое давление масла",
                    "model_version": "mock-v1",
                },
            )
        if vid == "P456AT178":
            return httpx.Response(
                200,
                json={
                    "vehicle_id": "P456AT178",
                    "session_id": "S-0003",
                    "status": "anomaly",
                    "anomaly_type": "F01",
                    "anomaly_title": "Клапаны",
                    "anomaly_score": 0.71,
                    "confidence": 0.80,
                    "signal_quality": "bad",
                    "description": "Стук клапанов",
                    "model_version": "mock-v1",
                },
            )
        return httpx.Response(404, json={"detail": "vehicle not found"})

    def _toir_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tickets":
            return httpx.Response(
                201, json={"ticket_id": "TKT-0001", "status": "created"}
            )
        return httpx.Response(404, json={"detail": "not found"})

    hub.ml = MlClient(
        "http://ml.test",
        http=httpx.AsyncClient(transport=httpx.MockTransport(_ml_handler)),
    )
    hub.toir = ToirClient(
        "http://toir.test",
        http=httpx.AsyncClient(transport=httpx.MockTransport(_toir_handler)),
    )

    # RAG with unroutable URL → RequestError → honest fallback paths.
    hub.rag = RagClient(
        base_url="http://127.0.0.1:1",
        mock_chunks_path=None,
        manuals_dir=settings.manuals_dir,
    )

    # LLM config for the chat endpoint (fake client is patched per test).
    api_deps.get_app_settings().set(
        "llm",
        {
            "base_url": "http://llm.test/v1",
            "api_key": "test-key-abc123xyz",
            "model": "fake-model",
            "protocol": "openai_compatible",
        },
    )

    app = create_app()
    client = httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )
    yield client
    await client.aclose()

    for service in (hub.auth, hub.ticket_log, hub.usage, hub.alerts):
        try:
            service._conn.close()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    try:
        api_deps.get_app_settings()._conn.close()
    except Exception:  # noqa: BLE001
        pass
    api_deps._hub = None
    api_deps._app_settings = None
    api_deps._conversations = None


# ---------------------------------------------------------------------------
# Helper: login and get token.
# ---------------------------------------------------------------------------


async def _login(client: httpx.AsyncClient, username: str, password: str) -> str:
    """Login and return the auth token."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


async def _admin_login(client: httpx.AsyncClient) -> str:
    """Login as bootstrap admin after setting its password."""
    from mechanic.api.deps import get_hub

    hub = get_hub()
    # The bootstrap admin was created by the fixture; set a known password.
    hub.auth.change_password_admin("admin", "admin-pass-1")
    return await _login(client, "admin", "admin-pass-1")


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


async def test_login_wrong_password_401(app_client: httpx.AsyncClient) -> None:
    """POST /api/auth/login with wrong password returns 401."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "testuser", "password": "pass12345", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    resp = await app_client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "wrongpass"},
    )
    assert resp.status_code == 401


async def test_login_and_me(app_client: httpx.AsyncClient) -> None:
    """Admin login → /api/auth/me returns role admin."""
    token = await _admin_login(app_client)
    resp = await app_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["role"] == "admin"


async def test_vehicles_requires_auth(app_client: httpx.AsyncClient) -> None:
    """GET /api/vehicles without token returns 401."""
    resp = await app_client.get("/api/vehicles")
    assert resp.status_code == 401


async def test_vehicles_list_and_detail(app_client: httpx.AsyncClient) -> None:
    """List vehicles and get detail for M333YK47."""
    token = await _admin_login(app_client)

    resp = await app_client.get(
        "/api/vehicles", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    vehicles = resp.json()
    assert len(vehicles) == 50

    detail_resp = await app_client.get(
        "/api/vehicles/M333YK47", headers={"Authorization": f"Bearer {token}"}
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["vehicle_id"] == "M333YK47"
    assert detail["engine_model"] == "ЯМЗ-236М2"
    assert "sessions" in detail
    assert "tickets" in detail


async def test_fleet_stats_and_priority(app_client: httpx.AsyncClient) -> None:
    """Fleet stats total == 50; priority vehicles are all quarantine."""
    token = await _admin_login(app_client)

    stats_resp = await app_client.get(
        "/api/fleet/stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total"] == 50

    priority_resp = await app_client.get(
        "/api/fleet/priority", headers={"Authorization": f"Bearer {token}"}
    )
    assert priority_resp.status_code == 200
    priorities = priority_resp.json()
    for vehicle in priorities:
        assert vehicle["group"] == "quarantine"


async def test_chat_sse_stream(app_client: httpx.AsyncClient) -> None:
    """Chat SSE stream with fake LLM yields token + turn_done events."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    # Patch the chat module's client factory with our fake.
    import mechanic.api.chat_api as chat_api

    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: FakeLLMClient()  # type: ignore[assignment]

    try:
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "привет", "session_id": "S-0005"},
            headers={"Authorization": f"Bearer {mech_token}"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse_events(resp.text)
        event_names = [e["event"] for e in events]
        assert "token" in event_names, f"Missing token event: {event_names}"
        assert "turn_done" in event_names, f"Missing turn_done event: {event_names}"

        # Usage recorded for this chat request.
        from mechanic.api.deps import get_hub

        hub = get_hub()
        recent = hub.usage.recent(200)
        chat_records = [r for r in recent if r.kind == "chat"]
        assert chat_records, f"No chat records: {[r.kind for r in recent]}"
        assert chat_records[0].input_tokens == 10
        assert chat_records[0].model == "fake-model"
    finally:
        chat_api.get_llm_client = original_get_llm


def _parse_sse_events(text: str) -> list[dict]:
    """Parse SSE-formatted text into event dicts."""
    events: list[dict] = []
    current_event: dict | None = None
    for line in text.split("\n"):
        if line.startswith("event: "):
            current_event = {"event": line[7:], "data": ""}
        elif line.startswith("data: "):
            if current_event is not None:
                current_event["data"] += line[6:]
        elif line == "" and current_event is not None:
            # End of event frame.
            try:
                current_event["_parsed_data"] = json.loads(current_event["data"])
            except (json.JSONDecodeError, ValueError):
                pass
            events.append(current_event)
            current_event = None
    return events


async def test_chat_unknown_vehicle_404(app_client: httpx.AsyncClient) -> None:
    """Chat for unknown vehicle returns 404 before streaming."""
    token = await _admin_login(app_client)
    resp = await app_client.post(
        "/api/chat/UNKNOWN123",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_ticket_submit_flow(app_client: httpx.AsyncClient) -> None:
    """Submit a ticket → mock TOiR returns 201; the local log shows it."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "M333YK47",
        "session_id": "S-0005",
        "anomaly_type": "F08",
        "conclusion": "Стук в топливной аппаратуре",
        "urgency": "high",
        "operations": ["Проверить и отрегулировать топливоподачу"],
        "spare_parts": [],
        "references": [{"manual": "236.01.01 РК", "pdf_page": 50}],
    }

    resp = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticket_id"] == "TKT-0001"

    list_resp = await app_client.get(
        "/api/tickets/M333YK47", headers={"Authorization": f"Bearer {mech_token}"}
    )
    assert list_resp.status_code == 200
    tickets = list_resp.json()
    assert len(tickets) == 1
    assert tickets[0]["payload"]["conclusion"].startswith("Стук")

    # Usage recorded the ticket_submit request.
    from mechanic.api.deps import get_hub

    hub = get_hub()
    kinds = [r.kind for r in hub.usage.recent(200)]
    assert "ticket_submit" in kinds


async def test_ticket_resubmission_same_id_replaces(
    app_client: httpx.AsyncClient,
) -> None:
    """Re-submitting with the same TOiR id replaces the local log row."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "M333YK47",
        "session_id": "S-0005",
        "anomaly_type": "F08",
        "conclusion": "Первый диагноз",
        "urgency": "high",
        "operations": ["Проверить"],
        "spare_parts": [],
        "references": [{"manual": "236.01.01 РК", "pdf_page": 50}],
    }
    first = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert first.status_code == 200

    payload2 = {**payload, "conclusion": "Уточнённый диагноз"}
    second = await app_client.post(
        "/api/tickets",
        json=payload2,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert second.status_code == 200

    list_resp = await app_client.get(
        "/api/tickets/M333YK47", headers={"Authorization": f"Bearer {mech_token}"}
    )
    tickets = list_resp.json()
    assert len(tickets) == 1
    assert tickets[0]["payload"]["conclusion"] == "Уточнённый диагноз"


async def test_ticket_invalid_422_mapped(app_client: httpx.AsyncClient) -> None:
    """Mock TOiR 422 → response status 422."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    from mechanic.api.deps import get_hub
    from mechanic.errors import MockApiError

    hub = get_hub()
    orig_submit = hub.toir.submit_ticket

    async def _mock_submit_bad(*args: object, **kwargs: object) -> object:
        raise MockApiError("mock-toir", 422, "bad payload")

    hub.toir.submit_ticket = _mock_submit_bad  # type: ignore[method-assign]

    try:
        resp = await app_client.post(
            "/api/tickets",
            json={
                "vehicle_id": "M333YK47",
                "session_id": "S-0005",
                "anomaly_type": "F08",
                "conclusion": "test",
                "urgency": "high",
                "operations": ["op1"],
                "references": [{"manual": "236.01.01 РК", "pdf_page": 1}],
            },
            headers={"Authorization": f"Bearer {mech_token}"},
        )
        assert resp.status_code == 422
        assert "bad payload" in resp.json()["detail"]
    finally:
        hub.toir.submit_ticket = orig_submit  # type: ignore[method-assign]


async def test_documents_list_and_page_404(app_client: httpx.AsyncClient) -> None:
    """Documents list returns 6 docs; page access is graceful without RAG."""
    token = await _admin_login(app_client)

    resp = await app_client.get(
        "/api/documents", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    docs = resp.json()
    assert len(docs) == 6
    doc_ids = {d["doc_id"] for d in docs}
    assert "236.01.01 РК" in doc_ids

    # Known doc_id with spaces and Cyrillic in the path.
    encoded = quote("236.01.01 РК", safe="")
    page_resp = await app_client.get(
        f"/api/documents/{encoded}/page/112",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Without the RAG service: PDF present → 200 (text empty, pdf_path set);
    # PDF absent → 404. Both are honest outcomes.
    assert page_resp.status_code in (200, 404)

    unknown_resp = await app_client.get(
        f"/api/documents/{quote('NOPE-123', safe='')}/page/1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unknown_resp.status_code == 404


async def test_admin_settings_masked(app_client: httpx.AsyncClient) -> None:
    """GET /api/admin/settings/llm masks api_key; PUT with empty keeps stored."""
    token = await _admin_login(app_client)

    resp = await app_client.get(
        "/api/admin/settings/llm", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["api_key"] != "test-key-abc123xyz"
    assert "…" in data["api_key"] or data["api_key"] == "***"

    put_resp = await app_client.put(
        "/api/admin/settings/llm",
        json={"api_key": "", "model": "better-model"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["model"] == "better-model"

    # Stored key survived the empty-key PUT.
    from mechanic.api.deps import get_app_settings
    from mechanic.config import Settings as AppCfg
    from mechanic.services.app_settings import effective_llm_config

    cfg = effective_llm_config(AppCfg(_env_file=None), get_app_settings())
    assert cfg.api_key == "test-key-abc123xyz"
    assert cfg.model == "better-model"


async def test_admin_users_crud(app_client: httpx.AsyncClient) -> None:
    """Create user, list, delete, last-admin refusal."""
    token = await _admin_login(app_client)

    resp = await app_client.post(
        "/api/admin/users",
        json={"username": "newuser", "password": "pass12345", "role": "user"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    list_resp = await app_client.get(
        "/api/admin/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert list_resp.status_code == 200
    usernames = [u["username"] for u in list_resp.json()]
    assert "newuser" in usernames

    del_resp = await app_client.delete(
        "/api/admin/users/newuser", headers={"Authorization": f"Bearer {token}"}
    )
    assert del_resp.status_code == 200

    last_del = await app_client.delete(
        "/api/admin/users/admin", headers={"Authorization": f"Bearer {token}"}
    )
    assert last_del.status_code == 400


async def test_admin_required(app_client: httpx.AsyncClient) -> None:
    """Regular user on /api/admin/usage/totals → 403."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    resp = await app_client.get(
        "/api/admin/usage/totals", headers={"Authorization": f"Bearer {mech_token}"}
    )
    assert resp.status_code == 403


async def test_chat_invalid_language_422(app_client: httpx.AsyncClient) -> None:
    """POST /api/chat with language='de' returns 422 (invalid literal)."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    resp = await app_client.post(
        "/api/chat/M333YK47",
        json={"message": "hello", "language": "de"},
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422


async def test_config_status_requires_auth(app_client: httpx.AsyncClient) -> None:
    """GET /api/config-status without token returns 401."""
    resp = await app_client.get("/api/config-status")
    assert resp.status_code == 401


async def test_config_status_structure(app_client: httpx.AsyncClient) -> None:
    """GET /api/config-status with valid token → 200, correct JSON structure."""
    token = await _admin_login(app_client)

    resp = await app_client.get(
        "/api/config-status", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()

    # Top-level keys.
    assert "overall" in data
    assert isinstance(data["overall"], bool)
    assert "checks" in data
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) >= 3

    # Every check has the required shape.
    for item in data["checks"]:
        assert "check" in item
        assert "ok" in item
        assert isinstance(item["ok"], bool)
        assert "detail" in item
        assert "hint" in item

    # At least the rag_service check must be present.
    check_names = [c["check"] for c in data["checks"]]
    assert "rag_service" in check_names, f"Missing rag_service check: {check_names}"


async def test_chat_invalid_image_url_422(app_client: httpx.AsyncClient) -> None:
    """POST /api/chat with image not starting with data:image/ returns 422."""
    admin_token = await _admin_login(app_client)

    resp = await app_client.post(
        "/api/chat/M333YK47",
        json={
            "message": "hello",
            "image": "https://example.com/photo.jpg",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


async def test_ticket_submit_requires_warning_override(
    app_client: httpx.AsyncClient,
) -> None:
    """POST /api/tickets with warning signal_quality requires override_confirmed."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "P854BT78",
        "session_id": "S-0021",
        "anomaly_type": "F09",
        "conclusion": "Стук в турбокомпрессоре",
        "urgency": "medium",
        "operations": ["Проверить турбокомпрессор"],
        "spare_parts": [],
        "references": [{"manual": "236.01.01 РК", "pdf_page": 50}],
    }

    # Without override_confirmed → 422 mentioning «подтвердите»
    resp = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    assert "подтвердите" in resp.json()["detail"]

    # With override_confirmed true → success (200 per existing convention)
    payload_with_override = {**payload, "override_confirmed": True}
    resp = await app_client.post(
        "/api/tickets",
        json=payload_with_override,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticket_id"] == "TKT-0001"

    # Verify ticket appears in list
    list_resp = await app_client.get(
        "/api/tickets/P854BT78", headers={"Authorization": f"Bearer {mech_token}"}
    )
    assert list_resp.status_code == 200
    tickets = list_resp.json()
    assert len(tickets) == 1

    # Alert created for warning override.
    alerts_resp = await app_client.get(
        "/api/admin/alerts", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    override_alerts = [a for a in alerts if a["kind"] == "warning_override"]
    assert len(override_alerts) >= 1
    assert override_alerts[0]["vehicle_id"] == "P854BT78"


async def test_ticket_submit_blocked_below_floor(app_client: httpx.AsyncClient) -> None:
    """Session with confidence below floor → ticket blocked even with override."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "M739BA198",
        "session_id": "S-0103",
        "anomaly_type": "F02",
        "conclusion": "Низкое давление масла",
        "urgency": "high",
        "operations": ["Проверить давление масла"],
        "spare_parts": [],
        "references": [{"manual": "236.01.01 РК", "pdf_page": 50}],
    }

    # With override_confirmed true but confidence below floor → 422 mentioning «порога»
    payload_with_override = {**payload, "override_confirmed": True}
    resp = await app_client.post(
        "/api/tickets",
        json=payload_with_override,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "порога" in detail


async def test_ticket_submit_blocked_bad_quality(app_client: httpx.AsyncClient) -> None:
    """Session with signal_quality bad → ticket blocked regardless of override."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "P456AT178",
        "session_id": "S-0003",
        "anomaly_type": "F01",
        "conclusion": "Стук клапанов",
        "urgency": "high",
        "operations": ["Отрегулировать клапаны"],
        "spare_parts": [],
        "references": [{"manual": "236.01.01 РК", "pdf_page": 50}],
    }

    # Without override_confirmed → 422 mentioning «повторите запись»
    resp = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "повторите запись" in detail

    # With override_confirmed true → still 422 (bad quality always blocks)
    payload_with_override = {**payload, "override_confirmed": True}
    resp = await app_client.post(
        "/api/tickets",
        json=payload_with_override,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "повторите запись" in detail


async def test_ticket_submit_blocked_check_failed_status(
    app_client: httpx.AsyncClient,
) -> None:
    """Real check_failed session (P456AT178/S-0003) → status gate blocks.

    The deterministic status gate must fire before the quality gates, so
    the detail names the failed recording, not the signal quality.
    """
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "P456AT178",
        "session_id": "S-0003",
        "anomaly_type": "F01",
        "conclusion": "Стук клапанов",
        "urgency": "high",
        "operations": ["Отрегулировать клапаны"],
        "spare_parts": [],
        "references": [{"manual": "236.01.01 РК", "pdf_page": 50}],
        "override_confirmed": True,
    }
    resp = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "check_failed" in detail
    assert "повторите запись" in detail


async def test_ticket_submit_blocked_check_failed_good_quality(
    app_client: httpx.AsyncClient,
) -> None:
    """check_failed + good quality (out-of-mock-contract pair) → still blocked.

    The mock data always pairs check_failed with signal_quality bad, so the
    bad-quality gate would never see this; the status gate is what refuses
    it deterministically.
    """
    from shared.models import SessionCheck

    from mechanic.api import deps as api_deps

    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    hub = api_deps.get_hub()
    original_get_session = hub.fleet.get_session
    synthetic = SessionCheck(
        vehicle_id="P456AT178",
        session_id="S-9001",
        status="check_failed",
        signal_quality="good",
        confidence=0.9,
        description="синтетическая сессия: сбой записи с хорошим качеством",
        model_version="mock-test",
    )

    def _fake_get_session(vehicle_id: str, session_id: str) -> SessionCheck:
        if vehicle_id == "P456AT178" and session_id == "S-9001":
            return synthetic
        return original_get_session(vehicle_id, session_id)

    hub.fleet.get_session = _fake_get_session  # type: ignore[method-assign]
    try:
        payload = {
            "vehicle_id": "P456AT178",
            "session_id": "S-9001",
            "anomaly_type": "F01",
            "conclusion": "Стук клапанов",
            "urgency": "high",
            "operations": ["Отрегулировать клапаны"],
            "spare_parts": [],
            "references": [{"manual": "236.01.01 РК", "pdf_page": 50}],
            "override_confirmed": True,
        }
        resp = await app_client.post(
            "/api/tickets",
            json=payload,
            headers={"Authorization": f"Bearer {mech_token}"},
        )
        assert resp.status_code == 422, resp.text
        assert "check_failed" in resp.json()["detail"]
    finally:
        hub.fleet.get_session = original_get_session  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Fake LLM client that yields one tool call then final text.
# ---------------------------------------------------------------------------


class FakeToolLLMClient:
    """Fake LLM that yields a tool call followed by a final response."""

    async def stream_chat(
        self, request: ChatRequest
    ) -> AsyncIterator[TextDelta | ToolCallsReady | TurnComplete]:
        yield ToolCallsReady(
            tool_calls=[
                ToolCall(
                    call_id="call_1",
                    name="get_diagnostic_result",
                    arguments_json=json.dumps({"vehicle_id": "M333YK47"}),
                )
            ],
        )
        yield TextDelta("диагноз получен")
        yield TurnComplete(
            stop_reason=StopReason.END_TURN,
            input_tokens=10,
            output_tokens=5,
        )

    async def fetch_models(self, base_url: str, api_key: str) -> list:
        return []


async def test_admin_usage_detail_contains_agent_steps(
    app_client: httpx.AsyncClient,
) -> None:
    """POST /api/chat → tool call → GET detail → steps present."""
    admin_token = await _admin_login(app_client)

    # Create mech2 user.
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech2", "password": "mech-pass-2", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech2_token = await _login(app_client, "mech2", "mech-pass-2")

    # Patch the chat module's client factory with our tool-calling fake.
    import mechanic.api.chat_api as chat_api_module

    original_get_llm = chat_api_module.get_llm_client
    chat_api_module.get_llm_client = (  # type: ignore[assignment]
        lambda protocol, transport=None: FakeToolLLMClient()
    )

    try:
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "проверь диагностику"},
            headers={"Authorization": f"Bearer {mech2_token}"},
        )
        assert resp.status_code == 200

        # Find the chat usage record.
        from mechanic.api.deps import get_hub

        hub = get_hub()
        recent = hub.usage.recent(200)
        chat_records = [r for r in recent if r.kind == "chat"]
        assert chat_records, f"No chat records: {[r.kind for r in recent]}"

        # Get the newest chat record (last in list).
        latest = chat_records[-1]
        detail_resp = await app_client.get(
            f"/api/admin/usage/{latest.id}/detail",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()

        # Assert steps are present and contain the tool call.
        assert "steps" in detail
        steps = detail["steps"]
        assert isinstance(steps, list)
        assert len(steps) >= 1
        assert steps[0]["tool"] == "get_diagnostic_result"
        assert steps[0]["ok"] is True
        assert "arguments" in steps[0]
        args = steps[0]["arguments"]
        assert isinstance(args, dict)
        assert "vehicle_id" in args
    finally:
        chat_api_module.get_llm_client = original_get_llm


async def test_admin_economics_endpoint(app_client: httpx.AsyncClient) -> None:
    """GET /api/admin/economics returns scenario + fleet calculation."""
    token = await _admin_login(app_client)

    # Seed usage rows so medians are deterministic.
    from mechanic.api.deps import get_hub

    hub = get_hub()
    hub.usage.record(username="x", kind="chat", input_tokens=10000, output_tokens=1000)
    hub.usage.record(username="x", kind="chat", input_tokens=10000, output_tokens=1000)
    hub.usage.record(username="x", kind="chat", input_tokens=12000, output_tokens=800)

    # GET /api/admin/economics with default params
    resp = await app_client.get(
        "/api/admin/economics?machines=50&period_days=14&questions=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    data = resp.json()

    # scenario.turns == diagnosis(1) + questions(3) = 4
    assert data["scenario"]["turns"] == 4

    # usage_stats medians: inputs [10000,10000,12000] → median=10000
    #                        outputs [1000,1000,800]   → median=1000
    assert data["usage_stats"]["median_input"] == 10000
    assert data["usage_stats"]["median_output"] == 1000

    # scenario cost: per_turn = (10000*0.22 + 1000*0.88)/1e6 = 0.00308
    #   factor = 82.313 (USD), turns=4
    #   cost = 0.00308 * 4 * 82.313 ≈ 1.0141
    expected_cost = 4 * (10000 * 0.22 + 1000 * 0.88) / 1_000_000 * 82.313
    assert data["scenario"]["cost_rub"] == pytest.approx(expected_cost, rel=0.01)

    # fleet cost_year_rub ≈ scenario_cost * (30/14*50) * 12
    expected_year = expected_cost * (30 / 14 * 50) * 12
    assert data["fleet"]["cost_year_rub"] == pytest.approx(expected_year, rel=0.01)

    # Assumptions are capped correctly
    assert data["assumptions"]["machines"] == 50
    assert data["assumptions"]["period_days"] == 14
    assert data["assumptions"]["questions"] == 3


async def test_ticket_submit_f08_fuel_mismatch_rejected(
    app_client: httpx.AsyncClient,
) -> None:
    """F08 (дизельная топливоподача) on petrol vehicle → 422; alert created."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "M739BA198",
        "session_id": "S-0102",
        "anomaly_type": "F08",
        "conclusion": "Жёсткая работа с резким стуком",
        "urgency": "high",
        "operations": ["Проверить топливную систему"],
        "spare_parts": [],
        "references": [{"manual": "ЗМЗ-5234.10 РК", "pdf_page": 50}],
    }

    resp = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "топлива" in detail or "карточке" in detail

    # Alert with kind fuel_mismatch exists for this vehicle.
    alerts_resp = await app_client.get(
        "/api/admin/alerts", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    fuel_alerts = [a for a in alerts if a["kind"] == "fuel_mismatch"]
    assert len(fuel_alerts) >= 1
    assert any(a["vehicle_id"] == "M739BA198" for a in fuel_alerts)


async def test_ticket_submit_hallucinated_manual_rejected(
    app_client: httpx.AsyncClient,
) -> None:
    """Reference to non-existent manual → 422; no ticket created."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "M333YK47",
        "session_id": "S-0005",
        "anomaly_type": "F02",
        "conclusion": "Стук в механизме газораспределения",
        "urgency": "high",
        "operations": ["Проверить ГРМ"],
        "spare_parts": [],
        "references": [{"manual": "Несуществующее руководство", "pdf_page": 10}],
    }

    resp = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "несуществующее руководство" in detail

    # No ticket was created — response must not contain ticket_id.
    data = resp.json()
    assert "ticket_id" not in data


async def test_ticket_submit_page_out_of_range_rejected(
    app_client: httpx.AsyncClient,
) -> None:
    """Page beyond manual page count → 422."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    payload = {
        "vehicle_id": "M333YK47",
        "session_id": "S-0005",
        "anomaly_type": "F02",
        "conclusion": "Стук в механизме газораспределения",
        "urgency": "high",
        "operations": ["Проверить ГРМ"],
        "spare_parts": [],
        "references": [{"manual": "236.01.01 РК", "pdf_page": 999}],
    }

    resp = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "страницу" in detail or "диапазон" in detail


async def test_ticket_submit_wrong_engine_manual_rejected(
    app_client: httpx.AsyncClient,
) -> None:
    """Reference to manual for different engine → 422."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    # M333YK47 has engine ЯМЗ-236М2; ЗМЗ-5234.10 РК is for ЗМЗ-5234.10.
    payload = {
        "vehicle_id": "M333YK47",
        "session_id": "S-0005",
        "anomaly_type": "F02",
        "conclusion": "Стук в механизме газораспределения",
        "urgency": "high",
        "operations": ["Проверить ГРМ"],
        "spare_parts": [],
        "references": [{"manual": "ЗМЗ-5234.10 РК", "pdf_page": 50}],
    }

    resp = await app_client.post(
        "/api/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {mech_token}"},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "двигателю" in detail


async def test_login_rate_limited_after_failures(
    app_client: httpx.AsyncClient,
) -> None:
    """POST /api/auth/login returns 429 after 5 failed attempts for a username."""
    admin_token = await _admin_login(app_client)

    # Create a regular user with a known password.
    await app_client.post(
        "/api/admin/users",
        json={"username": "bruteforce", "password": "brute-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # 5 failed login attempts with wrong password.
    for _ in range(5):
        resp = await app_client.post(
            "/api/auth/login",
            json={"username": "bruteforce", "password": "wrong"},
        )
        assert resp.status_code == 401

    # 6th attempt with the CORRECT password is still throttled → 429.
    resp = await app_client.post(
        "/api/auth/login",
        json={"username": "bruteforce", "password": "brute-pass-1"},
    )
    assert resp.status_code == 429
    assert "подождите" in resp.json()["detail"]

    # A login attempt for a DIFFERENT username (admin) still succeeds.
    admin_resp = await app_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-pass-1"},
    )
    assert admin_resp.status_code == 200
