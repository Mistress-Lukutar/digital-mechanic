'''
File:   fleet.py
Brief:  Fleet store: loads vehicles.json + fault_types.json, provides
        vehicle lookup, session queries, grouping and priority lists.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter
from shared.models import (
    DiagnosticStatus,
    FaultType,
    FleetFile,
    SessionCheck,
    SignalQuality,
    Vehicle,
)

from mechanic.errors import FleetError

# ---------------------------------------------------------------------------
# Pydantic summary model used by list_vehicles / fleet_stats / priority.
# ---------------------------------------------------------------------------


class VehicleSummary(BaseModel):
    """Compact view of a single vehicle for listing and prioritisation."""

    vehicle_id: str = Field(min_length=1)
    garage_no: str
    make: str
    model: str | None = None
    vehicle_type: str
    engine_model: str
    fuel: str
    latest_status: DiagnosticStatus | None = None
    latest_checked_at: str | None = None
    latest_anomaly_type: str | None = None
    latest_anomaly_title: str | None = None
    latest_anomaly_score: float | None = None
    anomaly_count: int = 0
    check_count: int = 0
    group: Literal["normal", "attention", "quarantine"] = "normal"


class FleetStats(BaseModel):
    """Aggregate counts for the entire fleet."""

    total: int
    normal: int
    attention: int
    quarantine: int


# ---------------------------------------------------------------------------
# Internal helper: parse a checked_at ISO string into a datetime, or return
# the raw string as fallback so sorting still works deterministically.
# ---------------------------------------------------------------------------


def _parse_checked_at(raw: str | None) -> object:
    """Return a datetime for sorting; falls back to the raw string."""
    if raw is None:
        return ""
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return raw


# ---------------------------------------------------------------------------
# Grouping rule — applied to the *latest* session of each vehicle.
#
#   status "anomaly"          → "quarantine"
#   status "check_failed"     → "attention"
#   status "normal" + signal   → "attention"
#                                  quality "warning"
#   otherwise                 → "normal"
# ---------------------------------------------------------------------------


def _determine_group(
    latest_status: DiagnosticStatus | None,
    latest_signal: SignalQuality | None,
) -> Literal["normal", "attention", "quarantine"]:
    """Assign a group based on the latest session's status and signal quality."""
    if latest_status == "anomaly":
        return "quarantine"
    if latest_status == "check_failed":
        return "attention"
    if latest_status == "normal" and latest_signal == "warning":
        return "attention"
    return "normal"


# ---------------------------------------------------------------------------
# FleetStore — the main public API over vehicle data.
# ---------------------------------------------------------------------------


class FleetStore:
    """In-memory fleet backed by vehicles.json + fault_types.json."""

    def __init__(self, data_dir: Path) -> None:
        self._vehicles: dict[str, Vehicle] = {}
        self._faults: dict[str, str] = {}  # code → title

        # Load vehicles file.
        vehicles_path = data_dir / "vehicles.json"
        if not vehicles_path.is_file():
            raise FleetError(f"Fleet file not found: {vehicles_path}")
        try:
            json_text = vehicles_path.read_text(encoding="utf-8")
            fleet_file = FleetFile.model_validate_json(json_text)
        except Exception as exc:  # noqa: BLE001
            raise FleetError(f"Malformed vehicles.json: {exc}") from exc

        for vehicle in fleet_file.vehicles:
            self._sort_sessions(vehicle)
            self._vehicles[vehicle.vehicle_id] = vehicle

        # Load fault types catalog.
        faults_path = data_dir / "fault_types.json"
        if not faults_path.is_file():
            raise FleetError(f"Fault types file not found: {faults_path}")
        try:
            adapter = TypeAdapter(list[FaultType])
            fault_list = adapter.validate_json(faults_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise FleetError(f"Malformed fault_types.json: {exc}") from exc

        for ft in fault_list:
            self._faults[ft.code] = ft.title

    # -- internal helpers -----------------------------------------------------

    @staticmethod
    def _sort_sessions(vehicle: Vehicle) -> None:
        """Sort *vehicle.sessions* ascending by checked_at (datetime or string)."""
        vehicle.sessions.sort(key=lambda s: _parse_checked_at(s.checked_at))

    def _summary(self, vehicle: Vehicle) -> VehicleSummary:
        """Build a VehicleSummary from a Vehicle record."""
        sessions = vehicle.sessions
        check_count = len(sessions)

        # Count anomaly sessions (all sessions with status "anomaly").
        anomaly_count = sum(1 for s in sessions if s.status == "anomaly")

        latest: SessionCheck | None = sessions[-1] if sessions else None

        if latest is not None:
            group = _determine_group(latest.status, latest.signal_quality)
            latest_status = latest.status
            latest_checked_at = latest.checked_at
            latest_anomaly_type = latest.anomaly_type
            latest_anomaly_title = latest.anomaly_title
            latest_anomaly_score = latest.anomaly_score
        else:
            group = "normal"
            latest_status = None
            latest_checked_at = None
            latest_anomaly_type = None
            latest_anomaly_title = None
            latest_anomaly_score = None

        return VehicleSummary(
            vehicle_id=vehicle.vehicle_id,
            garage_no=vehicle.garage_no,
            make=vehicle.make,
            model=vehicle.model,
            vehicle_type=vehicle.vehicle_type,
            engine_model=vehicle.engine_model,
            fuel=vehicle.fuel,
            latest_status=latest_status,
            latest_checked_at=latest_checked_at,
            latest_anomaly_type=latest_anomaly_type,
            latest_anomaly_title=latest_anomaly_title,
            latest_anomaly_score=latest_anomaly_score,
            anomaly_count=anomaly_count,
            check_count=check_count,
            group=group,
        )

    # -- public API -----------------------------------------------------------

    def list_vehicles(
        self,
        query: str | None = None,
        group: Literal["normal", "attention", "quarantine"] | None = None,
    ) -> list[VehicleSummary]:
        """Return summaries optionally filtered by *query* and/or *group*.

        Args:
            query: Case-insensitive substring matched against vehicle_id,
                garage_no, make, model, engine_model (model is None-safe).
            group: If given, only return vehicles in this group.

        Returns:
            A list of VehicleSummary objects sorted by garage_no.
        """
        summaries = [self._summary(v) for v in self._vehicles.values()]

        if query is not None:
            q_lower = query.lower()

            def _matches(s: VehicleSummary) -> bool:
                return (
                    q_lower in s.vehicle_id.lower()
                    or q_lower in s.garage_no.lower()
                    or q_lower in s.make.lower()
                    or (s.model is not None and q_lower in s.model.lower())
                    or q_lower in s.engine_model.lower()
                )

            summaries = [s for s in summaries if _matches(s)]

        if group is not None:
            summaries = [s for s in summaries if s.group == group]

        summaries.sort(key=lambda s: s.garage_no)
        return summaries

    def get_vehicle(self, vehicle_id: str) -> Vehicle:
        """Return the full Vehicle record.

        Raises:
            FleetError: If *vehicle_id* is not found.
        """
        vehicle = self._vehicles.get(vehicle_id)
        if vehicle is None:
            raise FleetError(f"Vehicle '{vehicle_id}' not found in fleet")
        return vehicle

    def get_session(self, vehicle_id: str, session_id: str) -> SessionCheck:
        """Return a specific session within a vehicle.

        Raises:
            FleetError: If the vehicle or session is not found (distinct messages).
        """
        vehicle = self._vehicles.get(vehicle_id)
        if vehicle is None:
            raise FleetError(f"Vehicle '{vehicle_id}' not found in fleet")

        for session in vehicle.sessions:
            if session.session_id == session_id:
                return session

        raise FleetError(
            f"Session '{session_id}' not found in vehicle '{vehicle_id}'"
        )

    def latest_session(self, vehicle_id: str) -> SessionCheck | None:
        """Return the most recent session for a vehicle, or None."""
        vehicle = self._vehicles.get(vehicle_id)
        if vehicle is None:
            return None
        return vehicle.sessions[-1] if vehicle.sessions else None

    def sessions_desc(self, vehicle_id: str) -> list[SessionCheck]:
        """Return all sessions for a vehicle, newest first.

        Raises:
            FleetError: If the vehicle is not found.
        """
        vehicle = self._vehicles.get(vehicle_id)
        if vehicle is None:
            raise FleetError(f"Vehicle '{vehicle_id}' not found in fleet")
        return list(reversed(vehicle.sessions))

    def fault_title(self, code: str) -> str:
        """Return the human-readable title for a fault-code.

        Raises:
            FleetError: If *code* is unknown.
        """
        title = self._faults.get(code)
        if title is None:
            raise FleetError(f"Unknown fault code '{code}'")
        return title

    def fleet_stats(self) -> FleetStats:
        """Return aggregate counts (total == normal + attention + quarantine)."""
        summaries = [self._summary(v) for v in self._vehicles.values()]
        total = len(summaries)
        normal = sum(1 for s in summaries if s.group == "normal")
        attention = sum(1 for s in summaries if s.group == "attention")
        quarantine = sum(1 for s in summaries if s.group == "quarantine")
        return FleetStats(
            total=total,
            normal=normal,
            attention=attention,
            quarantine=quarantine,
        )

    def priority_vehicles(self) -> list[VehicleSummary]:
        """Return vehicles in the *quarantine* group.

        Sorted by latest_anomaly_score descending (None scores last),
        then by garage_no ascending as tie-breaker.
        """
        quarantine = [s for s in self.list_vehicles(group="quarantine")]

        def _sort_key(s: VehicleSummary) -> tuple:
            # Negate the score for descending order; vehicles without a
            # score get +inf so they sort last.
            raw = s.latest_anomaly_score
            score = -(raw if raw is not None else float("-inf"))
            return (score, s.garage_no)

        quarantine.sort(key=_sort_key)
        return quarantine
