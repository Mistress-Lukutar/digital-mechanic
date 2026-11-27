"""
File:   test_alerts.py
Brief:  Tests for AlertsStore — admin alert store for non-standard agent situations.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0
"""

from __future__ import annotations

import pytest

from mechanic.services.alerts import AlertRow, AlertsStore


class TestAlertsStoreAddAndRecent:
    """Test add() and recent() methods."""

    def test_add_returns_increasing_ids(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """add() returns monotonically increasing ids via AUTOINCREMENT."""
        store = AlertsStore(tmp_path / "alerts.db")

        id1 = store.add("warning_override", "first alert")
        id2 = store.add("diagnostic_mismatch", "second alert")
        id3 = store.add("missing_instructions", "third alert")

        assert id1 < id2 < id3

    def test_recent_returns_all_fields(self, tmp_path: pytest.TempPath) -> None:
        """recent() returns AlertRow with all fields populated."""
        store = AlertsStore(tmp_path / "alerts.db")

        alert_id = store.add(
            kind="warning_override",
            text="Механик confirmed warning.",
            username="ivanov",
            vehicle_id="P854BT78",
            session_id="S-0021",
            engine_model="ЯМЗ-236М2",
        )

        rows = store.recent(limit=10)
        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, AlertRow)
        assert row.id == alert_id
        assert row.kind == "warning_override"
        assert row.text == "Механик confirmed warning."
        assert row.username == "ivanov"
        assert row.vehicle_id == "P854BT78"
        assert row.session_id == "S-0021"
        assert row.engine_model == "ЯМЗ-236М2"

    def test_recent_newest_first(self, tmp_path: pytest.TempPath) -> None:
        """recent() returns entries in descending id order (newest first)."""
        store = AlertsStore(tmp_path / "alerts.db")

        for i in range(5):
            store.add("test", f"alert_{i}")

        rows = store.recent(limit=3)
        assert len(rows) == 3
        # Newest ids: 5, 4, 3
        texts = [r.text for r in rows]
        assert texts == ["alert_4", "alert_3", "alert_2"]


class TestAlertsStoreEmpty:
    """Test behaviour on an empty store."""

    def test_recent_empty_returns_list(self, tmp_path: pytest.TempPath) -> None:
        """recent() on empty store returns []."""
        store = AlertsStore(tmp_path / "alerts.db")
        assert store.recent() == []

    def test_unread_count_empty(self, tmp_path: pytest.TempPath) -> None:
        """unread_count() on empty store returns 0."""
        store = AlertsStore(tmp_path / "alerts.db")
        assert store.unread_count() == 0


class TestAlertsStoreReadMarking:
    """Test mark_read() and unread_count()."""

    def test_unread_count_counts_only_unread(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """unread_count() counts only rows with is_read=0."""
        store = AlertsStore(tmp_path / "alerts.db")

        store.add("a", "alert 1")
        store.add("b", "alert 2")
        store.add("c", "alert 3")

        assert store.unread_count() == 3

        # Mark one as read.
        ids = [r.id for r in store.recent(limit=10)]
        store.mark_read(ids[0])

        assert store.unread_count() == 2

    def test_mark_read_returns_true_and_flips_flag(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """mark_read() returns True for existing row and sets is_read=1."""
        store = AlertsStore(tmp_path / "alerts.db")

        alert_id = store.add("test", "read me")

        result = store.mark_read(alert_id)
        assert result is True

        # After marking, recent should show is_read=True.
        rows = store.recent(limit=10)
        row = [r for r in rows if r.id == alert_id][0]
        assert row.is_read is True

    def test_mark_read_second_time_returns_false(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """mark_read() on already-read row returns False."""
        store = AlertsStore(tmp_path / "alerts.db")

        alert_id = store.add("test", "already read")
        store.mark_read(alert_id)

        result = store.mark_read(alert_id)
        assert result is False

    def test_mark_read_unknown_id_returns_false(
        self, tmp_path: pytest.TempPath
    ) -> None:
        """mark_read() on non-existent id returns False."""
        store = AlertsStore(tmp_path / "alerts.db")

        result = store.mark_read(99999)
        assert result is False
