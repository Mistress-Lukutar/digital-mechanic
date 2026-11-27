'''
File:   test_chat_conversations.py
Brief:  Integration tests for conversation persistence and resume on the
        ``/api/chat`` SSE endpoint.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0

Tests that chat conversations are persisted to ChatStore, resumed via
conversation_id, and that the in-memory ConversationStore is hydrated
from SQLite on resume.
'''

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from mechanic.llm.types import ChatRequest, StopReason, TextDelta, TurnComplete

# ---------------------------------------------------------------------------
# Paths and constants.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fake LLM client that records the LAST received request.turns.
# ---------------------------------------------------------------------------


class FakeLLMClient:
    """Minimal fake that yields token + turn_done events and records turns."""

    last_turns: list[Any] | None = None  # module-level for test inspection

    async def stream_chat(
        self, request: ChatRequest
    ) -> AsyncIterator[TextDelta | TurnComplete]:
        """Yield a text delta followed by turn_complete with usage."""
        FakeLLMClient.last_turns = list(request.turns)
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
    """Build the app with an isolated hub."""
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

    hub.rag = RagClient(
        base_url="http://127.0.0.1:1",
        mock_chunks_path=None,
        manuals_dir=settings.manuals_dir,
    )

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

    for service in (hub.auth, hub.ticket_log, hub.usage):
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
    hub.auth.change_password_admin("admin", "admin-pass-1")
    return await _login(client, "admin", "admin-pass-1")


# ---------------------------------------------------------------------------
# Helper: seed conversations via the ChatStore.
# ---------------------------------------------------------------------------


def _seed_conversation(hub, username: str, vehicle_id: str) -> dict:
    """Create a conversation and add one user + one assistant message."""
    conv = hub.chats.create_conversation(username, vehicle_id)
    cid = conv["id"]
    hub.chats.add_message(cid, "user", "Hello mechanic")
    hub.chats.add_message(cid, "assistant", "Hi! How can I help?")
    return conv


# ---------------------------------------------------------------------------
# SSE frame parsing (minimal subset of test_api.py pattern).
# ---------------------------------------------------------------------------


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
            try:
                current_event["_parsed_data"] = json.loads(current_event["data"])
            except (json.JSONDecodeError, ValueError):
                pass
            events.append(current_event)
            current_event = None
    return events


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


async def test_create_conversation_sse_and_persistence(
    app_client: httpx.AsyncClient,
) -> None:
    """POST /api/chat without conversation_id creates one; messages stored."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    import mechanic.api.chat_api as chat_api

    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: FakeLLMClient()  # type: ignore[assignment]

    try:
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "привет"},
            headers={"Authorization": f"Bearer {mech_token}"},
        )
        assert resp.status_code == 200

        events = _parse_sse_events(resp.text)

        # First event must be 'conversation' with a non-empty conversation_id.
        conv_event = next(e for e in events if e["event"] == "conversation")
        assert "_parsed_data" in conv_event
        cid = conv_event["_parsed_data"]["conversation_id"]
        assert cid  # non-empty

        # After stream ends, hub.chats has user + assistant rows.
        from mechanic.api.deps import get_hub

        hub = get_hub()
        messages = hub.chats.get_messages(cid)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["text"] == "привет"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["text"] == "ответ"
    finally:
        chat_api.get_llm_client = original_get_llm


async def test_resumed_conversation_grows_to_four(
    app_client: httpx.AsyncClient,
) -> None:
    """Second POST with conversation_id grows to 4 message rows."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    import mechanic.api.chat_api as chat_api

    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: FakeLLMClient()  # type: ignore[assignment]

    try:
        # First POST — creates conversation.
        resp1 = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "first"},
            headers={"Authorization": f"Bearer {mech_token}"},
        )
        assert resp1.status_code == 200
        events1 = _parse_sse_events(resp1.text)
        cid = next(
            e["_parsed_data"]["conversation_id"]
            for e in events1
            if e["event"] == "conversation"
        )

        # Second POST — resume with conversation_id.
        resp2 = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "second", "conversation_id": cid},
            headers={"Authorization": f"Bearer {mech_token}"},
        )
        assert resp2.status_code == 200

        from mechanic.api.deps import get_hub

        hub = get_hub()
        messages = hub.chats.get_messages(cid)
        assert len(messages) == 4
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "user", "assistant"]
    finally:
        chat_api.get_llm_client = original_get_llm


