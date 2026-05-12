"""Condition-index history tracking for simulation sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import pandas as pd

from src.enums.entity_type import EntityType

if TYPE_CHECKING:
    from src.config.midas_config_data import MidasConfigData
    from src.models import Facility, Installation, System


@dataclass(frozen=True)
class ConditionIndexSnapshot:
    """A point-in-time condition-index record for one entity."""

    entity_id: str
    entity_type: EntityType
    date: date
    tick_index: int
    condition_index: float | None
    installation_id: str | None = None
    facility_id: str | None = None
    system_id: str | None = None


@dataclass
class ConditionHistoryStore:
    """Stores condition-index history generated during a simulation run."""

    snapshots: list[ConditionIndexSnapshot] = field(default_factory=list)

    def record_installation(
        self, installation: Installation, current_date: date, tick_index: int
    ) -> None:
        """Record a point-in-time installation snapshot."""
        self.snapshots.append(
            ConditionIndexSnapshot(
                entity_id=installation.id,
                entity_type=EntityType.INSTALLATION,
                date=current_date,
                tick_index=tick_index,
                condition_index=installation.condition_index,
                installation_id=installation.id,
            )
        )

    def record_facility(
        self, facility: Facility, current_date: date, tick_index: int
    ) -> None:
        """Record a point-in-time facility snapshot."""
        self.snapshots.append(
            ConditionIndexSnapshot(
                entity_id=facility.id,
                entity_type=EntityType.FACILITY,
                date=current_date,
                tick_index=tick_index,
                condition_index=facility.condition_index,
                installation_id=facility.installation_id,
                facility_id=facility.id,
            )
        )

    def record_system(
        self,
        system: System,
        installation_id: str | None,
        current_date: date,
        tick_index: int,
    ) -> None:
        """Record a point-in-time system snapshot."""
        self.snapshots.append(
            ConditionIndexSnapshot(
                entity_id=system.id,
                entity_type=EntityType.SYSTEM,
                date=current_date,
                tick_index=tick_index,
                condition_index=system.condition_index,
                installation_id=installation_id,
                facility_id=system.facility_id,
                system_id=system.id,
            )
        )

    def record_current_state(
        self,
        installation: Installation,
        facilities: list[Facility],
        systems: list[System],
        current_date: date,
        tick_index: int,
    ) -> None:
        """Record the current state of the active installation hierarchy."""
        self.record_installation(
            installation, current_date=current_date, tick_index=tick_index
        )
        for facility in facilities:
            self.record_facility(
                facility, current_date=current_date, tick_index=tick_index
            )
        for system in systems:
            self.record_system(
                system,
                installation_id=installation.id,
                current_date=current_date,
                tick_index=tick_index,
            )

    def latest_snapshot(self, entity_id: str) -> ConditionIndexSnapshot | None:
        """Return the latest snapshot for a specific entity."""
        for snapshot in reversed(self.snapshots):
            if snapshot.entity_id == entity_id:
                return snapshot
        return None


class ConditionHistoryExportAdapter:
    """Convert runtime history into table-like time-series outputs."""

    def __init__(
        self,
        history: ConditionHistoryStore,
        config_data: "MidasConfigData | None" = None,
    ) -> None:
        """Initialize the export adapter (reference data resolves from the singleton)."""
        from src.config.midas_config_data import MidasConfigData

        self.history = history
        self.config_data = config_data or MidasConfigData()

    def create_tables(
        self,
        installation: Installation,
        facilities: list[Facility],
        systems: list[System],
    ) -> dict[str, pd.DataFrame | None]:
        """Create installation, facility, and system history tables."""
        return {
            "installation_time_series": self._build_installation_history(installation),
            "facility_time_series": self._build_facility_history(facilities),
            "system_time_series": self._build_system_history(systems),
        }

    def _build_installation_history(
        self, installation: Installation
    ) -> pd.DataFrame | None:
        """Build the installation history table."""
        rows = [
            {
                "entity_id": snapshot.entity_id,
                "entity_type": snapshot.entity_type.value,
                "installation_id": snapshot.installation_id,
                "title": installation.title,
                "date": snapshot.date.isoformat(),
                "tick_index": snapshot.tick_index,
                "condition_index": snapshot.condition_index,
            }
            for snapshot in self.history.snapshots
            if snapshot.entity_type == EntityType.INSTALLATION
        ]
        return pd.DataFrame(rows) if rows else None

    def _build_facility_history(
        self, facilities: list[Facility]
    ) -> pd.DataFrame | None:
        """Build the facility history table."""
        facilities_by_id = {facility.id: facility for facility in facilities}
        rows = []
        for snapshot in self.history.snapshots:
            if snapshot.entity_type != EntityType.FACILITY:
                continue
            facility = facilities_by_id.get(snapshot.entity_id)
            if facility is None:
                continue
            facility_type = self.config_data.get_facility_type(
                facility.facility_type_key or 0
            )
            rows.append(
                {
                    "entity_id": snapshot.entity_id,
                    "entity_type": snapshot.entity_type.value,
                    "installation_id": snapshot.installation_id,
                    "facility_id": snapshot.facility_id,
                    "facility_type_key": facility.facility_type_key,
                    "title": facility_type.title if facility_type else "",
                    "date": snapshot.date.isoformat(),
                    "tick_index": snapshot.tick_index,
                    "condition_index": snapshot.condition_index,
                }
            )
        return pd.DataFrame(rows) if rows else None

    def _build_system_history(self, systems: list[System]) -> pd.DataFrame | None:
        """Build the system history table."""
        systems_by_id = {system.id: system for system in systems}
        rows = []
        for snapshot in self.history.snapshots:
            if snapshot.entity_type != EntityType.SYSTEM:
                continue
            system = systems_by_id.get(snapshot.entity_id)
            if system is None:
                continue
            system_type = self.config_data.get_system_type(system.system_type_key or 0)
            rows.append(
                {
                    "entity_id": snapshot.entity_id,
                    "entity_type": snapshot.entity_type.value,
                    "installation_id": snapshot.installation_id,
                    "facility_id": snapshot.facility_id,
                    "system_id": snapshot.system_id,
                    "system_type_key": system.system_type_key,
                    "title": system_type.title if system_type else "",
                    "date": snapshot.date.isoformat(),
                    "tick_index": snapshot.tick_index,
                    "condition_index": snapshot.condition_index,
                }
            )
        return pd.DataFrame(rows) if rows else None
