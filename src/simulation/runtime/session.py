"""Simulation session state, aggregation, and pause-policy helpers."""

from __future__ import annotations

import copy
import warnings
from dataclasses import dataclass, field
from datetime import date

from src.config.midas_settings import MidasSettings
from src.enums.entity_type import EntityType
from src.enums.work_order import WO_Status
from src.models import DataStore, Facility, Installation, System, WorkOrder
from src.simulation.modules.base import ModuleEvent, SimulationModuleBase
from src.simulation.runtime.clock import SimulationClock, TickSize
from src.simulation.runtime.history import (
    ConditionHistoryExportAdapter,
    ConditionHistoryStore,
)

_OPEN_WORK_ORDER_STATUSES = {
    WO_Status.SUBMITTED,
    WO_Status.APPROVED,
    WO_Status.IN_PROGRESS,
}
_PLAYBACK_DELAY_PRESETS = [1.0, 0.5, 0.25, 0.1, 0.05]


@dataclass(frozen=True)
class EntityRuntimeState:
    """Operational summary for one entity at the current tick."""

    entity_id: str
    entity_type: EntityType
    condition_index: float | None
    degraded: bool
    inoperable: bool
    mission_blocked: bool
    open_work_orders: int
    mission_impacting_open_work_orders: int
    child_degraded_count: int = 0
    child_inoperable_count: int = 0

    @property
    def status_label(self) -> str:
        """Return a concise status label for dashboard rendering."""
        if self.mission_blocked:
            return "MISSION BLOCKED"
        if self.inoperable:
            return "INOPERABLE"
        if self.degraded:
            return "DEGRADED"
        return "OPERATIONAL"


class CriticalStatePausePolicy(SimulationModuleBase):
    """Pause the simulation when an entity newly becomes critical."""

    def apply(self, session: SimulationSession) -> list[ModuleEvent]:
        """Return pause events for newly critical entities."""
        events: list[ModuleEvent] = []
        current_critical_entities: set[tuple[EntityType, str]] = set()

        for runtime_state in session.iter_runtime_states():
            is_critical = runtime_state.inoperable or runtime_state.mission_blocked
            if not is_critical:
                continue
            key = (runtime_state.entity_type, runtime_state.entity_id)
            current_critical_entities.add(key)
            if session.clock.tick_index == 0 or key in session.critical_entities:
                continue
            events.append(
                ModuleEvent(
                    code="critical_entity_reached",
                    message=(
                        f"{runtime_state.entity_type.value.title()} {runtime_state.entity_id} reached "
                        f"a critical state ({runtime_state.status_label.lower()})."
                    ),
                    entity_id=runtime_state.entity_id,
                    entity_type=runtime_state.entity_type,
                    should_pause=True,
                )
            )

        session.critical_entities = current_critical_entities
        return events


