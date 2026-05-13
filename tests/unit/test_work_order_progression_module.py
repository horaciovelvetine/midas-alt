"""Unit tests for ``WorkOrderProgressionModule`` lifecycle and repair behavior."""

from __future__ import annotations

from datetime import date

import pytest

from src.enums import WO_Priority, WO_Status
from src.enums.entity_type import EntityType
from src.models import DataStore, Facility, Installation, System, WorkOrder
from src.simulation.modules.work_order_progression import WorkOrderProgressionModule
from src.simulation.runtime.clock import SimulationClock, TickSize, TickUnit
from src.simulation.runtime.session import SimulationSession


def _build_session(work_orders: list[WorkOrder]) -> SimulationSession:
    """Build a single-installation session with the provided work orders attached."""
    installation = Installation(id="inst-1", title="Test Base", facility_ids=["fac-1"])
    facility = Facility(
        id="fac-1", installation_id=installation.id, system_ids=["sys-1"]
    )
    system = System(
        id="sys-1",
        facility_id=facility.id,
        condition_index=50.0,
        year_constructed=2010,
    )
    for wo in work_orders:
        wo.installation_id = installation.id
        wo.facility_id = facility.id
        wo.system_id = system.id

    data = DataStore(
        installations=[installation],
        facilities=[facility],
        systems=[system],
        work_orders=list(work_orders),
    )
    return SimulationSession(
        result=data,
        clock=SimulationClock(
            current_date=date(2026, 1, 1), tick_size=TickSize(1, TickUnit.DAY)
        ),
        modules=[],
        pause_policies=[],
    )


@pytest.mark.parametrize(
    ("priority", "tick_thresholds"),
    [
        (WO_Priority.EMERGENCY, (1, 2, 3)),
        (WO_Priority.URGENT, (2, 4, 6)),
        (WO_Priority.ROUTINE, (5, 10, 15)),
        (WO_Priority.MAINTENANCE, (10, 20, 30)),
    ],
)
def test_priority_progression_matches_documented_thresholds(
    priority: WO_Priority, tick_thresholds: tuple[int, int, int]
) -> None:
    """Each priority advances through the documented submitted-approved-in-progress-completed schedule."""
    wo = WorkOrder(id="wo-1", status=WO_Status.SUBMITTED, priority=priority)
    session = _build_session([wo])
    module = WorkOrderProgressionModule(seed=1)

    submitted_to_approved, approved_to_in_progress, in_progress_to_completed = (
        tick_thresholds
    )

    for _ in range(submitted_to_approved - 1):
        module.apply(session)
        assert wo.status == WO_Status.SUBMITTED
    module.apply(session)
    assert wo.status == WO_Status.APPROVED

    for _ in range(approved_to_in_progress - submitted_to_approved - 1):
        module.apply(session)
        assert wo.status == WO_Status.APPROVED
    module.apply(session)
    assert wo.status == WO_Status.IN_PROGRESS

    for _ in range(in_progress_to_completed - approved_to_in_progress - 1):
        module.apply(session)
        assert wo.status == WO_Status.IN_PROGRESS
    module.apply(session)
    assert wo.status == WO_Status.COMPLETED


def test_completed_work_orders_are_ignored() -> None:
    """Work orders already completed are skipped each tick and emit no events."""
    wo = WorkOrder(
        id="wo-done", status=WO_Status.COMPLETED, priority=WO_Priority.EMERGENCY
    )
    session = _build_session([wo])
    module = WorkOrderProgressionModule(seed=42)

    events = module.apply(session)

    assert events == []
    assert wo.status == WO_Status.COMPLETED


def test_status_change_emits_module_event_with_system_entity_type() -> None:
    """Each status change emits a ``work_order_status_changed`` event keyed on the system."""
    wo = WorkOrder(
        id="wo-em", status=WO_Status.SUBMITTED, priority=WO_Priority.EMERGENCY
    )
    session = _build_session([wo])
    module = WorkOrderProgressionModule(seed=1)

    events = module.apply(session)

    assert len(events) == 1
    event = events[0]
    assert event.code == "work_order_status_changed"
    assert event.entity_type == EntityType.SYSTEM
    assert event.entity_id == "wo-em"
    assert event.should_pause is False


