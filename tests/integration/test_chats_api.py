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