@dataclass
class SimulationSession:
    """Holds all mutable runtime state for an active simulation."""

    result: DataStore
    clock: SimulationClock
    settings: MidasSettings = field(default_factory=MidasSettings)
    history: ConditionHistoryStore = field(default_factory=ConditionHistoryStore)
    modules: list[SimulationModuleBase] = field(default_factory=list)
    pause_policies: list[SimulationModuleBase] = field(
        default_factory=lambda: [CriticalStatePausePolicy()]
    )
    paused: bool = True
    playback_delay_seconds: float = 0.25
    selected_facility_id: str | None = None
    selected_system_id: str | None = None
    stop_reason: str | None = None
    critical_entities: set[tuple[EntityType, str]] = field(
        default_factory=set, repr=False
    )
    facilities_by_id: dict[str, Facility] = field(
        default_factory=dict, init=False, repr=False
    )
    systems_by_id: dict[str, System] = field(
        default_factory=dict, init=False, repr=False
    )
    systems_by_facility: dict[str, list[System]] = field(
        default_factory=dict, init=False, repr=False
    )
    work_orders_by_system: dict[str, list[WorkOrder]] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Validate and initialize runtime state."""
        if len(self.result.installations) != 1:
            raise ValueError(
                "SimulationSession requires exactly one active installation"
            )
        self.rebuild_indexes()
        self.sync_age_caches()
        self.recalculate_aggregates()
        self.history.record_current_state(
            installation=self.installation,
            facilities=self.facilities,
            systems=self.systems,
            current_date=self.current_date,
            tick_index=self.clock.tick_index,
        )
        self._run_pause_policies()

    @property
    def data(self) -> DataStore:
        """Active installation dataset (same object as ``result``; preferred name)."""
        return self.result

    @classmethod
    def from_data_store(
        cls,
        data: DataStore,
        settings: MidasSettings | None = None,
        installation_id: str | None = None,
        start_date: date | None = None,
        modules: list[SimulationModuleBase] | None = None,
        pause_policies: list[SimulationModuleBase] | None = None,
    ) -> SimulationSession:
        """Create a session from a loaded or generated :class:`DataStore`."""
        selected = cls.select_installation_result(data, installation_id=installation_id)
        return cls(
            result=selected,
            settings=settings or MidasSettings(),
            clock=SimulationClock(current_date=start_date or date.today()),
            modules=modules or [],
            pause_policies=pause_policies or [CriticalStatePausePolicy()],
        )

    @classmethod
    def from_generation_result(
        cls,
        result: DataStore,
        settings: MidasSettings | None = None,
        installation_id: str | None = None,
        start_date: date | None = None,
        modules: list[SimulationModuleBase] | None = None,
        pause_policies: list[SimulationModuleBase] | None = None,
    ) -> SimulationSession:
        """Deprecated alias for :meth:`from_data_store`."""
        warnings.warn(
            "SimulationSession.from_generation_result is deprecated; use from_data_store",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.from_data_store(
            result,
            settings=settings,
            installation_id=installation_id,
            start_date=start_date,
            modules=modules,
            pause_policies=pause_policies,
        )

    @staticmethod
    def select_installation_result(
        result: DataStore,
        installation_id: str | None = None,
    ) -> DataStore:
        """Return a deep-copied single-installation subset of a result set."""
        if not result.installations:
            raise ValueError("No installations are available to simulate")
        if installation_id is None and len(result.installations) > 1:
            raise ValueError(
                "installation_id is required when multiple installations are available"
            )

        selected_installation = None
        if installation_id is None:
            selected_installation = result.installations[0]
        else:
            for installation in result.installations:
                if installation.id == installation_id:
                    selected_installation = installation
                    break
        if selected_installation is None:
            raise ValueError(f"Unknown installation_id: {installation_id}")

        facility_ids = {
            facility.id
            for facility in result.facilities
            if facility.installation_id == selected_installation.id
        }
        facilities = [
            facility for facility in result.facilities if facility.id in facility_ids
        ]
        systems = [
            system for system in result.systems if system.facility_id in facility_ids
        ]
        system_ids = {system.id for system in systems}
        work_orders = [
            work_order
            for work_order in result.work_orders
            if work_order.installation_id == selected_installation.id
            or work_order.system_id in system_ids
        ]
        if not work_orders:
            for system in systems:
                work_orders.extend(system.work_orders)

        return copy.deepcopy(
            DataStore(
                installations=[selected_installation],
                facilities=facilities,
                systems=systems,
                work_orders=work_orders,
            )
        )

    @property
    def installation(self) -> Installation:
        """Return the active installation."""
        return self.result.installations[0]

    @property
    def facilities(self) -> list[Facility]:
        """Return the facilities for the active installation."""
        return self.result.facilities

    @property
    def systems(self) -> list[System]:
        """Return the systems for the active installation."""
        return self.result.systems

    @property
    def work_orders(self) -> list[WorkOrder]:
        """Return the work orders for the active installation."""
        return self.result.work_orders

    @property
    def current_date(self) -> date:
        """Return the current simulated date."""
        return self.clock.current_date

    @property
    def playback_label(self) -> str:
        """Return a human-readable playback delay label."""
        return f"{self.playback_delay_seconds:.2f}s/tick"

    def rebuild_indexes(self) -> None:
        """Rebuild lookup maps for facilities, systems, and work orders."""
        self.facilities_by_id = {facility.id: facility for facility in self.facilities}
        self.systems_by_id = {system.id: system for system in self.systems}
        self.systems_by_facility = {}
        self.work_orders_by_system = {}

        for system in self.systems:
            self.systems_by_facility.setdefault(system.facility_id or "", []).append(
                system
            )
        for work_order in self.work_orders:
            if not work_order.system_id:
                continue
            self.work_orders_by_system.setdefault(work_order.system_id, []).append(
                work_order
            )

        for system in self.systems:
            system.work_orders = list(self.work_orders_by_system.get(system.id, []))

    def sync_age_caches(self) -> None:
        """Update cached age values to match the simulated date."""
        for facility in self.facilities:
            facility._age_months = _calculate_age_months(
                facility.year_constructed, self.current_date
            )
        for system in self.systems:
            system._age_months = _calculate_age_months(
                system.year_constructed, self.current_date
            )

    def recalculate_aggregates(self) -> None:
        """Recompute facility and installation aggregate condition indices."""
        for facility in self.facilities:
            child_systems = self.systems_by_facility.get(facility.id, [])
            facility.condition_index = _average_condition_index(child_systems)
        self.installation.condition_index = _average_condition_index(self.facilities)

    def set_selected_facility(self, facility_id: str | None) -> None:
        """Set the focused facility and clear invalid system focus."""
        if facility_id is not None and facility_id not in self.facilities_by_id:
            raise ValueError(f"Unknown facility_id: {facility_id}")
        self.selected_facility_id = facility_id
        if self.selected_system_id is None:
            return
        selected_system = self.systems_by_id.get(self.selected_system_id)
        if selected_system is None or selected_system.facility_id != facility_id:
            self.selected_system_id = None

    def set_selected_system(self, system_id: str | None) -> None:
        """Set the focused system and align facility focus if needed."""
        if system_id is not None and system_id not in self.systems_by_id:
            raise ValueError(f"Unknown system_id: {system_id}")
        self.selected_system_id = system_id
        if system_id is None:
            return
        system = self.systems_by_id[system_id]
        self.selected_facility_id = system.facility_id

    def clear_selection(self) -> None:
        """Clear focused facility and system selections."""
        self.selected_facility_id = None
        self.selected_system_id = None

    def cycle_tick_size(self) -> TickSize:
        """Cycle through common tick-size presets."""
        return self.clock.cycle_tick_size()

    def increase_speed(self) -> float:
        """Increase playback speed by reducing tick delay."""
        return self._shift_playback_delay(direction=1)

    def decrease_speed(self) -> float:
        """Decrease playback speed by increasing tick delay."""
        return self._shift_playback_delay(direction=-1)

    def resume(self) -> None:
        """Resume playback."""
        self.paused = False
        self.stop_reason = None

    def pause(self, reason: str | None = None) -> None:
        """Pause playback with an optional reason."""
        self.paused = True
        self.stop_reason = reason

    def step(self) -> list[ModuleEvent]:
        """Advance the session by one tick and return emitted events."""
        self.stop_reason = None
        self.clock.advance()
        self.sync_age_caches()

        events: list[ModuleEvent] = []
        for module in self.modules:
            events.extend(module.apply(self))

        self.recalculate_aggregates()
        self.history.record_current_state(
            installation=self.installation,
            facilities=self.facilities,
            systems=self.systems,
            current_date=self.current_date,
            tick_index=self.clock.tick_index,
        )
        events.extend(self._run_pause_policies())

        pause_events = [event for event in events if event.should_pause]
        if pause_events:
            self.pause(reason=pause_events[0].message)
        return events

    def _condition_index_degraded_threshold(self) -> float:
        """Return the configured threshold for degraded condition state."""
        return float(self.settings.get_value("condition_index_degraded_threshold"))

    def get_system_state(self, system_id: str) -> EntityRuntimeState:
        """Return the runtime state for a system."""
        system = self.systems_by_id[system_id]
        open_work_orders = [
            work_order
            for work_order in system.work_orders
            if work_order.status in _OPEN_WORK_ORDER_STATUSES
        ]
        mission_work_orders = [
            work_order for work_order in open_work_orders if work_order.impacts_mission
        ]
        condition_index = system.condition_index
        threshold = self._condition_index_degraded_threshold()
        degraded = condition_index is not None and condition_index <= threshold
        inoperable = condition_index is not None and condition_index <= 0
        mission_blocked = inoperable and bool(mission_work_orders)
        return EntityRuntimeState(
            entity_id=system.id,
            entity_type=EntityType.SYSTEM,
            condition_index=condition_index,
            degraded=degraded,
            inoperable=inoperable,
            mission_blocked=mission_blocked,
            open_work_orders=len(open_work_orders),
            mission_impacting_open_work_orders=len(mission_work_orders),
        )

    def get_facility_state(self, facility_id: str) -> EntityRuntimeState:
        """Return the runtime state for a facility."""
        facility = self.facilities_by_id[facility_id]
        child_states = [
            self.get_system_state(system.id)
            for system in self.systems_by_facility.get(facility.id, [])
        ]
        open_work_orders = sum(state.open_work_orders for state in child_states)
        mission_work_orders = sum(
            state.mission_impacting_open_work_orders for state in child_states
        )
        condition_index = facility.condition_index
        threshold = self._condition_index_degraded_threshold()
        degraded = (
            condition_index is not None and condition_index <= threshold
        ) or any(state.degraded for state in child_states)
        inoperable = (condition_index is not None and condition_index <= 0) or any(
            state.inoperable for state in child_states
        )
        mission_blocked = any(state.mission_blocked for state in child_states) or (
            inoperable and mission_work_orders > 0
        )
        return EntityRuntimeState(
            entity_id=facility.id,
            entity_type=EntityType.FACILITY,
            condition_index=condition_index,
            degraded=degraded,
            inoperable=inoperable,
            mission_blocked=mission_blocked,
            open_work_orders=open_work_orders,
            mission_impacting_open_work_orders=mission_work_orders,
            child_degraded_count=sum(1 for state in child_states if state.degraded),
            child_inoperable_count=sum(1 for state in child_states if state.inoperable),
        )

    def get_installation_state(self) -> EntityRuntimeState:
        """Return the runtime state for the active installation."""
        facility_states = [
            self.get_facility_state(facility.id) for facility in self.facilities
        ]
        open_work_orders = sum(state.open_work_orders for state in facility_states)
        mission_work_orders = sum(
            state.mission_impacting_open_work_orders for state in facility_states
        )
        condition_index = self.installation.condition_index
        threshold = self._condition_index_degraded_threshold()
        degraded = (
            condition_index is not None and condition_index <= threshold
        ) or any(state.degraded for state in facility_states)
        inoperable = (condition_index is not None and condition_index <= 0) or any(
            state.inoperable for state in facility_states
        )
        mission_blocked = any(state.mission_blocked for state in facility_states) or (
            inoperable and mission_work_orders > 0
        )
        return EntityRuntimeState(
            entity_id=self.installation.id,
            entity_type=EntityType.INSTALLATION,
            condition_index=condition_index,
            degraded=degraded,
            inoperable=inoperable,
            mission_blocked=mission_blocked,
            open_work_orders=open_work_orders,
            mission_impacting_open_work_orders=mission_work_orders,
            child_degraded_count=sum(1 for state in facility_states if state.degraded),
            child_inoperable_count=sum(
                1 for state in facility_states if state.inoperable
            ),
        )

    def iter_runtime_states(self) -> list[EntityRuntimeState]:
        """Return runtime states in evaluation order."""
        states = [self.get_system_state(system.id) for system in self.systems]
        states.extend(
            self.get_facility_state(facility.id) for facility in self.facilities
        )
        states.append(self.get_installation_state())
        return states

    def work_order_status_counts(self) -> dict[str, int]:
        """Return counts of work orders grouped by status label."""
        counts = {status.value: 0 for status in WO_Status}
        counts["Unknown"] = 0
        for work_order in self.work_orders:
            if work_order.status is None:
                counts["Unknown"] += 1
            else:
                counts[work_order.status.value] = (
                    counts.get(work_order.status.value, 0) + 1
                )
        return counts

    def condition_summary(self) -> dict[str, int]:
        """Return a summary of degraded and inoperable entity counts."""
        states = self.iter_runtime_states()
        return {
            "degraded": sum(1 for state in states if state.degraded),
            "inoperable": sum(1 for state in states if state.inoperable),
            "mission_blocked": sum(1 for state in states if state.mission_blocked),
        }

    def export_history_tables(self) -> dict[str, object]:
        """Return table-like history outputs for later export integration."""
        return ConditionHistoryExportAdapter(self.history).create_tables(
            installation=self.installation,
            facilities=self.facilities,
            systems=self.systems,
        )

    def _run_pause_policies(self) -> list[ModuleEvent]:
        """Evaluate pause policies against the current session state."""
        events: list[ModuleEvent] = []
        for policy in self.pause_policies:
            events.extend(policy.apply(self))
        return events

    def _shift_playback_delay(self, direction: int) -> float:
        """Move playback delay one step faster or slower."""
        try:
            current_index = _PLAYBACK_DELAY_PRESETS.index(self.playback_delay_seconds)
        except ValueError:
            current_index = 2

        if direction > 0:
            new_index = min(len(_PLAYBACK_DELAY_PRESETS) - 1, current_index + 1)
        else:
            new_index = max(0, current_index - 1)
        self.playback_delay_seconds = _PLAYBACK_DELAY_PRESETS[new_index]
        return self.playback_delay_seconds


def _average_condition_index(entities: list[Facility] | list[System]) -> float | None:
    """Return the rounded average condition index for a list of entities."""
    values = [
        float(entity.condition_index)
        for entity in entities
        if entity.condition_index is not None
    ]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _calculate_age_months(
    year_constructed: int | None, current_date: date
) -> int | None:
    """Return age in whole months relative to the simulated date."""
    if year_constructed is None:
        return None
    age_months = (current_date.year - year_constructed) * 12 + current_date.month - 1
    return max(0, age_months)
