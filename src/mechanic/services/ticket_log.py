"""
File:   ticket_log.py
Brief:  Local per-vehicle ticket history backed by SQLite.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Stores diagnostic defect-inspection tickets so the agent can recall
previous reports for any vehicle without re-calling TOiR.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from shared.models import TicketPayload, TicketRecord, TicketResult


class TicketLog:
    """Per-vehicle ticket history stored in a local SQLite database.

    The database uses WAL mode for concurrent-read safety and a threading
    lock around writes to prevent interleaved inserts from the same process.

    Args:
        db_path: Filesystem path where the SQLite database will reside.
            Parent directories are created automatically if missing.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise the ticket-log database.

        Creates parent directories, opens a connection with WAL journal mode,
        and creates the ``tickets`` table if it does not already exist.

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
        """Create the ``tickets`` table if it is missing."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id   TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                vehicle_id  TEXT NOT NULL,
                session_id  TEXT NOT NULL,
                username    TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_vehicle_id ON tickets(vehicle_id)"
        )
        self._conn.commit()

    def add(
        self,
        result: TicketResult,
        payload: TicketPayload,
        username: str,
        created_at: datetime | None = None,
    ) -> TicketRecord:
        """Insert a ticket record into the log.

        Args:
            result: Mock TOiR response confirming ticket creation.
            payload: Full defect-inspection payload to persist.
            username: Username of the operator who created the ticket.
            created_at: Optional ISO-8601 timestamp; defaults to current UTC.

        Returns:
            The stored :class:`~shared.models.TicketRecord`.

        Raises:
            sqlite3.IntegrityError: If *ticket_id* already exists.
        """
        if created_at is None:
            created_at = datetime.now(UTC)

        row = {
            "ticket_id": result.ticket_id,
            "created_at": created_at.isoformat(),
            "vehicle_id": payload.vehicle_id,
            "session_id": payload.session_id,
            "username": username,
            "payload_json": payload.model_dump_json(),
        }

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO tickets (ticket_id, created_at, vehicle_id, session_id,
                                     username, payload_json)
                VALUES (:ticket_id, :created_at, :vehicle_id, :session_id,
                        :username, :payload_json)
                """,
                row,
            )
            self._conn.commit()

        return TicketRecord(
            ticket_id=result.ticket_id,
            created_at=created_at,
            payload=payload,
        )

    def list_by_vehicle(self, vehicle_id: str) -> list[TicketRecord]:
        """Return all tickets for *vehicle_id*, newest first.

        Args:
            vehicle_id: License-plate identifier of the vehicle.

        Returns:
            List of :class:`~shared.models.TicketRecord` sorted by
            ``created_at`` descending.
        """
        cursor = self._conn.execute(
            """
            SELECT ticket_id, created_at, payload_json
            FROM tickets
            WHERE vehicle_id = ?
            ORDER BY created_at DESC
            """,
            (vehicle_id,),
        )
        records: list[TicketRecord] = []
        for row in cursor.fetchall():
            records.append(
                TicketRecord(
                    ticket_id=row["ticket_id"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    payload=TicketPayload.model_validate_json(row["payload_json"]),
                )
            )
        return records

    def count(self) -> int:
        """Return the total number of tickets stored.

        Returns:
            Integer count of all ticket records in the database.
        """
        cursor = self._conn.execute("SELECT COUNT(*) AS cnt FROM tickets")
        return cursor.fetchone()["cnt"]
