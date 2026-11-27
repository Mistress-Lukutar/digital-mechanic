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


class TestBranchingLinearIdsAndParentChain:
    """Test add_message() linear insertion and parent chain."""

    def test_add_message_returns_increasing_int_ids_and_linear_parent_chain(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """add_message() returns increasing integer ids; parent_id forms a chain."""
        store = ChatStore(tmp_path / "chats15.db")
        conv_id = store.create_conversation(
            "user_alpha", "veh_A1", "Linear Chain"
        )["id"]

        id_u1 = store.add_message(conv_id, "user", "Hello")
        id_a1 = store.add_message(conv_id, "assistant", "Hi back")
        id_u2 = store.add_message(conv_id, "user", "How are you?")
        id_a2 = store.add_message(conv_id, "assistant", "I'm fine")

        # IDs must be strictly increasing positive integers.
        assert isinstance(id_u1, int) and id_u1 > 0
        assert isinstance(id_a1, int) and id_a1 > 0
        assert isinstance(id_u2, int) and id_u2 > 0
        assert isinstance(id_a2, int) and id_a2 > 0
        assert id_u1 < id_a1 < id_u2 < id_a2

        # Parent chain: each message's parent_id must be the previous one.
        msgs = store.get_messages(conv_id)
        assert len(msgs) == 4
        assert msgs[0]["parent_id"] is None          # root message
        assert msgs[1]["parent_id"] == id_u1         # assistant follows user
        assert msgs[2]["parent_id"] == id_a1         # user follows assistant
        assert msgs[3]["parent_id"] == id_u2         # assistant follows user

        # Verify via get_message as well.
        for mid, expected_parent in [
            (id_u1, None),
            (id_a1, id_u1),
            (id_u2, id_a1),
            (id_a2, id_u2),
        ]:
            row = store.get_message(conv_id, mid)
            assert row is not None
            assert row["parent_id"] == expected_parent


class TestEditSimulationSiblingBranch:
    """Test creating a sibling branch via explicit parent_id."""

    def test_edit_simulation_siblings_and_active_path(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """Editing u2 by adding with parent_id=u1 shifts the active path."""
        store = ChatStore(tmp_path / "chats16.db")
        conv_id = store.create_conversation(
            "user_beta", "veh_B2", "Edit Simulation"
        )["id"]

        # Build original linear chain: u1 -> a1 -> u2 -> a2
        id_u1 = store.add_message(conv_id, "user", "Hello")
        id_a1 = store.add_message(conv_id, "assistant", "Hi there!")
        id_u2 = store.add_message(conv_id, "user", "How are you?")
        id_a2 = store.add_message(conv_id, "assistant", "I'm fine.")

        # Now edit u2 by adding a sibling with explicit parent_id=u1.
        id_u2_prime = store.add_message(
            conv_id, "user", "How are you doing today?", parent_id=id_u1
        )

        # Active path follows parent_id chain from leaf: [u1, u2'].
        active = store.get_messages(conv_id)
        assert len(active) == 2
        assert active[0]["id"] == id_u1
        assert active[1]["id"] == id_u2_prime

        # The last entry's text must be u2'.
        assert active[-1]["text"] == "How are you doing today?"

        # Old u2/a2 rows still exist in the database.
        assert store.count_messages(conv_id) == 5

    def test_edit_mid_chain_keeps_prefix_and_switches_path(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """Editing u2 (parent=a1) yields active path [u1, a1, u2']."""
        store = ChatStore(tmp_path / "chats16b.db")
        conv_id = store.create_conversation(
            "user_beta", "veh_B2", "Mid-chain Edit"
        )["id"]

        id_u1 = store.add_message(conv_id, "user", "Hello")
        id_a1 = store.add_message(conv_id, "assistant", "Hi there!")
        id_u2 = store.add_message(conv_id, "user", "How are you?")
        id_a2 = store.add_message(conv_id, "assistant", "I'm fine.")

        # Real edit flow: the new version gets the edited message's parent.
        edited = store.get_message(conv_id, id_u2)
        assert edited is not None
        id_u2_prime = store.add_message(
            conv_id, "user", "Edited question", parent_id=edited["parent_id"]
        )

        active = store.get_messages(conv_id)
        assert [m["id"] for m in active] == [id_u1, id_a1, id_u2_prime]
        assert active[-1]["sibling_count"] == 2
        assert active[-1]["prev_sibling_id"] == id_u2

        # The abandoned tail a2 is preserved but not on the active path.
        assert store.count_messages(conv_id) == 5
        assert id_a2 not in [m["id"] for m in active]


class TestSiblingMetadata:
    """Test sibling_index, sibling_count, prev/next sibling fields."""

    def test_sibling_metadata_after_edit(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """Active path entry for u2' carries correct sibling metadata."""
        store = ChatStore(tmp_path / "chats17.db")
        conv_id = store.create_conversation(
            "user_gamma", "veh_C3", "Sibling Meta"
        )["id"]

        id_u1 = store.add_message(conv_id, "user", "Hello")
        id_a1 = store.add_message(conv_id, "assistant", "Hi there!")
        id_u2 = store.add_message(conv_id, "user", "How are you?")
        _id_a2 = store.add_message(conv_id, "assistant", "I'm fine.")

        # Add sibling of u2 via parent_id=u1.
        id_u2_prime = store.add_message(
            conv_id, "user", "How are you doing today?", parent_id=id_u1
        )

        active = store.get_messages(conv_id)
        u2_prime_entry = next(e for e in active if e["id"] == id_u2_prime)

        # Messages with parent_id=id_u1 form the sibling group: [a1(id=2),
        # u2'(id=5)].  Sorted by id, u2' is at index 2.
        assert u2_prime_entry["sibling_count"] == 2
        assert u2_prime_entry["sibling_index"] == 2
        assert u2_prime_entry["prev_sibling_id"] == id_a1
        assert u2_prime_entry["next_sibling_id"] is None

        # Also verify the original u2 entry (via path to a2).
        store.switch_branch(conv_id, id_u2)
        active_a2 = store.get_messages(conv_id)
        u2_entry = next(e for e in active_a2 if e["id"] == id_u2)
        # u2 has parent_id=id_a1; sibling group under a1 is [a2(id=4)].
        assert u2_entry["sibling_count"] == 1
        assert u2_entry["sibling_index"] == 1
        assert u2_entry["next_sibling_id"] is None

        # And verify u2' entry on this path (via switch back).
        store.switch_branch(conv_id, id_u2_prime)
        active_u2p = store.get_messages(conv_id)
        u2p_entry = next(e for e in active_u2p if e["id"] == id_u2_prime)
        assert u2p_entry["prev_sibling_id"] == id_a1


class TestSwitchBranch:
    """Test switch_branch() toggling between sibling branches."""

    def test_switch_branch_back_and_forth(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """switch_branch() toggles active path between sibling branches."""
        store = ChatStore(tmp_path / "chats18.db")
        conv_id = store.create_conversation(
            "user_delta", "veh_D4", "Switch Branch"
        )["id"]

        id_u1 = store.add_message(conv_id, "user", "Hello")
        id_a1 = store.add_message(conv_id, "assistant", "Hi there!")
        id_u2 = store.add_message(conv_id, "user", "How are you?")
        id_a2 = store.add_message(conv_id, "assistant", "I'm fine.")

        # Create sibling branch.
        id_u2_prime = store.add_message(
            conv_id, "user", "How are you doing today?", parent_id=id_u1
        )

        # switch_branch(u2) → path [u1, a1, u2, a2].
        assert store.switch_branch(conv_id, id_u2) is True
        active = store.get_messages(conv_id)
        assert len(active) == 4
        assert active[2]["id"] == id_u2
        assert active[3]["id"] == id_a2

        # u2 entry: parent_id=id_a1; sibling group under a1 is [a2(id=4)].
        u2_entry = next(e for e in active if e["id"] == id_u2)
        assert u2_entry["sibling_index"] == 1
        assert u2_entry["next_sibling_id"] is None

        # switch_branch(u2') → path [u1, u2'] (parent_id chain: u2'→u1).
        assert store.switch_branch(conv_id, id_u2_prime) is True
        active = store.get_messages(conv_id)
        assert len(active) == 2
        assert active[1]["id"] == id_u2_prime


class TestSwitchBranchForeignAndNonexistent:
    """Test switch_branch() with foreign or nonexistent message ids."""

    def test_switch_branch_foreign_conversation(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """switch_branch() returns False for a message from another conversation."""
        store = ChatStore(tmp_path / "chats19.db")
        conv_id_a = store.create_conversation(
            "user_eta", "veh_E5", "Conv A"
        )["id"]
        conv_id_b = store.create_conversation(
            "user_eta", "veh_E6", "Conv B"
        )["id"]

        id_msg_a = store.add_message(conv_id_a, "user", "Hello from A")
        store.add_message(conv_id_a, "assistant", "Reply A")

        id_msg_b = store.add_message(conv_id_b, "user", "Hello from B")

        # Switch conv B's branch using a message id from conv A.
        assert store.switch_branch(conv_id_b, id_msg_a) is False

        # Active path for B should still be [msg_b].
        active = store.get_messages(conv_id_b)
        assert len(active) == 1
        assert active[0]["id"] == id_msg_b

    def test_switch_branch_nonexistent_id(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """switch_branch() returns False for a completely nonexistent id."""
        store = ChatStore(tmp_path / "chats19b.db")
        conv_id = store.create_conversation(
            "user_epsilon", "veh_F6", "Nonexistent"
        )["id"]

        assert store.switch_branch(conv_id, 999_999) is False

        # Active path unchanged (empty).
        active = store.get_messages(conv_id)
        assert len(active) == 0


class TestGetMessage:
    """Test get_message() for valid and invalid lookups."""

    def test_get_message_valid_id(self, tmp_path: pytest.TempPath) -> None:
        """get_message() returns the row dict for a valid message id."""
        store = ChatStore(tmp_path / "chats20.db")
        conv_id = store.create_conversation(
            "user_zeta", "veh_G1", "Get Message"
        )["id"]

        msg_id = store.add_message(conv_id, "user", "Hello!")
        row = store.get_message(conv_id, msg_id)

        assert row is not None
        assert row["id"] == msg_id
        assert row["role"] == "user"
        assert row["text"] == "Hello!"
        assert row["conversation_id"] == conv_id
        assert "ts" in row
        assert "parent_id" in row

    def test_get_message_foreign_conversation(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """get_message() returns None when message id belongs to another conversation."""
        store = ChatStore(tmp_path / "chats21.db")
        conv_a_id = store.create_conversation(
            "user_eta", "veh_H1", "Conv A"
        )["id"]
        conv_b_id = store.create_conversation(
            "user_eta", "veh_H2", "Conv B"
        )["id"]

        msg_id_a = store.add_message(conv_a_id, "user", "Hello from A")

        # Looking up msg_a in conv_b should return None.
        assert store.get_message(conv_b_id, msg_id_a) is None

    def test_get_message_nonexistent_id(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """get_message() returns None for a nonexistent id."""
        store = ChatStore(tmp_path / "chats22.db")
        conv_id = store.create_conversation(
            "user_theta", "veh_I1", "Missing"
        )["id"]

        assert store.get_message(conv_id, 999_999) is None


class TestGetPathTo:
    """Test get_path_to() for valid and invalid targets."""

    def test_get_path_to_valid(self, tmp_path: pytest.TempPath) -> None:
        """get_path_to() returns [u1, a1] for the assistant's message id."""
        store = ChatStore(tmp_path / "chats23.db")
        conv_id = store.create_conversation(
            "user_iota", "veh_J1", "Path To"
        )["id"]

        id_u1 = store.add_message(conv_id, "user", "Hello")
        id_a1 = store.add_message(conv_id, "assistant", "Hi there!")

        path = store.get_path_to(conv_id, id_a1)
        assert len(path) == 2
        assert path[0]["id"] == id_u1
        assert path[0]["role"] == "user"
        assert path[1]["id"] == id_a1
        assert path[1]["role"] == "assistant"

    def test_get_path_to_foreign_or_nonexistent(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """get_path_to() returns [] for a foreign or nonexistent id."""
        store = ChatStore(tmp_path / "chats24.db")
        conv_id = store.create_conversation(
            "user_kappa", "veh_K1", "Path Foreign"
        )["id"]

        store.add_message(conv_id, "user", "Hello")

        # Nonexistent id.
        assert store.get_path_to(conv_id, 999_999) == []

        # Id from another conversation.
        other_conv = store.create_conversation(
            "user_kappa", "veh_K2", "Other"
        )["id"]
        foreign_msg_id = store.add_message(other_conv, "user", "Foreign")
        assert store.get_path_to(conv_id, foreign_msg_id) == []


class TestEditRootMessage:
    """Test branching from the root message (parent_id=None)."""

    def test_edit_root_message_and_switch(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """Editing the root creates a sibling; switch_branch toggles."""
        store = ChatStore(tmp_path / "chats25.db")
        conv_id = store.create_conversation(
            "user_lambda", "veh_L1", "Root Edit"
        )["id"]

        id_u1 = store.add_message(conv_id, "user", "Original root")
        _id_a1 = store.add_message(conv_id, "assistant", "Reply to original")

        # Add u1' with explicit parent_id=None (sibling of u1 at root).
        id_u1_prime = store.add_message(
            conv_id, "user", "New root message", parent_id=None
        )

        # Active path should now be [u1'].
        active = store.get_messages(conv_id)
        assert len(active) == 1
        assert active[0]["id"] == id_u1_prime
        assert active[0]["text"] == "New root message"

        # u1' should have sibling_count==2 (u1 and u1').
        assert active[0]["sibling_count"] == 2

        # switch_branch to original u1 → path [u1, a1].
        assert store.switch_branch(conv_id, id_u1) is True
        active = store.get_messages(conv_id)
        assert len(active) == 2
        assert active[0]["id"] == id_u1
        assert active[1]["id"] == _id_a1


class TestDeleteConversationRemovesAllBranches:
    """Test that delete_conversation cleans up all branches."""

    def test_delete_removes_all_branch_data(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """After edits and branching, delete_conversation empties everything."""
        store = ChatStore(tmp_path / "chats26.db")
        conv_id = store.create_conversation(
            "user_mu", "veh_M1", "Delete All"
        )["id"]

        id_u1 = store.add_message(conv_id, "user", "Hello")
        _id_a1 = store.add_message(conv_id, "assistant", "Hi!")
        id_u2 = store.add_message(conv_id, "user", "How are you?")
        _id_a2 = store.add_message(conv_id, "assistant", "Fine.")

        # Create a sibling branch.
        store.add_message(
            conv_id, "user", "Revised question?", parent_id=id_u1
        )

        assert store.count_messages(conv_id) == 5
        store.delete_conversation(conv_id)

        assert store.get_messages(conv_id) == []
        assert store.count_messages(conv_id) == 0


class TestEmptyConversation:
    """Test behaviour of an empty conversation."""

    def test_get_messages_empty_returns_list(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """get_messages() on a freshly created conversation returns []."""
        store = ChatStore(tmp_path / "chats27.db")
        conv_id = store.create_conversation(
            "user_nu", "veh_N1", "Empty"
        )["id"]

        active = store.get_messages(conv_id)
        assert isinstance(active, list)
        assert len(active) == 0
