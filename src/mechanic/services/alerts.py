'''
File:   alerts.py
Brief:  Admin alert store for non-standard agent situations.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0

Records automatic alerts raised by deterministic gates and agent tools
(warning overrides, diagnostics/card mismatches, missing instructions) so
administrators can review them and follow up with the manual authors.
'''

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class AlertRow(BaseModel):
    '''One admin alert entry.'''

    id: int
    ts: str
    username: str | None = None
    vehicle_id: str | None = None
    session_id: str | None = None
    engine_model: str | None = None
    kind: str
    text: str
    is_read: bool = False


class AlertsStore:
    """Admin alert store backed by SQLite (same DB as auth/usage).

    Args:
        db_path: Filesystem path of the SQLite database file.
            Parent directories are created automatically if missing.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise the alerts database.

        Creates parent directories, opens a connection with WAL journal mode,
        and creates the ``alerts`` table if it does not already exist.

        Args:
            db_path: Destination path for the SQLite database file.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_table()

    def _init_table(self) -> None:
        """Create the ``alerts`` table if it is missing."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           TEXT NOT NULL,
                username     TEXT,
                vehicle_id   TEXT,
                session_id   TEXT,
                engine_model TEXT,
                kind         TEXT NOT NULL,
                text         TEXT NOT NULL,
                is_read      INTEGER DEFAULT 0
            )
            """
        )
        # Idempotent migration: add ``is_read`` column on existing DBs.
        cursor = self._conn.execute("PRAGMA table_info(alerts)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "is_read" not in columns:
            self._conn.execute(
                "ALTER TABLE alerts ADD COLUMN is_read INTEGER DEFAULT 0"
            )
        self._conn.commit()

    def add(
        self,
        kind: str,
        text: str,
        *,
        username: str | None = None,
        vehicle_id: str | None = None,
        session_id: str | None = None,
        engine_model: str | None = None,
    ) -> int:
        """Insert a new alert row.

        Args:
            kind: Alert category string (e.g. "warning_override").
            text: Human-readable description of the alert event.
            username: Operator username, or ``None``.
            vehicle_id: Vehicle identifier, or ``None``.
            session_id: Session identifier, or ``None``.
            engine_model: Engine model string, or ``None``.

        Returns:
            The auto-increment primary key of the inserted row.
        """
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "username": username,
            "vehicle_id": vehicle_id,
            "session_id": session_id,
            "engine_model": engine_model,
            "kind": kind,
            "text": text,
            "is_read": 0,
        }

        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO alerts (ts, username, vehicle_id, session_id,
                                    engine_model, kind, text, is_read)
                VALUES (:ts, :username, :vehicle_id, :session_id,
                        :engine_model, :kind, :text, :is_read)
                """,
                row,
            )
            self._conn.commit()
            return cursor.lastrowid

    def recent(self, limit: int = 50) -> list[AlertRow]:
        """Return the most recent alert entries.

        Args:
            limit: Maximum number of rows to return. Defaults to 50.

        Returns:
            List of :class:`AlertRow` sorted by ``id`` descending (newest first).
        """
        cursor = self._conn.execute(
            """
            SELECT id, ts, username, vehicle_id, session_id, engine_model,
                   kind, text, is_read
            FROM alerts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows: list[AlertRow] = []
        for r in cursor.fetchall():
            rows.append(
                AlertRow(
                    id=r["id"],
                    ts=r["ts"],
                    username=r["username"],
                    vehicle_id=r["vehicle_id"],
                    session_id=r["session_id"],
                    engine_model=r["engine_model"],
                    kind=r["kind"],
                    text=r["text"],
                    is_read=bool(r["is_read"]),
                )
            )
        return rows

    def unread_count(self) -> int:
        """Return the number of unread alerts.

        Returns:
            Count of rows where ``is_read`` is 0.
        """
        cursor = self._conn.execute(
            "SELECT COUNT(*) AS cnt FROM alerts WHERE is_read = 0"
        )
        return cursor.fetchone()["cnt"]

    def mark_read(self, alert_id: int) -> bool:
        """Mark one alert as read.

        Args:
            alert_id: Primary key of the alert row.

        Returns:
            ``True`` when a row was updated, ``False`` otherwise.
        """
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE alerts SET is_read = 1 WHERE id = ? AND is_read = 0",
                (alert_id,),
            )
            affected = cursor.rowcount
            self._conn.commit()
            return bool(affected)

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()
