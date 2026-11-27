'''
File:   test_chats_api.py
Brief:  Integration tests for the /api/chats endpoints.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0

Tests list, get, and delete chat conversations through the FastAPI app
using ``httpx.AsyncClient`` with ``ASGITransport``. The hub is isolated
with a tmp_path database; users are created and seeded via the ChatStore.
'''

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

# ---------------------------------------------------------------------------
# Paths and constants.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture: isolated app with overridden hub (mirrors test_api.py).
# ---------------------------------------------------------------------------


@pytest.fixture()
async def app_client(tmp_path: Path) -> httpx.AsyncClient:
    """Build the app with an isolated hub.

    The DB lives in *tmp_path*, fleet data is read from the committed repo
    data dir, and the lifespan is bypassed so singletons are initialised
    directly.
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
        body = request.json if request.content else {}  # type: ignore[union-attr]
        vid = body.get("vehicle_id", "") if isinstance(body, dict) else ""
        if vid == "M333YK47":
            return httpx.Response(
                200,
                json={
                    "vehicle_id": "M333YK47",
                    "session_id": "S-0005",
                    "status": "anomaly",
                    "anomaly_type": "F08",
                    "anomaly_title": "Test",
                    "anomaly_score": 0.76,
                    "confidence": 0.73,
                    "signal_quality": "good",
                    "description": "Test",
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

    for service in (hub.auth, hub.chats, hub.ticket_log, hub.usage):
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


async def _admin_login(client: httpx.AsyncClient) -> str:
    """Login as bootstrap admin after setting its password."""
    from mechanic.api.deps import get_hub

    hub = get_hub()
    hub.auth.change_password_admin("admin", "admin-pass-1")
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin-pass-1"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


async def _login(client: httpx.AsyncClient, username: str, password: str) -> str:
    """Login and return the auth token."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# Helper: seed conversations via the ChatStore.
# ---------------------------------------------------------------------------


def _seed_conversation(hub, username: str, vehicle_id: str, title: str = "") -> dict:
    """Create a conversation and add one user + one assistant message."""
    conv = hub.chats.create_conversation(username, vehicle_id, title)
    cid = conv["id"]
    hub.chats.add_message(cid, "user", "Hello mechanic")
    hub.chats.add_message(cid, "assistant", "Hi! How can I help?")
    return conv


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


async def test_chats_requires_auth(app_client: httpx.AsyncClient) -> None:
    """GET /api/chats without token returns 401."""
    resp = await app_client.get("/api/chats", params={"vehicle_id": "V001"})
    assert resp.status_code == 401


