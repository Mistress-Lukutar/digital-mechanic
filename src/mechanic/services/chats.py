"""
File:   chats.py
Brief:  Persistent chat conversation and message store backed by SQLite.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0

Stores chat conversations, messages, and metadata so the frontend can
retrieve conversation lists, individual messages, and perform CRUD
operations on chat threads.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path


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
        """Create the chat tables if they are missing."""
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
                ts              TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chat_messages_conv
                ON chat_messages (conversation_id, id)
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
    ) -> None:
        """Add a message to a conversation.

        Inserts the message row, updates the conversation's ``updated_at``,
        and backfills the title from the first message text if still empty.

        Args:
            conversation_id: Parent conversation primary key.
            role: ``'user'`` or ``'assistant'``.
            text: Message body text.
            image: Optional data-URL string; stored as-is.
        """
        now = datetime.now(UTC).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id FROM chat_conversations WHERE id = ?",
                (conversation_id,),
            )
            if cursor.fetchone() is None:
                return

            self._conn.execute(
                """
                INSERT INTO chat_messages
                    (conversation_id, role, text, image, ts)
                VALUES (:conversation_id, :role, :text, :image, :ts)
                """,
                {
                    "conversation_id": conversation_id,
                    "role": role,
                    "text": text,
                    "image": image,
                    "ts": now,
                },
            )
            self._conn.execute(
                """
                UPDATE chat_conversations
                SET title = CASE WHEN title = '' THEN ? ELSE title END,
                    updated_at = ?
                WHERE id = ?
                """,
                (text[:80], now, conversation_id),
            )
            self._conn.commit()

    def get_messages(self, conversation_id: str) -> list[dict]:
        """Retrieve all messages for a conversation.

        Args:
            conversation_id: Parent conversation primary key.

        Returns:
            List of dicts with keys ``role``, ``text``, ``image``, and ``ts``,
            ordered by message id ascending.
        """
        cursor = self._conn.execute(
            """
            SELECT role, text, image, ts
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

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
