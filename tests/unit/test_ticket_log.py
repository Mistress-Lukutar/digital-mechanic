"""
File:   test_ticket_log.py
Brief:  Tests for TicketLog — local per-vehicle ticket history.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shared.models import (
    Reference,
    TicketPayload,
    TicketResult,
)

from mechanic.services.ticket_log import TicketLog


def _make_payload(
    vehicle_id: str = "M333YK47",
    session_id: str = "S-0005",
    anomaly_type: str = "F08",
) -> TicketPayload:
    """Build a realistic TicketPayload for testing."""
    return TicketPayload(
        vehicle_id=vehicle_id,
        session_id=session_id,
        anomaly_type=anomaly_type,
        conclusion="Дизельная топливоподача — аномалия",
        urgency="high",
        operations=["Замена форсунок", "Проводка"],
        spare_parts=["Форсунка 3"],
        references=[Reference(manual="236.01.01 РК", pdf_page=42)],
    )


def _make_result(ticket_id: str = "TKT-0001") -> TicketResult:
    """Build a minimal TicketResult."""
    return TicketResult(ticket_id=ticket_id, status="created")


class TestTicketLogAdd:
    """Test the add() method of TicketLog."""

    def test_add_returns_ticket_record(self, tmp_path: pytest.TempPath) -> None:
        """add() returns a TicketRecord with correct fields."""
        log = TicketLog(tmp_path / "tickets.db")
        payload = _make_payload()
        result = _make_result("TKT-0001")

        record = log.add(result, payload, "operator")

        assert record.ticket_id == "TKT-0001"
        assert isinstance(record.created_at, datetime)
        assert record.payload.vehicle_id == payload.vehicle_id
        # Verify created_at has timezone info (UTC)
        assert record.created_at.tzinfo is not None


class TestTicketLogListByVehicle:
    """Test list_by_vehicle() — newest first, full round-trip."""

    def test_list_newest_first(self, tmp_path: pytest.TempPath) -> None:
        """list_by_vehicle returns records sorted newest first."""
        log = TicketLog(tmp_path / "tickets.db")
        payload = _make_payload(vehicle_id="M333YK47", session_id="S-0005")

        t1 = datetime(2026, 11, 20, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 11, 21, 14, 0, 0, tzinfo=UTC)

        log.add(_make_result("TKT-0001"), payload, "op", created_at=t1)
        log.add(_make_result("TKT-0002"), payload, "op", created_at=t2)

        records = log.list_by_vehicle("M333YK47")
        assert len(records) == 2
        assert records[0].ticket_id == "TKT-0002"
        assert records[1].ticket_id == "TKT-0001"

    def test_payload_round_trip(self, tmp_path: pytest.TempPath) -> None:
        """Stored payload round-trips correctly through SQLite."""
        log = TicketLog(tmp_path / "tickets.db")
        payload = _make_payload(
            vehicle_id="M333YK47", session_id="S-0005", anomaly_type="F08"
        )
        result = _make_result("TKT-0010")

        log.add(result, payload, "operator")

        records = log.list_by_vehicle("M333YK47")
        assert len(records) == 1
        stored = records[0]
        assert stored.payload.vehicle_id == "M333YK47"
        assert stored.payload.session_id == "S-0005"
        assert stored.payload.anomaly_type == "F08"
        assert stored.payload.conclusion == "Дизельная топливоподача — аномалия"
        assert stored.payload.urgency == "high"
        assert stored.payload.operations == ["Замена форсунок", "Проводка"]


class TestTicketLogCount:
    """Test the count() method."""

    def test_count_starts_at_zero(self, tmp_path: pytest.TempPath) -> None:
        """count() returns 0 on a fresh database."""
        log = TicketLog(tmp_path / "tickets.db")
        assert log.count() == 0

    def test_count_increments(self, tmp_path: pytest.TempPath) -> None:
        """count() reflects every insert."""
        log = TicketLog(tmp_path / "tickets.db")
        payload = _make_payload()
        log.add(_make_result("TKT-1"), payload, "op")
        log.add(_make_result("TKT-2"), payload, "op")

        assert log.count() == 2


class TestTicketLogVehicleIsolation:
    """Test that records of different vehicles do not mix."""

    def test_different_vehicles_do_not_mix(self, tmp_path: pytest.TempPath) -> None:
        """list_by_vehicle returns only records for the requested vehicle."""
        log = TicketLog(tmp_path / "tickets.db")

        payload_a = _make_payload(vehicle_id="AAA001", session_id="S-001")
        payload_b = _make_payload(vehicle_id="BBB002", session_id="S-002")

        log.add(_make_result("TKT-A"), payload_a, "op")
        log.add(_make_result("TKT-B"), payload_b, "op")

        a_records = log.list_by_vehicle("AAA001")
        b_records = log.list_by_vehicle("BBB002")

        assert len(a_records) == 1
        assert a_records[0].payload.vehicle_id == "AAA001"
        assert len(b_records) == 1
        assert b_records[0].payload.vehicle_id == "BBB002"


class TestTicketRecordCreatedAt:
    """Test that TicketRecord.created_at is a datetime with timezone."""

    def test_created_at_is_datetime(self, tmp_path: pytest.TempPath) -> None:
        """created_at must be a datetime instance with tzinfo."""
        log = TicketLog(tmp_path / "tickets.db")
        payload = _make_payload()
        record = log.add(_make_result("TKT-Z"), payload, "op")

        assert isinstance(record.created_at, datetime)
        assert record.created_at.tzinfo is not None

    def test_list_created_at_is_datetime(self, tmp_path: pytest.TempPath) -> None:
        """Records returned by list_by_vehicle also have timezone-aware created_at."""
        log = TicketLog(tmp_path / "tickets.db")
        payload = _make_payload()
        log.add(_make_result("TKT-L"), payload, "op")

        records = log.list_by_vehicle("M333YK47")
        assert len(records) == 1
        assert isinstance(records[0].created_at, datetime)
        assert records[0].created_at.tzinfo is not None
