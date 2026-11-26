'''
File:   test_fleet.py
Brief:  Unit tests for FleetStore — listing, filtering, grouping, sessions,
        priority list and fault-code lookup against the real committed data.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

import pytest

from mechanic.errors import FleetError
from mechanic.services.fleet import FleetStore

# ---------------------------------------------------------------------------
# 1. Full fleet listing
# ---------------------------------------------------------------------------


def test_list_returns_full_fleet(fleet: FleetStore) -> None:
    """list_vehicles() with no filters returns all 50 vehicle summaries."""
    result = fleet.list_vehicles()
    assert len(result) == 50


# ---------------------------------------------------------------------------
# 2. Substring search by plate and garage prefix
# ---------------------------------------------------------------------------


def test_search_by_plate_and_garage(fleet: FleetStore) -> None:
    """Case-insensitive substring match on vehicle_id and garage_no."""
    # Exact plate match — should return exactly one result.
    plate_results = fleet.list_vehicles(query="M333YK47")
    assert len(plate_results) == 1
    assert plate_results[0].vehicle_id == "M333YK47"

    # Garage prefix "Г-1" — all returned vehicles must start with "Г-1".
    garage_results = fleet.list_vehicles(query="Г-1")
    for summary in garage_results:
        assert summary.garage_no.startswith("Г-1")


# ---------------------------------------------------------------------------
# 3. Group filter and stats invariant
# ---------------------------------------------------------------------------


def test_group_filter_and_stats_sum(fleet: FleetStore) -> None:
    """Fleet stats totals match the sum of group counts; anomaly latest → quarantine."""
    stats = fleet.fleet_stats()
    assert stats.total == 50
    assert stats.total == stats.normal + stats.attention + stats.quarantine

    # Every vehicle whose latest session status is "anomaly" must be in
    # the quarantine group. Pick one such vehicle from the store and verify.
    for vehicle in fleet._vehicles.values():
        sessions = vehicle.sessions
        if not sessions:
            continue
        latest = sessions[-1]
        if latest.status == "anomaly":
            summaries = fleet.list_vehicles()
            matching = [s for s in summaries if s.vehicle_id == vehicle.vehicle_id]
            assert len(matching) == 1, (
                f"Expected exactly one summary for {vehicle.vehicle_id}"
            )
            assert matching[0].group == "quarantine", (
                f"Vehicle {vehicle.vehicle_id} latest status is 'anomaly' "
                f"but group is '{matching[0].group}'"
            )


# ---------------------------------------------------------------------------
# 4. Error cases: unknown vehicle / wrong session
# ---------------------------------------------------------------------------


def test_get_vehicle_unknown_raises(fleet: FleetStore) -> None:
    """get_vehicle() raises FleetError for an unknown vehicle_id."""
    with pytest.raises(FleetError, match="not found"):
        fleet.get_vehicle("NOPE999")


def test_get_session_wrong_vehicle_raises(fleet: FleetStore) -> None:
    """get_session() raises FleetError when session belongs to a different vehicle."""
    # S-0003 belongs to P456AT178, not M333YK47.
    with pytest.raises(FleetError, match="not found"):
        fleet.get_session("M333YK47", "S-0003")


# ---------------------------------------------------------------------------
# 5. Sessions newest-first for a known vehicle
# ---------------------------------------------------------------------------


def test_sessions_desc_newest_first(fleet: FleetStore) -> None:
    """sessions_desc() returns the most recent session first."""
    sessions = fleet.sessions_desc("P456AT178")
    assert len(sessions) == 3
    assert sessions[0].session_id == "S-0003"


# ---------------------------------------------------------------------------
# 6. Priority vehicles — quarantine only, score descending
# ---------------------------------------------------------------------------


def test_priority_vehicles_sorted_desc(fleet: FleetStore) -> None:
    """priority_vehicles() returns quarantine vehicles sorted by score desc."""
    priority = fleet.priority_vehicles()

    # All must be in the quarantine group.
    for summary in priority:
        assert summary.group == "quarantine"

    # Scores must be non-increasing (None values go last).
    scores: list[float | None] = [s.latest_anomaly_score for s in priority]
    prev: float | None = None
    for score in scores:
        if prev is not None and score is not None:
            assert score <= prev, (
                f"Scores must be non-increasing; found {score} after {prev}"
            )
        if score is not None:
            prev = score


# ---------------------------------------------------------------------------
# 7. Fault-code lookup
# ---------------------------------------------------------------------------


def test_fault_title_lookup(fleet: FleetStore) -> None:
    """Return correct title for known codes and raises FleetError for unknown."""
    assert fleet.fault_title("F08") == "Дизельная топливоподача"

    with pytest.raises(FleetError, match="Unknown fault code 'F99'"):
        fleet.fault_title("F99")
