"""
File:   test_chats_store.py
Brief:  Tests for ChatStore — persistent chat conversation and message store.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0
"""

from __future__ import annotations

import pytest

from mechanic.services.chats import ChatStore


class TestCreateConversation:
    """Test create_conversation()."""

    def test_create_returns_matching_dict(self, tmp_path: pytest.TempPath) -> None:
        """create_conversation() returns a dict with all expected fields."""
        store = ChatStore(tmp_path / "chats.db")
        conv = store.create_conversation("user_alpha", "veh_A1", "My Chat")

        assert isinstance(conv, dict)
        assert len(conv["id"]) > 0  # non-empty hex id from uuid4().hex
        assert conv["username"] == "user_alpha"
        assert conv["vehicle_id"] == "veh_A1"
        assert conv["title"] == "My Chat"
        assert conv["created_at"] is not None
        assert conv["updated_at"] is not None

    def test_create_empty_title(self, tmp_path: pytest.TempPath) -> None:
        """create_conversation() works with an empty title."""
        store = ChatStore(tmp_path / "chats2.db")
        conv = store.create_conversation("user_beta", "veh_B2")

        assert conv["title"] == ""
        assert conv["created_at"] == conv["updated_at"]


class TestAddMessageAndGetMessages:
    """Test add_message() and get_messages()."""

    def test_roundtrip_no_image(self, tmp_path: pytest.TempPath) -> None:
        """add_message + get_messages round-trip preserves order without image."""
        store = ChatStore(tmp_path / "chats3.db")
        conv_id = store.create_conversation(
            "user_gamma", "veh_C3", "Roundtrip Test"
        )["id"]

        store.add_message(conv_id, "user", "Hello!")
        store.add_message(conv_id, "assistant", "Hi there!")

        messages = store.get_messages(conv_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["text"] == "Hello!"
        assert messages[0]["image"] is None
        assert messages[1]["role"] == "assistant"
        assert messages[1]["text"] == "Hi there!"

    def test_roundtrip_with_image(self, tmp_path: pytest.TempPath) -> None:
        """add_message + get_messages round-trip preserves data-URL image."""
        store = ChatStore(tmp_path / "chats4.db")
        conv_id = store.create_conversation(
            "user_delta", "veh_D4", "Image Test"
        )["id"]

        data_url = "data:image/png;base64,abc123"
        store.add_message(conv_id, "user", "Look at this", image=data_url)

        messages = store.get_messages(conv_id)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["text"] == "Look at this"
        assert messages[0]["image"] == data_url


class TestTitleBackfill:
    """Test title backfill behaviour."""

    def test_empty_title_backfilled_from_first_message(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """Conversation with empty title gets title from first message text."""
        store = ChatStore(tmp_path / "chats5.db")
        conv_id = store.create_conversation("user_epsilon", "veh_E5")["id"]

        long_text = ("This is a very long message that should be "
                     "truncated to eighty characters")
        store.add_message(conv_id, "user", long_text)

        conv = store.get_conversation(conv_id)
        assert conv["title"] == long_text[:80]

    def test_existing_title_preserved(self, tmp_path: pytest.TempPath) -> None:
        """Conversation created with a title keeps it after messages are added."""
        store = ChatStore(tmp_path / "chats6.db")
        conv_id = store.create_conversation(
            "user_zeta", "veh_F6", "My Preserved Title"
        )["id"]

        store.add_message(conv_id, "user", "Hello!")

        conv = store.get_conversation(conv_id)
        assert conv["title"] == "My Preserved Title"


class TestListConversations:
    """Test list_conversations()."""

    def test_filters_by_username_and_vehicle(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """list_conversations() filters by username AND vehicle_id."""
        store = ChatStore(tmp_path / "chats7.db")
        store.create_conversation("user_eta", "veh_G1", "Chat 1")
        store.create_conversation("user_eta", "veh_G2", "Chat 2")
        store.create_conversation("user_epsilon", "veh_G1", "Chat 3")

        results = store.list_conversations("user_eta", "veh_G1")
        assert len(results) == 1
        assert results[0]["title"] == "Chat 1"

    def test_newest_updated_first(self, tmp_path: pytest.TempPath) -> None:
        """list_conversations() returns conversations newest-updated first."""
        store = ChatStore(tmp_path / "chats8.db")
        conv_a_id = store.create_conversation(
            "user_theta", "veh_H1", "Older"
        )["id"]
        store.create_conversation(
            "user_theta", "veh_H1", "Newer"
        )

        # Add a message to the older conversation so its updated_at changes.
        import time

        time.sleep(0.05)
        store.add_message(conv_a_id, "user", "Updated older chat")

        results = store.list_conversations("user_theta", "veh_H1")
        assert len(results) == 2
        assert results[0]["title"] == "Older"
        assert results[1]["title"] == "Newer"

    def test_message_count_correct(self, tmp_path: pytest.TempPath) -> None:
        """list_conversations() message_count reflects actual count."""
        store = ChatStore(tmp_path / "chats9.db")
        conv_id = store.create_conversation(
            "user_iota", "veh_I1", "Count Test"
        )["id"]

        store.add_message(conv_id, "user", "Msg 1")
        store.add_message(conv_id, "assistant", "Reply 1")
        store.add_message(conv_id, "user", "Msg 2")

        results = store.list_conversations("user_iota", "veh_I1")
        assert len(results) == 1
        assert results[0]["message_count"] == 3

    def test_limit_respected(self, tmp_path: pytest.TempPath) -> None:
        """list_conversations() respects the limit parameter."""
        store = ChatStore(tmp_path / "chats10.db")
        for i in range(5):
            store.create_conversation("user_kappa", "veh_K1", f"Chat {i}")

        results = store.list_conversations("user_kappa", "veh_K1", limit=2)
        assert len(results) == 2


class TestDeleteConversation:
    """Test delete_conversation()."""

    def test_removes_conversation_and_messages(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """delete_conversation() removes both conversation and messages."""
        store = ChatStore(tmp_path / "chats11.db")
        conv_id = store.create_conversation(
            "user_lambda", "veh_L1", "Delete Test"
        )["id"]

        store.add_message(conv_id, "user", "Msg 1")
        store.add_message(conv_id, "assistant", "Reply 1")

        store.delete_conversation(conv_id)

        assert store.get_conversation(conv_id) is None
        assert store.count_messages(conv_id) == 0


class TestUnknownConversation:
    """Test behaviour with unknown conversation ids."""

    def test_get_conversation_returns_none(self, tmp_path: pytest.TempPath) -> None:
        """get_conversation() returns None for an unknown id."""
        store = ChatStore(tmp_path / "chats12.db")
        result = store.get_conversation("nonexistent_id")
        assert result is None

    def test_add_message_on_unknown_is_noop(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """add_message() on unknown id does not raise."""
        store = ChatStore(tmp_path / "chats13.db")
        store.add_message("unknown_id", "user", "Hello!")

        messages = store.get_messages("unknown_id")
        assert len(messages) == 0

    def test_count_messages_on_unknown(self, tmp_path: pytest.TempPath) -> None:
        """count_messages() returns 0 for unknown id."""
        store = ChatStore(tmp_path / "chats14.db")
        count = store.count_messages("unknown_id")
        assert count == 0