async def test_chats_list_ownership_and_order(app_client: httpx.AsyncClient) -> None:
    """List returns only current user's conversations, newest-updated first."""
    admin_token = await _admin_login(app_client)

    from mechanic.api.deps import get_hub

    hub = get_hub()

    vehicle_id = "V-CHATS-LIST"
    user1 = "chats-user-alpha"
    user2 = "chats-user-beta"

    # Create users
    await app_client.post(
        "/api/admin/users",
        json={"username": user1, "password": "pass1-pass1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await app_client.post(
        "/api/admin/users",
        json={"username": user2, "password": "pass2-pass2", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    token1 = await _login(app_client, user1, "pass1-pass1")
    token2 = await _login(app_client, user2, "pass2-pass2")

    # User1: own conversations on this vehicle and another vehicle
    conv1 = _seed_conversation(hub, user1, vehicle_id, "conv-1a")
    import time

    time.sleep(0.05)
    conv1b = _seed_conversation(hub, user1, vehicle_id, "conv-1b")

    # User2: conversation on same vehicle
    conv2 = _seed_conversation(hub, user2, vehicle_id, "conv-2a")

    # User1: conversation on a different vehicle (should not appear)
    _seed_conversation(hub, user1, "V-OTHER", "conv-other")

    # List for user1 — should see conv-1b then conv-1a (newest first by updated_at)
    resp = await app_client.get(
        "/api/chats",
        params={"vehicle_id": vehicle_id},
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    # newest-updated first: conv-1b was updated after conv-1a
    assert items[0]["id"] == conv1b["id"]
    assert items[1]["id"] == conv1["id"]
    # user2's conversation absent
    ids = {i["id"] for i in items}
    assert conv2["id"] not in ids

    # List for user2 — should see only conv-2a
    resp = await app_client.get(
        "/api/chats",
        params={"vehicle_id": vehicle_id},
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 200
    items2 = resp.json()
    assert len(items2) == 1
    assert items2[0]["id"] == conv2["id"]


async def test_chats_get_by_id(app_client: httpx.AsyncClient) -> None:
    """GET by id returns conversation + messages; unknown/other-user → 404."""
    admin_token = await _admin_login(app_client)

    from mechanic.api.deps import get_hub

    hub = get_hub()

    vehicle_id = "V-CHATS-GET"
    user1 = "chats-get-owner"
    user2 = "chats-get-friend"

    # Create users
    await app_client.post(
        "/api/admin/users",
        json={"username": user1, "password": "pass1-pass1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await app_client.post(
        "/api/admin/users",
        json={"username": user2, "password": "pass2-pass2", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    token1 = await _login(app_client, user1, "pass1-pass1")
    await _login(app_client, user2, "pass2-pass2")

    conv1 = _seed_conversation(hub, user1, vehicle_id, "my-chat")
    conv2 = _seed_conversation(hub, user2, vehicle_id, "friend-chat")

    # GET by owner — 200 with conversation and messages
    resp = await app_client.get(
        f"/api/chats/{conv1['id']}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "conversation" in data
    assert "messages" in data
    assert data["conversation"]["id"] == conv1["id"]
    assert data["conversation"]["message_count"] == 2
    messages = data["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"

    # GET unknown id — 404
    resp = await app_client.get(
        "/api/chats/0000000000000000000000000000",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 404

    # GET another user's id — 404 (same detail, never leaks existence)
    resp = await app_client.get(
        f"/api/chats/{conv2['id']}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 404


async def test_chats_delete(app_client: httpx.AsyncClient) -> None:
    """Delete returns 200; subsequent GET → 404; other-user survives."""
    admin_token = await _admin_login(app_client)

    from mechanic.agent.conversations import ConversationStore
    from mechanic.api.deps import get_conversations, get_hub

    hub = get_hub()

    vehicle_id = "V-CHATS-DEL"
    user1 = "chats-del-owner"
    user2 = "chats-del-other"

    # Create users
    await app_client.post(
        "/api/admin/users",
        json={"username": user1, "password": "pass1-pass1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await app_client.post(
        "/api/admin/users",
        json={"username": user2, "password": "pass2-pass2", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    token1 = await _login(app_client, user1, "pass1-pass1")
    await _login(app_client, user2, "pass2-pass2")

    conv1 = _seed_conversation(hub, user1, vehicle_id, "to-delete")
    conv2 = _seed_conversation(hub, user2, vehicle_id, "survives")

    # Verify forget() was called: seed turns BEFORE any delete, then delete
    store: ConversationStore = get_conversations()
    store.add_user_message(conv1["id"], "x")
    assert len(store.history(conv1["id"])) == 1

    # Delete by owner — 200 (forget() will be called)
    resp = await app_client.delete(
        f"/api/chats/{conv1['id']}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}

    # forget() was called — check turns are empty
    assert store.history(conv1["id"]) == []

    # Verify forget() on a non-existent conversation still works (no raise)
    store.forget("nonexistent-id-0000")

    # Subsequent GET → 404
    resp = await app_client.get(
        f"/api/chats/{conv1['id']}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 404

    # Delete another user's — 404, row survives in store
    resp = await app_client.delete(
        f"/api/chats/{conv2['id']}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 404
    # Verify the row still exists in the store
    row = hub.chats.get_conversation(conv2["id"])
    assert row is not None
    assert row["id"] == conv2["id"]


async def test_chats_delete_other_user_no_evict(app_client: httpx.AsyncClient) -> None:
    """Deleting another user's conversation does NOT evict their turns."""
    admin_token = await _admin_login(app_client)

    from mechanic.agent.conversations import ConversationStore
    from mechanic.api.deps import get_conversations, get_hub

    hub = get_hub()
    store: ConversationStore = get_conversations()

    vehicle_id = "V-CHATS-DEL2"
    user1 = "chats-del2-owner"
    user2 = "chats-del2-other"

    await app_client.post(
        "/api/admin/users",
        json={"username": user1, "password": "pass1-pass1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await app_client.post(
        "/api/admin/users",
        json={"username": user2, "password": "pass2-pass2", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    token1 = await _login(app_client, user1, "pass1-pass1")
    await _login(app_client, user2, "pass2-pass2")

    conv2 = _seed_conversation(hub, user2, vehicle_id, "other-conv")

    # Seed turns for the other user's conversation
    store.add_user_message(conv2["id"], "hello from other")
    assert len(store.history(conv2["id"])) == 1

    # Delete by owner (user1) — should not evict user2's turns
    resp = await app_client.delete(
        f"/api/chats/{conv2['id']}",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert resp.status_code == 404

    # Turns for conv2 should still exist (forget was NOT called)
    assert len(store.history(conv2["id"])) == 1


async def test_chats_missing_vehicle_id_422(app_client: httpx.AsyncClient) -> None:
    """GET /api/chats without vehicle_id → 422."""
    admin_token = await _admin_login(app_client)

    resp = await app_client.get(
        "/api/chats",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Helpers shared from test_chat_conversations.py pattern.
# ---------------------------------------------------------------------------


class _FakeLLMClient:
    """Minimal fake that yields token + turn_done events and records turns."""

    last_turns: list | None = None  # module-level for test inspection

    async def stream_chat(self, request):  # noqa: D401
        """Yield a text delta followed by turn_complete with usage."""
        from mechanic.llm.types import ChatRequest, StopReason, TextDelta, TurnComplete

        _FakeLLMClient.last_turns = list(request.turns)
        yield TextDelta("ответ")
        yield TurnComplete(
            stop_reason=StopReason.END_TURN,
            input_tokens=10,
            output_tokens=5,
        )

    async def fetch_models(self, base_url: str, api_key: str) -> list:
        return []


def _parse_sse_events(text: str) -> list[dict]:
    """Parse SSE-formatted text into event dicts."""
    import json

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
# Tests — Message-edit (branching) API.
# ---------------------------------------------------------------------------


async def test_edit_flow_happy_path(app_client: httpx.AsyncClient) -> None:
    """Edit a user message via SSE → new sibling created, old branch preserved."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "editer", "password": "edit-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    editer_token = await _login(app_client, "editer", "edit-pass-1")

    import mechanic.api.chat_api as chat_api

    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: _FakeLLMClient()  # type: ignore[assignment]

    try:
        # 1. First POST — creates conversation with initial message.
        resp1 = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "original question"},
            headers={"Authorization": f"Bearer {editer_token}"},
        )
        assert resp1.status_code == 200

        events1 = _parse_sse_events(resp1.text)
        conv_event = next(e for e in events1 if e["event"] == "conversation")
        cid = conv_event["_parsed_data"]["conversation_id"]

        # 2. Fetch messages to find the user message id.
        from mechanic.api.deps import get_hub

        hub = get_hub()
        msg_resp = await app_client.get(
            f"/api/chats/{cid}",
            headers={"Authorization": f"Bearer {editer_token}"},
        )
        assert msg_resp.status_code == 200
        msg_data = msg_resp.json()
        messages = msg_data["messages"]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        original_user_id = user_msg["id"]

        # Verify initial state: sibling_count == 1, sibling_index == 1.
        assert user_msg["sibling_count"] == 1
        assert user_msg["sibling_index"] == 1

        # 3. Edit the user message via SSE (new text).
        resp2 = await app_client.post(
            "/api/chat/M333YK47",
            json={
                "message": "edited question text",
                "conversation_id": cid,
                "edit_message_id": original_user_id,
            },
            headers={"Authorization": f"Bearer {editer_token}"},
        )
        assert resp2.status_code == 200

        # Consume SSE to completion.
        events2 = _parse_sse_events(resp2.text)
        conv_event2 = next(e for e in events2 if e["event"] == "conversation")
        assert conv_event2["_parsed_data"]["conversation_id"] == cid

        # 4. After edit: active path should show NEW user text.
        msg_resp2 = await app_client.get(
            f"/api/chats/{cid}",
            headers={"Authorization": f"Bearer {editer_token}"},
        )
        assert msg_resp2.status_code == 200
        updated_data = msg_resp2.json()
        updated_messages = updated_data["messages"]

        # Find the user message on active path — should be the new one.
        edited_user_msgs = [m for m in updated_messages if m["role"] == "user"]
        assert len(edited_user_msgs) == 1
        assert edited_user_msgs[0]["text"] == "edited question text"

        # The edited user entry should have sibling_count == 2.
        assert edited_user_msgs[0]["sibling_count"] == 2
        # It is the second sibling (newer).
        assert edited_user_msgs[0]["sibling_index"] == 2

        # The assistant answer follows the edited user message.
        roles = [m["role"] for m in updated_messages]
        assert roles[-1] == "assistant"

        # 5. Old branch rows still exist: switch to old and verify.
        from mechanic.llm.types import ChatRequest, StopReason, TextDelta, TurnComplete

        class _OldBranchLLM:
            async def stream_chat(self, request):
                _FakeLLMClient.last_turns = list(request.turns)
                yield TextDelta("old branch answer")
                yield TurnComplete(
                    stop_reason=StopReason.END_TURN,
                    input_tokens=5,
                    output_tokens=3,
                )

            async def fetch_models(self, base_url: str, api_key: str) -> list:
                return []

        original_get_llm2 = chat_api.get_llm_client
        chat_api.get_llm_client = lambda protocol, transport=None: _OldBranchLLM()  # type: ignore[assignment]
        try:
            resp_switch = await app_client.post(
                f"/api/chats/{cid}/branch",
                json={"message_id": original_user_id},
                headers={"Authorization": f"Bearer {editer_token}"},
            )
            assert resp_switch.status_code == 200
            switch_data = resp_switch.json()
            old_messages = switch_data["messages"]
            old_user = [m for m in old_messages if m["role"] == "user"][0]
            assert old_user["text"] == "original question"
            # Old sibling has index 1.
            assert old_user["sibling_index"] == 1
        finally:
            chat_api.get_llm_client = original_get_llm2

    finally:
        chat_api.get_llm_client = original_get_llm


async def test_branch_switch_round_trip(app_client: httpx.AsyncClient) -> None:
    """Switch between sibling branches via POST /branch and verify content."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "brtr-user", "password": "brtr-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    brtr_token = await _login(app_client, "brtr-user", "brtr-pass-1")

    import mechanic.api.chat_api as chat_api

    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: _FakeLLMClient()  # type: ignore[assignment]

    try:
        # Create a conversation with an initial user message.
        resp1 = await app_client.post(
            "/api/chat/M333YK47",
            json={"message": "first question"},
            headers={"Authorization": f"Bearer {brtr_token}"},
        )
        assert resp1.status_code == 200

        events1 = _parse_sse_events(resp1.text)
        cid = next(
            e["_parsed_data"]["conversation_id"]
            for e in events1
            if e["event"] == "conversation"
        )

        from mechanic.api.deps import get_hub
        hub = get_hub()
        msg_resp = await app_client.get(
            f"/api/chats/{cid}",
            headers={"Authorization": f"Bearer {brtr_token}"},
        )
        user_msg_id = [m["id"] for m in msg_resp.json()["messages"] if m["role"] == "user"][0]

        # Edit to create a sibling.
        resp_edit = await app_client.post(
            "/api/chat/M333YK47",
            json={
                "message": "edited question",
                "conversation_id": cid,
                "edit_message_id": user_msg_id,
            },
            headers={"Authorization": f"Bearer {brtr_token}"},
        )
        assert resp_edit.status_code == 200

        # Capture the new user message id immediately after edit.
        from mechanic.api.deps import get_hub as get_hub2
        hub2 = get_hub2()
        all_msg_resp = await app_client.get(
            f"/api/chats/{cid}",
            headers={"Authorization": f"Bearer {brtr_token}"},
        )
        new_user_msg_id = [m["id"] for m in all_msg_resp.json()["messages"] if m["text"] == "edited question"][0]

        # --- Switch to OLD branch (original message) ---
        from mechanic.llm.types import ChatRequest, StopReason, TextDelta, TurnComplete

        class _OldLLM:
            async def stream_chat(self, request):
                yield TextDelta("old answer")
                yield TurnComplete(
                    stop_reason=StopReason.END_TURN,
                    input_tokens=5,
                    output_tokens=3,
                )

            async def fetch_models(self, base_url: str, api_key: str) -> list:
                return []

        chat_api.get_llm_client = lambda protocol, transport=None: _OldLLM()  # type: ignore[assignment]
        try:
            resp_old = await app_client.post(
                f"/api/chats/{cid}/branch",
                json={"message_id": user_msg_id},
                headers={"Authorization": f"Bearer {brtr_token}"},
            )
            assert resp_old.status_code == 200
            old_data = resp_old.json()
            old_messages = old_data["messages"]
            old_user = [m for m in old_messages if m["role"] == "user"][0]
            assert old_user["text"] == "first question"
            assert old_user["sibling_index"] == 1

            # --- Switch to NEW branch (edited message) ---
            resp_new = await app_client.post(
                f"/api/chats/{cid}/branch",
                json={"message_id": new_user_msg_id},
                headers={"Authorization": f"Bearer {brtr_token}"},
            )
            assert resp_new.status_code == 200
            new_data = resp_new.json()
            new_messages = new_data["messages"]
            new_user = [m for m in new_messages if m["role"] == "user"][0]
            assert new_user["text"] == "edited question"
            assert new_user["sibling_index"] == 2
        finally:
            chat_api.get_llm_client = original_get_llm

    finally:
        chat_api.get_llm_client = original_get_llm


async def test_edit_no_conversation_id_400(app_client: httpx.AsyncClient) -> None:
    """edit_message_id without conversation_id → 400."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "valuser", "password": "val-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    val_token = await _login(app_client, "valuser", "val-pass-1")

    resp = await app_client.post(
        "/api/chat/M333YK47",
        json={
            "message": "hi",
            "edit_message_id": 42,
        },
        headers={"Authorization": f"Bearer {val_token}"},
    )
    assert resp.status_code == 400


async def test_edit_nonexistent_message_404(app_client: httpx.AsyncClient) -> None:
    """edit_message_id pointing to a nonexistent message → 404."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "valuser2", "password": "valpass-2", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    val_token = await _login(app_client, "valuser2", "valpass-2")

    from mechanic.api.deps import get_hub
    import mechanic.api.chat_api as chat_api

    hub = get_hub()
    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: _FakeLLMClient()  # type: ignore[assignment]

    try:
        # Seed a conversation so that conversation_id exists.
        conv = hub.chats.create_conversation("valuser2", "M333YK47")
        cid = conv["id"]
        hub.chats.add_message(cid, "user", "hello")
        hub.chats.add_message(cid, "assistant", "hi")

        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={
                "message": "hi",
                "conversation_id": cid,
                "edit_message_id": 999999,
            },
            headers={"Authorization": f"Bearer {val_token}"},
        )
        assert resp.status_code == 404
    finally:
        chat_api.get_llm_client = original_get_llm


async def test_edit_assistant_message_400(app_client: httpx.AsyncClient) -> None:
    """edit_message_id pointing to an assistant message → 400."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "valuser3", "password": "val-pass-3", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    val_token = await _login(app_client, "valuser3", "val-pass-3")

    from mechanic.api.deps import get_hub
    import mechanic.api.chat_api as chat_api

    hub = get_hub()
    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: _FakeLLMClient()  # type: ignore[assignment]

    try:
        # Seed a conversation with user + assistant messages.
        conv = hub.chats.create_conversation("valuser3", "M333YK47")
        cid = conv["id"]
        hub.chats.add_message(cid, "user", "hello")
        hub.chats.add_message(cid, "assistant", "hi there")

        # Get the assistant message id.
        all_msgs = hub.chats.get_messages(cid)
        assistant_msg_id = [m["id"] for m in all_msgs if m["role"] == "assistant"][0]

        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={
                "message": "new text",
                "conversation_id": cid,
                "edit_message_id": assistant_msg_id,
            },
            headers={"Authorization": f"Bearer {val_token}"},
        )
        assert resp.status_code == 400
    finally:
        chat_api.get_llm_client = original_get_llm


async def test_edit_foreign_user_404(app_client: httpx.AsyncClient) -> None:
    """edit_message_id on another user's conversation → 404."""
    admin_token = await _admin_login(app_client)

    await app_client.post(
        "/api/admin/users",
        json={"username": "foreign-owner", "password": "fo-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await app_client.post(
        "/api/admin/users",
        json={"username": "foreign-editer", "password": "fe-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    owner_token = await _login(app_client, "foreign-owner", "fo-pass-1")
    editer_token = await _login(app_client, "foreign-editer", "fe-pass-1")

    from mechanic.api.deps import get_hub
    import mechanic.api.chat_api as chat_api

    hub = get_hub()
    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: _FakeLLMClient()  # type: ignore[assignment]

    try:
        # Owner creates a conversation.
        conv = hub.chats.create_conversation("foreign-owner", "M333YK47")
        cid = conv["id"]
        hub.chats.add_message(cid, "user", "owner's message")
        hub.chats.add_message(cid, "assistant", "owner's reply")

        all_msgs = hub.chats.get_messages(cid)
        owner_user_msg_id = [m["id"] for m in all_msgs if m["role"] == "user"][0]

        # Editer tries to edit owner's message.
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={
                "message": "editer's text",
                "conversation_id": cid,
                "edit_message_id": owner_user_msg_id,
            },
            headers={"Authorization": f"Bearer {editer_token}"},
        )
        assert resp.status_code == 404
    finally:
        chat_api.get_llm_client = original_get_llm


async def test_branch_unknown_message_404(app_client: httpx.AsyncClient) -> None:
    """Branch endpoint with unknown message_id → 404."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "branchuser", "password": "br-u-pass-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    branch_token = await _login(app_client, "branchuser", "br-u-pass-1")

    resp = await app_client.post(
        "/api/chats/0000000000000000000000000000/branch",
        json={"message_id": 999999},
        headers={"Authorization": f"Bearer {branch_token}"},
    )
    assert resp.status_code == 404


async def test_branch_foreign_conversation_404(app_client: httpx.AsyncClient) -> None:
    """Branch endpoint on another user's conversation → 404."""
    admin_token = await _admin_login(app_client)

    await app_client.post(
        "/api/admin/users",
        json={"username": "br-owner", "password": "br-o-p-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    await app_client.post(
        "/api/admin/users",
        json={"username": "br-editer", "password": "br-e-p-1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    owner_token = await _login(app_client, "br-owner", "br-o-p-1")
    editer_token = await _login(app_client, "br-editer", "br-e-p-1")

    from mechanic.api.deps import get_hub

    hub = get_hub()
    conv = hub.chats.create_conversation("br-owner", "M333YK47")
    cid = conv["id"]
    hub.chats.add_message(cid, "user", "hello")
    hub.chats.add_message(cid, "assistant", "hi")

    all_msgs = hub.chats.get_messages(cid)
    user_msg_id = [m["id"] for m in all_msgs if m["role"] == "user"][0]

    resp = await app_client.post(
        f"/api/chats/{cid}/branch",
        json={"message_id": user_msg_id},
        headers={"Authorization": f"Bearer {editer_token}"},
    )
    assert resp.status_code == 404


async def test_branch_missing_auth_401(app_client: httpx.AsyncClient) -> None:
    """Branch endpoint without auth token → 401."""
    resp = await app_client.post(
        "/api/chats/some-id/branch",
        json={"message_id": 1},
    )
    assert resp.status_code == 401


async def test_message_shape_fields(app_client: httpx.AsyncClient) -> None:
    """GET /api/chats/{id} messages contain all new branching fields."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "shapeuser", "password": "shape-pw1", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    shape_token = await _login(app_client, "shapeuser", "shape-pw1")

    from mechanic.api.deps import get_hub

    hub = get_hub()
    conv = hub.chats.create_conversation("shapeuser", "M333YK47")
    cid = conv["id"]
    hub.chats.add_message(cid, "user", "question 1")
    hub.chats.add_message(cid, "assistant", "answer 1")

    resp = await app_client.get(
        f"/api/chats/{cid}",
        headers={"Authorization": f"Bearer {shape_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    messages = data["messages"]
    assert len(messages) == 2

    required_fields = {"id", "parent_id", "sibling_index", "sibling_count", "prev_sibling_id", "next_sibling_id"}
    for msg in messages:
        assert required_fields.issubset(msg.keys()), f"Missing fields in message {msg.get('id')}: {required_fields - set(msg.keys())}"

    # First user message has parent_id is None (root).
    user_msg = [m for m in messages if m["role"] == "user"][0]
    assert user_msg["parent_id"] is None


async def test_message_siblings_after_edit(app_client: httpx.AsyncClient) -> None:
    """Sibling metadata correct after an edit creates two siblings."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "sibuser", "password": "sibuserpw", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    sib_token = await _login(app_client, "sibuser", "sibuserpw")

    from mechanic.api.deps import get_hub
    import mechanic.api.chat_api as chat_api

    hub = get_hub()
    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: _FakeLLMClient()  # type: ignore[assignment]

    try:
        conv = hub.chats.create_conversation("sibuser", "M333YK47")
        cid = conv["id"]
        hub.chats.add_message(cid, "user", "original text")
        hub.chats.add_message(cid, "assistant", "answer to original")

        # Get the user message id.
        all_msgs = hub.chats.get_messages(cid)
        user_msg_id = [m["id"] for m in all_msgs if m["role"] == "user"][0]

        # Edit to create a sibling.
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={
                "message": "edited text",
                "conversation_id": cid,
                "edit_message_id": user_msg_id,
            },
            headers={"Authorization": f"Bearer {sib_token}"},
        )
        assert resp.status_code == 200

        # Capture the new user message id immediately after edit (before switching).
        all_after_edit = await app_client.get(
            f"/api/chats/{cid}",
            headers={"Authorization": f"Bearer {sib_token}"},
        )
        new_user_msg_id = [m["id"] for m in all_after_edit.json()["messages"] if m["text"] == "edited text"][0]

        # Switch to the old branch.
        from mechanic.llm.types import ChatRequest, StopReason, TextDelta, TurnComplete

        class _OldLLM:
            async def stream_chat(self, request):
                yield TextDelta("old answer")
                yield TurnComplete(
                    stop_reason=StopReason.END_TURN,
                    input_tokens=5,
                    output_tokens=3,
                )

            async def fetch_models(self, base_url: str, api_key: str) -> list:
                return []

        chat_api.get_llm_client = lambda protocol, transport=None: _OldLLM()  # type: ignore[assignment]
        try:
            resp_switch = await app_client.post(
                f"/api/chats/{cid}/branch",
                json={"message_id": user_msg_id},
                headers={"Authorization": f"Bearer {sib_token}"},
            )
            assert resp_switch.status_code == 200
            switch_data = resp_switch.json()
            old_messages = switch_data["messages"]

            # Find the user message on old branch.
            old_user = [m for m in old_messages if m["role"] == "user"][0]
            assert old_user["text"] == "original text"
            assert old_user["sibling_index"] == 1
            assert old_user["sibling_count"] == 2

            # Switch to new branch using the captured id.
            chat_api.get_llm_client = lambda protocol, transport=None: _FakeLLMClient()  # type: ignore[assignment]
            resp_new = await app_client.post(
                f"/api/chats/{cid}/branch",
                json={"message_id": new_user_msg_id},
                headers={"Authorization": f"Bearer {sib_token}"},
            )
            assert resp_new.status_code == 200
            new_data = resp_new.json()
            new_messages = new_data["messages"]

            # The edited user message on active path.
            new_user = [m for m in new_messages if m["role"] == "user"][0]
            assert new_user["text"] == "edited text"
            assert new_user["sibling_index"] == 2
            assert new_user["sibling_count"] == 2

            # prev_sibling_id / next_sibling_id should be set.
            assert new_user["prev_sibling_id"] is not None
        finally:
            chat_api.get_llm_client = original_get_llm
    finally:
        chat_api.get_llm_client = original_get_llm


async def test_conversation_message_count_grows_with_branches(app_client: httpx.AsyncClient) -> None:
    """Editing a message adds rows; total count reflects all branches."""
    admin_token = await _admin_login(app_client)
    await app_client.post(
        "/api/admin/users",
        json={"username": "countuser", "password": "countuserpw", "role": "user"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    cnt_token = await _login(app_client, "countuser", "countuserpw")

    from mechanic.api.deps import get_hub
    import mechanic.api.chat_api as chat_api

    hub = get_hub()
    original_get_llm = chat_api.get_llm_client
    chat_api.get_llm_client = lambda protocol, transport=None: _FakeLLMClient()  # type: ignore[assignment]

    try:
        conv = hub.chats.create_conversation("countuser", "M333YK47")
        cid = conv["id"]
        hub.chats.add_message(cid, "user", "msg1")
        hub.chats.add_message(cid, "assistant", "ans1")

        # Initial count: 2 messages.
        assert hub.chats.count_messages(cid) == 2

        user_msg_id = [m["id"] for m in hub.chats.get_messages(cid) if m["role"] == "user"][0]

        # Edit creates a new user + assistant row.
        resp = await app_client.post(
            "/api/chat/M333YK47",
            json={
                "message": "msg2",
                "conversation_id": cid,
                "edit_message_id": user_msg_id,
            },
            headers={"Authorization": f"Bearer {cnt_token}"},
        )
        assert resp.status_code == 200

        # Now there are 4 messages total (original user, original assistant, new user, new assistant).
        assert hub.chats.count_messages(cid) == 4
    finally:
        chat_api.get_llm_client = original_get_llm