def test_completion_repairs_system_with_priority_based_amount() -> None:
    """Completing an emergency work order bumps the system CI by 25.0 (clamped at 100)."""
    wo = WorkOrder(
        id="wo-em",
        status=WO_Status.IN_PROGRESS,
        priority=WO_Priority.EMERGENCY,
    )
    session = _build_session([wo])
    session.systems[0].condition_index = 50.0
    module = WorkOrderProgressionModule(seed=1)

    module._work_order_ages[wo.id] = 2

    events = module.apply(session)

    repair_events = [e for e in events if e.code == "system_repaired"]
    assert len(repair_events) == 1
    repair = repair_events[0]
    assert repair.entity_id == "sys-1"
    assert repair.entity_type == EntityType.SYSTEM
    assert session.systems[0].condition_index == 75.0


def test_completion_caps_condition_index_at_one_hundred() -> None:
    """Repairs never push the system CI above ``100.0``."""
    wo = WorkOrder(
        id="wo-em",
        status=WO_Status.IN_PROGRESS,
        priority=WO_Priority.EMERGENCY,
    )
    session = _build_session([wo])
    session.systems[0].condition_index = 90.0
    module = WorkOrderProgressionModule(seed=1)
    module._work_order_ages[wo.id] = 2

    module.apply(session)

    assert session.systems[0].condition_index == 100.0


def test_repair_amount_uses_preventive_maintenance_branch() -> None:
    """Routine + ``Preventive Maintenance`` category repairs by 30.0."""
    wo = WorkOrder(
        id="wo-pm",
        status=WO_Status.IN_PROGRESS,
        priority=WO_Priority.ROUTINE,
        work_category="Preventive Maintenance",
    )
    module = WorkOrderProgressionModule(seed=1)
    assert module._calculate_repair_amount(wo) == 30.0


def test_repair_amount_default_branch_uses_fifteen() -> None:
    """Routine work orders without a known category default to 15.0."""
    wo = WorkOrder(
        id="wo-rt",
        status=WO_Status.IN_PROGRESS,
        priority=WO_Priority.ROUTINE,
        work_category=None,
    )
    module = WorkOrderProgressionModule(seed=1)
    assert module._calculate_repair_amount(wo) == 15.0


def test_repair_skipped_when_system_has_no_condition_index() -> None:
    """If the linked system's CI is ``None``, no ``system_repaired`` event is emitted."""
    wo = WorkOrder(
        id="wo-em",
        status=WO_Status.IN_PROGRESS,
        priority=WO_Priority.EMERGENCY,
    )
    session = _build_session([wo])
    session.systems[0].condition_index = None
    module = WorkOrderProgressionModule(seed=1)
    module._work_order_ages[wo.id] = 2

    events = module.apply(session)
    assert all(event.code != "system_repaired" for event in events)


def test_find_system_returns_none_when_system_id_missing() -> None:
    """The lookup helper short-circuits when ``system_id`` is unset."""
    wo = WorkOrder(id="wo-loose", system_id=None, priority=WO_Priority.EMERGENCY)
    session = _build_session([])
    module = WorkOrderProgressionModule(seed=1)
    assert module._find_system_for_work_order(wo, session) is None


def test_work_order_age_is_dropped_after_completion() -> None:
    """The age ledger entry is removed once the work order finishes."""
    wo = WorkOrder(
        id="wo-em",
        status=WO_Status.IN_PROGRESS,
        priority=WO_Priority.EMERGENCY,
    )
    session = _build_session([wo])
    module = WorkOrderProgressionModule(seed=1)
    module._work_order_ages[wo.id] = 2

    module.apply(session)
    assert wo.id not in module._work_order_ages
