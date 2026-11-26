"""
File:   test_usage.py
Brief:  Tests for UsageLog — request/token log for the admin dashboard.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
"""

from __future__ import annotations

import pytest

from mechanic.services.usage import UsageLog


class TestUsageLogRecordAndTotals:
    """Test record() and totals() methods."""

    def test_totals_accumulate_ok_and_error(self, tmp_path: pytest.TempPath) -> None:
        """totals() correctly sums ok/error requests and token counts."""
        log = UsageLog(tmp_path / "usage.db")

        # Record several requests with mixed statuses
        log.record("alice", "chat", model="gpt-4", input_tokens=10, output_tokens=20)
        log.record("bob", "chat", model="gpt-4", input_tokens=5, output_tokens=10)
        log.record("alice", "ticket_submit", vehicle_id="M333YK47")
        log.record(
            "bob",
            "chat",
            status="error",
            error="Rate limit exceeded",
            input_tokens=2,
            output_tokens=0,
        )

        totals = log.totals()
        assert totals.requests_total == 4
        assert totals.requests_error == 1
        assert totals.input_tokens == 17  # 10 + 5 + 0 + 2
        assert totals.output_tokens == 30  # 20 + 10 + 0 + 0

    def test_totals_empty_db(self, tmp_path: pytest.TempPath) -> None:
        """totals() returns all zeros on an empty database."""
        log = UsageLog(tmp_path / "usage.db")
        totals = log.totals()
        assert totals.requests_total == 0
        assert totals.requests_error == 0
        assert totals.input_tokens == 0
        assert totals.output_tokens == 0


class TestUsageLogRecent:
    """Test the recent() method."""

    def test_recent_limit_two(self, tmp_path: pytest.TempPath) -> None:
        """recent(limit=2) returns the two newest entries first."""
        log = UsageLog(tmp_path / "usage.db")

        # Insert 5 requests — each gets a unique id via AUTOINCREMENT
        for i in range(5):
            log.record(f"user_{i}", "chat", model="test-model")

        recent = log.recent(limit=2)
        assert len(recent) == 2
        # Newest first: user_4 and user_3
        assert recent[0].username == "user_4"
        assert recent[1].username == "user_3"

    def test_recent_newest_first_order(self, tmp_path: pytest.TempPath) -> None:
        """recent() returns entries in descending order of id (newest first)."""
        log = UsageLog(tmp_path / "usage.db")

        for i in range(10):
            log.record(f"user_{i}", "chat")

        recent = log.recent(limit=5)
        usernames = [r.username for r in recent]
        assert usernames == ["user_9", "user_8", "user_7", "user_6", "user_5"]


class TestUsageLogNoneSafe:
    """Test that vehicle_id and model None values are handled correctly."""

    def test_vehicle_id_none(self, tmp_path: pytest.TempPath) -> None:
        """record() handles vehicle_id=None without error."""
        log = UsageLog(tmp_path / "usage.db")
        log.record("user1", "chat")  # vehicle_id defaults to None

        totals = log.totals()
        assert totals.requests_total == 1

    def test_model_none(self, tmp_path: pytest.TempPath) -> None:
        """record() handles model=None without error."""
        log = UsageLog(tmp_path / "usage.db")
        log.record("user1", "chat", model=None)  # explicit None

        recent = log.recent(limit=10)
        assert len(recent) == 1
        assert recent[0].model is None

    def test_recent_with_none_fields(self, tmp_path: pytest.TempPath) -> None:
        """recent() returns UsageRow with None fields preserved."""
        log = UsageLog(tmp_path / "usage.db")
        log.record("user1", "chat", vehicle_id=None, model=None, error=None)

        recent = log.recent(limit=1)
        assert len(recent) == 1
        row = recent[0]
        assert row.vehicle_id is None
        assert row.model is None
        assert row.error is None