async def test_hydration_from_sqlite(app_client: httpx.AsyncClient) -> None:
    """Seed conversation via hub.chats, POST with id; fake LLM sees turns."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    import mechanic.api.chat_api as chat_api
    from mechanic.api.deps import get_hub

    hub = get_hub()

    # Seed a conversation via the ChatStore.
    conv = _seed_conversation(hub, "mech", "M333YK47")
    cid = conv["id"]

    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: FakeLLMClient()  # type: ignore[assignment]

    try:
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "new message", "conversation_id": cid},
            headers={"Authorization": f"Bearer {mech_token}"},
        )
        assert resp.status_code == 200

        # Verify the fake LLM received turns including seeded user + assistant.
        turns = FakeLLMClient.last_turns
        assert turns is not None
        turn_roles = [t.role for t in turns]
        assert "user" in turn_roles
        assert "assistant" in turn_roles

        # The user message should include the seeded text.
        user_texts = [t.parts[0].text for t in turns if t.role == "user"]
        assert "Hello mechanic" in user_texts

        assistant_texts = []
        for t in turns:
            if t.role == "assistant":
                for p in t.parts:
                    if hasattr(p, "text"):
                        assistant_texts.append(p.text)
        assert "Hi! How can I help?" in assistant_texts
    finally:
        chat_api.get_llm_client = original_get_llm


async def test_conversation_id_validation(app_client: httpx.AsyncClient) -> None:
    """Wrong user, unknown id, or wrong vehicle → 404."""
    admin_token = await _admin_login(app_client)

    # Create two users with same password for simplicity.
    await app_client.post(
        "/api/admin/users",
        json={"username": "alice", "password": "user-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await app_client.post(
        "/api/admin/users",
        json={"username": "bob", "password": "user-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    alice_token = await _login(app_client, "alice", "user-pass-1")
    bob_token = await _login(app_client, "bob", "user-pass-1")

    import mechanic.api.chat_api as chat_api
    from mechanic.api.deps import get_hub

    hub = get_hub()

    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: FakeLLMClient()  # type: ignore[assignment]

    try:
        # Alice creates a conversation on M333YK47.
        conv_alice = _seed_conversation(hub, "alice", "M333YK47")
        cid_alice = conv_alice["id"]

        # 1) Unknown id → 404.
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "hi", "conversation_id": "nonexistent-uuid"},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "чат не найден"

        # 2) Conversation belongs to another user → 404.
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "hi", "conversation_id": cid_alice},
            headers={"Authorization": f"Bearer {bob_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "чат не найден"

        # 3) Conversation of the right user but different vehicle → 404.
        conv_other = _seed_conversation(hub, "alice", "OTHER-VEHICLE")
        cid_other = conv_other["id"]
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "hi", "conversation_id": cid_other},
            headers={"Authorization": f"Bearer {alice_token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "чат не найден"
    finally:
        chat_api.get_llm_client = original_get_llm


async def test_conversation_event_on_resume(app_client: httpx.AsyncClient) -> None:
    """The 'conversation' SSE event is emitted on resumed request too."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "mech", "password": "mech-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    mech_token = await _login(app_client, "mech", "mech-pass-1")

    import mechanic.api.chat_api as chat_api
    from mechanic.api.deps import get_hub

    hub = get_hub()

    # Seed a conversation.
    conv = _seed_conversation(hub, "mech", "M333YK47")
    cid = conv["id"]

    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: FakeLLMClient()  # type: ignore[assignment]

    try:
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "resumed msg", "conversation_id": cid},
            headers={"Authorization": f"Bearer {mech_token}"},
        )
        assert resp.status_code == 200

        events = _parse_sse_events(resp.text)
        conv_event = next(e for e in events if e["event"] == "conversation")
        assert "_parsed_data" in conv_event
        assert conv_event["_parsed_data"]["conversation_id"] == cid
    finally:
        chat_api.get_llm_client = original_get_llm
