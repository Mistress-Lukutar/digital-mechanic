"""
File:   chats.py
Brief:  Persistent chat conversation and message store backed by SQLite,
        with branching support (edit creates sibling; active leaf tracks
        the current visible path).
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.2.0

Stores chat conversations, messages, and metadata so the frontend can
retrieve conversation lists, individual messages, and perform CRUD
operations on chat threads.  Branching: editing a user message creates
a sibling (same parent); each conversation has an active leaf; the
visible dialog is the path from root to the active leaf.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

_UNSET: object = object()


class ChatStore:
    """Chat conversation and message store backed by SQLite.

    Args:
        db_path: Filesystem path where the SQLite database will reside.
            Parent directories are created automatically if missing.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise the chat-store database.

        Creates parent directories, opens a connection with WAL journal mode,
        and creates the tables if they do not already exist.

        Args:
            db_path: Destination path for the SQLite database file.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_table()

    def _init_table(self) -> None:
        """Create the chat tables if they are missing, and migrate schema."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id          TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                vehicle_id  TEXT NOT NULL,
                title       TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chats_vehicle
                ON chat_conversations (username, vehicle_id, updated_at)
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role            TEXT NOT NULL,
                text            TEXT NOT NULL DEFAULT '',
                image           TEXT,
                ts              TEXT NOT NULL,
                parent_id       INTEGER
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_conv
                ON chat_messages (conversation_id, id)
            """
        )

        # Migrate: add parent_id column if missing.
        cursor = self._conn.execute(
            "PRAGMA table_info(chat_messages)"
        )
        columns = {row["name"] for row in cursor.fetchall()}
        if "parent_id" not in columns:
            self._conn.execute(
                "ALTER TABLE chat_messages ADD COLUMN parent_id INTEGER"
            )
            self._conn.execute(
                """
                UPDATE chat_messages SET parent_id = (
                    SELECT MAX(m2.id) FROM chat_messages m2
                    WHERE m2.conversation_id = chat_messages.conversation_id
                      AND m2.id < chat_messages.id
                ) WHERE parent_id IS NULL
                """
            )

        # Migrate: add active_leaf_id column if missing.
        cursor = self._conn.execute(
            "PRAGMA table_info(chat_conversations)"
        )
        columns = {row["name"] for row in cursor.fetchall()}
        if "active_leaf_id" not in columns:
            self._conn.execute(
                "ALTER TABLE chat_conversations ADD COLUMN active_leaf_id INTEGER"
            )
            self._conn.execute(
                """
                UPDATE chat_conversations SET active_leaf_id = (
                    SELECT MAX(m.id) FROM chat_messages m
                    WHERE m.conversation_id = chat_conversations.id
                ) WHERE active_leaf_id IS NULL
                """
            )

        self._conn.commit()

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    def create_conversation(
        self, username: str, vehicle_id: str, title: str = ""
    ) -> dict:
        """Create a new chat conversation.

        Args:
            username: Operator username.
            vehicle_id: Vehicle identifier.
            title: Optional conversation title; defaults to empty string.

        Returns:
            Dict with keys ``id``, ``username``, ``vehicle_id``, ``title``,
            ``created_at``, and ``updated_at``.
        """
        now = datetime.now(UTC).isoformat()
        conv_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO chat_conversations
                (id, username, vehicle_id, title, created_at, updated_at)
            VALUES (:id, :username, :vehicle_id, :title, :created_at, :updated_at)
            """,
            {
                "id": conv_id,
                "username": username,
                "vehicle_id": vehicle_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
            },
        )
        self._conn.commit()
        return {
            "id": conv_id,
            "username": username,
            "vehicle_id": vehicle_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }

    def get_conversation(self, conversation_id: str) -> dict | None:
        """Retrieve a single conversation with message count.

        Args:
            conversation_id: Primary key of the conversation.

        Returns:
            Dict with conversation fields plus ``message_count``,
            or ``None`` if not found.
        """
        cursor = self._conn.execute(
            """
            SELECT c.id, c.username, c.vehicle_id, c.title,
                   c.created_at, c.updated_at,
                   COUNT(m.id) AS message_count
            FROM chat_conversations c
            LEFT JOIN chat_messages m ON m.conversation_id = c.id
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (conversation_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def list_conversations(
        self, username: str, vehicle_id: str, limit: int = 50
    ) -> list[dict]:
        """List conversations for a user and vehicle.

        Args:
            username: Operator username to filter by.
            vehicle_id: Vehicle identifier to filter by.
            limit: Maximum number of rows to return. Defaults to 50.

        Returns:
            List of dicts with keys ``id``, ``title``, ``created_at``,
            ``updated_at``, and ``message_count``, ordered by
            ``updated_at`` descending.
        """
        cursor = self._conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   COUNT(m.id) AS message_count
            FROM chat_conversations c
            LEFT JOIN chat_messages m ON m.conversation_id = c.id
            WHERE c.username = ? AND c.vehicle_id = ?
            GROUP BY c.id
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (username, vehicle_id, limit),
        )
        return [dict(r) for r in cursor.fetchall()]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        text: str,
        image: str | None = None,
        parent_id: int | None | object = _UNSET,
    ) -> int | None:
        """Add a message to a conversation.

        Inserts the message row, updates the conversation's ``updated_at``,
        and backfills the title from the first message text if still empty.

        Args:
            conversation_id: Parent conversation primary key.
            role: ``'user'`` or ``'assistant'``.
            text: Message body text.
            image: Optional data-URL string; stored as-is.
            parent_id: Parent message this message follows.
                ``_UNSET`` (default) appends after the current active leaf;
                pass an explicit parent message id — or None for a root —
                to start a sibling branch.

        Returns:
            The new message id (int), or ``None`` if the conversation
            does not exist.
        """
        now = datetime.now(UTC).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id FROM chat_conversations WHERE id = ?",
                (conversation_id,),
            )
            if cursor.fetchone() is None:
                return None

            # Resolve parent: default to current active leaf.
            if parent_id is _UNSET:
                cursor = self._conn.execute(
                    "SELECT active_leaf_id FROM chat_conversations WHERE id = ?",
                    (conversation_id,),
                )
                row = cursor.fetchone()
                resolved_parent = row["active_leaf_id"] if row else None
            else:
                resolved_parent = parent_id

            self._conn.execute(
                """
                INSERT INTO chat_messages
                    (conversation_id, role, text, image, ts, parent_id)
                VALUES (:conversation_id, :role, :text, :image, :ts, :parent_id)
                """,
                {
                    "conversation_id": conversation_id,
                    "role": role,
                    "text": text,
                    "image": image,
                    "ts": now,
                    "parent_id": resolved_parent,
                },
            )
            new_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            self._conn.execute(
                """
                UPDATE chat_conversations
                SET title = CASE WHEN title = '' THEN ? ELSE title END,
                    updated_at = ?,
                    active_leaf_id = ?
                WHERE id = ?
                """,
                (text[:80], now, new_id, conversation_id),
            )
            self._conn.commit()
            return new_id

    def get_messages(self, conversation_id: str) -> list[dict]:
        """Retrieve the active path of messages for a conversation.

        Returns the chain from root to the currently active leaf in
        chronological order, with sibling metadata.

        Args:
            conversation_id: Parent conversation primary key.

        Returns:
            List of dicts with keys ``id``, ``role``, ``text``, ``image``,
            ``ts``, ``parent_id``, ``sibling_index``, ``sibling_count``,
            ``prev_sibling_id``, and ``next_sibling_id``, ordered by id
            ascending along the path from root to active leaf.
        """
        # Determine the leaf message id.
        cursor = self._conn.execute(
            "SELECT active_leaf_id FROM chat_conversations WHERE id = ?",
            (conversation_id,),
        )
        row = cursor.fetchone()
        if row and row["active_leaf_id"] is not None:
            leaf_id = row["active_leaf_id"]
        else:
            cursor = self._conn.execute(
                "SELECT MAX(id) FROM chat_messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            max_row = cursor.fetchone()
            leaf_id = max_row[0] if max_row and max_row[0] is not None else None

        if leaf_id is None:
            return []

        return self._path_dicts(conversation_id, leaf_id)

    def _path_dicts(self, conversation_id: str, leaf_id: int) -> list[dict]:
        """Build path dicts from root to the given leaf id.

        Args:
            conversation_id: The conversation these messages belong to.
            leaf_id: The message id at the end of the desired path.

        Returns:
            List of dicts in chronological order (root first).
        """
        # Fetch all messages for this conversation once.
        cursor = self._conn.execute(
            "SELECT id, conversation_id, role, text, image, ts, parent_id "
            "FROM chat_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        all_rows = cursor.fetchall()
        if not all_rows:
            return []

        # Index by id for quick lookup.
        msg_map: dict[int, sqlite3.Row] = {}
        for r in all_rows:
            msg_map[r["id"]] = r

        # Walk from leaf to root following parent_id.
        path_ids: list[int] = []
        visited: set[int] = set()
        current: int | None = leaf_id
        while current is not None:
            if current in visited:
                break  # cycle guard
            row = msg_map.get(current)
            if row is None:
                break
            path_ids.append(current)
            visited.add(current)
            current = row["parent_id"]

        # Reverse to chronological order (root first).
        path_ids.reverse()

        # Group siblings: same parent_id group together.
        sibling_groups: dict[int | None, list[int]] = {}
        for r in all_rows:
            pid = r["parent_id"]
            sibling_groups.setdefault(pid, []).append(r["id"])
        for pid in sibling_groups:
            sibling_groups[pid].sort()

        # Build result dicts.
        result: list[dict] = []
        for mid in path_ids:
            row = msg_map[mid]
            siblings = sibling_groups.get(row["parent_id"], [])
            idx = siblings.index(mid) + 1 if mid in siblings else 1
            prev_sid = siblings[idx - 2] if idx >= 2 else None
            next_sid = siblings[idx] if idx < len(siblings) else None

            result.append({
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "role": row["role"],
                "text": row["text"],
                "image": row["image"],
                "ts": row["ts"],
                "parent_id": row["parent_id"],
                "sibling_index": idx,
                "sibling_count": len(siblings),
                "prev_sibling_id": prev_sid,
                "next_sibling_id": next_sid,
            })

        return result

    def get_message(self, conversation_id: str, message_id: int) -> dict | None:
        """Retrieve a single message by id.

        Args:
            conversation_id: The conversation the message belongs to.
            message_id: Primary key of the message.

        Returns:
            Dict with keys ``id``, ``conversation_id``, ``role``, ``text``,
            ``image``, ``ts``, and ``parent_id``, or ``None`` if not found
            or belonging to another conversation.
        """
        cursor = self._conn.execute(
            """
            SELECT id, conversation_id, role, text, image, ts, parent_id
            FROM chat_messages
            WHERE id = ? AND conversation_id = ?
            """,
            (message_id, conversation_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def get_path_to(
        self, conversation_id: str, message_id: int
    ) -> list[dict]:
        """Return the chronological path from root to a given message.

        Args:
            conversation_id: The conversation the message belongs to.
            message_id: The target message id (leaf of the desired path).

        Returns:
            List of dicts in chronological order (root first), same shape
            as ``get_messages()``; empty list if the message does not exist
            in that conversation.
        """
        # Verify the message exists in this conversation.
        cursor = self._conn.execute(
            "SELECT id FROM chat_messages WHERE id = ? AND conversation_id = ?",
            (message_id, conversation_id),
        )
        if cursor.fetchone() is None:
            return []

        return self._path_dicts(conversation_id, message_id)

    def switch_branch(
        self, conversation_id: str, message_id: int
    ) -> bool:
        """Switch the active leaf to the deepest descendant of a message.

        Descends from ``message_id`` by repeatedly finding the child with
        the highest id until no children remain; that final id becomes the
        new ``active_leaf_id``.  Switching to a sibling version activates
        the branch ending at that sibling's latest descendant.

        Args:
            conversation_id: The conversation containing the message.
            message_id: The starting message id for the descent.

        Returns:
            ``True`` if the message exists in the conversation and the
            active leaf was updated; ``False`` otherwise.
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id FROM chat_messages WHERE id = ? AND conversation_id = ?",
                (message_id, conversation_id),
            )
            if cursor.fetchone() is None:
                return False

            current = message_id
            while True:
                cursor = self._conn.execute(
                    "SELECT MAX(id) FROM chat_messages "
                    "WHERE conversation_id = ? AND parent_id = ?",
                    (conversation_id, current),
                )
                child_row = cursor.fetchone()
                if child_row[0] is None:
                    break
                current = child_row[0]

            self._conn.execute(
                "UPDATE chat_conversations SET active_leaf_id = ? WHERE id = ?",
                (current, conversation_id),
            )
            self._conn.commit()
            return True

    def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation and all its messages.

        Args:
            conversation_id: Primary key of the conversation to remove.
        """
        with self._lock:
            self._conn.execute(
                "DELETE FROM chat_messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            self._conn.execute(
                "DELETE FROM chat_conversations WHERE id = ?",
                (conversation_id,),
            )
            self._conn.commit()

    def count_messages(self, conversation_id: str) -> int:
        """Count messages in a conversation.

        Args:
            conversation_id: Parent conversation primary key.

        Returns:
            Integer message count.
        """
        cursor = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM chat_messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        return cursor.fetchone()["cnt"]
