"""
File:   usage.py
Brief:  Request/token log for the admin dashboard.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.2.0

Tracks every API call (chat, ticket_submit, etc.) with token counts,
duration and status so administrators can audit usage patterns.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel


class UsageTotals(BaseModel):
    """Aggregated usage statistics.

    Attributes:
        requests_total: Total number of logged requests.
        requests_error: Number of requests with status "error".
        input_tokens: Sum of all input tokens across requests.
        output_tokens: Sum of all output tokens across requests.
    """

    requests_total: int = 0
    requests_error: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class UsageRow(BaseModel):
    """One row from the usage request log.

    Attributes:
        id: Auto-incrementing primary key.
        ts: ISO 8601 timestamp of the request.
        username: Operator username, or ``None`` for system requests.
        vehicle_id: Vehicle identifier, or ``None`` if not applicable.
        kind: Request category (e.g. "chat", "ticket_submit").
        model: Model name used, or ``None``.
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens produced.
        duration_ms: Wall-clock duration in milliseconds.
        status: "ok" or "error".
        error: Error message, or ``None`` on success.
    """

    id: int
    ts: str
    username: str | None = None
    vehicle_id: str | None = None
    kind: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    status: str
    error: str | None = None


class UsageLog:
    """Request and token usage log backed by SQLite.

    Args:
        db_path: Filesystem path where the SQLite database will reside.
            Parent directories are created automatically if missing.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise the usage-log database.

        Creates parent directories, opens a connection with WAL journal mode,
        and creates the ``requests`` table if it does not already exist.

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
        """Create the ``requests`` table if it is missing."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ts             TEXT NOT NULL,
                username       TEXT,
                vehicle_id     TEXT,
                kind           TEXT NOT NULL,
                model          TEXT,
                input_tokens   INTEGER DEFAULT 0,
                output_tokens  INTEGER DEFAULT 0,
                duration_ms    INTEGER DEFAULT 0,
                status         TEXT NOT NULL,
                error          TEXT,
                detail         TEXT
            )
            """
        )
        # Idempotent migration: add ``detail`` column on existing DBs.
        cursor = self._conn.execute("PRAGMA table_info(requests)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "detail" not in columns:
            self._conn.execute(
                "ALTER TABLE requests ADD COLUMN detail TEXT"
            )
        self._conn.commit()

    def record(
        self,
        username: str,
        kind: str,
        *,
        vehicle_id: str | None = None,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_ms: int = 0,
        status: str = "ok",
        error: str | None = None,
        detail: dict | None = None,
    ) -> None:
        """Log a single request event.

        Args:
            username: Operator username.
            kind: Request category string (e.g. "chat", "ticket_submit").
            vehicle_id: Optional vehicle identifier.
            model: Optional model name used for the request.
            input_tokens: Number of input tokens consumed. Defaults to 0.
            output_tokens: Number of output tokens produced. Defaults to 0.
            duration_ms: Wall-clock duration in milliseconds. Defaults to 0.
            status: "ok" or "error". Defaults to "ok".
            error: Optional error message when *status* is "error".
            detail: Optional structured detail dict; stored as JSON text.
        """
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "username": username,
            "vehicle_id": vehicle_id,
            "kind": kind,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_ms": duration_ms,
            "status": status,
            "error": error,
            "detail": (
                json.dumps(detail, ensure_ascii=False)
                if detail is not None
                else None
            ),
        }

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO requests (ts, username, vehicle_id, kind, model,
                                      input_tokens, output_tokens, duration_ms,
                                      status, error, detail)
                VALUES (:ts, :username, :vehicle_id, :kind, :model,
                        :input_tokens, :output_tokens, :duration_ms,
                        :status, :error, :detail)
                """,
                row,
            )
            self._conn.commit()

    def get_detail(self, row_id: int) -> dict | None:
        """Return the detail dict for a given request row.

        Args:
            row_id: Primary key of the request row.

        Returns:
            Parsed JSON dict, or ``None`` when the row does not exist,
            the column is NULL/empty, or the value is invalid JSON.
        """
        cursor = self._conn.execute(
            "SELECT detail FROM requests WHERE id = ?", (row_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        raw = row["detail"]
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None

    def totals(self) -> UsageTotals:
        """Compute aggregate usage statistics.

        Returns:
            :class:`UsageTotals` with counts and token sums.
        """
        cursor = self._conn.execute(
            """
            SELECT
                COUNT(*) AS requests_total,
                SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS requests_error,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens
            FROM requests
            """
        )
        row = cursor.fetchone()
        return UsageTotals(
            requests_total=row["requests_total"],
            requests_error=row["requests_error"] or 0,
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
        )

    def recent(self, limit: int = 50) -> list[UsageRow]:
        """Return the most recent request log entries.

        Args:
            limit: Maximum number of rows to return. Defaults to 50.

        Returns:
            List of :class:`UsageRow` sorted by ``ts`` descending (newest first).
        """
        cursor = self._conn.execute(
            """
            SELECT id, ts, username, vehicle_id, kind, model,
                   input_tokens, output_tokens, duration_ms, status, error
            FROM requests
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows: list[UsageRow] = []
        for r in cursor.fetchall():
            rows.append(
                UsageRow(
                    id=r["id"],
                    ts=r["ts"],
                    username=r["username"],
                    vehicle_id=r["vehicle_id"],
                    kind=r["kind"],
                    model=r["model"],
                    input_tokens=r["input_tokens"],
                    output_tokens=r["output_tokens"],
                    duration_ms=r["duration_ms"],
                    status=r["status"],
                    error=r["error"],
                )
            )
        return rows
