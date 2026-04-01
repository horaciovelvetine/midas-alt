"""Work order progression and system repair for runtime simulation."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...enums.entity_type import EntityType
from ...enums.work_order import WO_Priority, WO_Status
from .base import Base, ModuleEvent

if TYPE_CHECKING:
    from ...models import WorkOrder, System
    from ..runtime.session import SimulationSession


class WorkOrderProgressionModule(Base):
    """Progress work orders through lifecycle and repair systems on completion."""

    def __init__(self, seed: int | None = None) -> None:
        """Initialize work order tracking and optional deterministic randomness."""
        self._rng = random.Random(seed)
        self._work_order_ages: dict[str, int] = {}  # Track ticks since submission

    def apply(self, session: SimulationSession) -> list[ModuleEvent]:
        """Advance work orders and repair systems for one simulation tick."""
        events: list[ModuleEvent] = []

        for wo in session.work_orders:
            if wo.status == WO_Status.COMPLETED:
                continue

            # Track how long this work order has been open
            self._work_order_ages[wo.id] = (
                self._work_order_ages.get(wo.id, 0) + 1
            )

            # Progress work order through lifecycle
            old_status = wo.status
            new_status = self._advance_work_order_status(wo, session)

            if new_status != old_status:
                wo.status = new_status
                events.append(
                    ModuleEvent(
                        code="work_order_status_changed",
                        message=f"Work order {wo.id} progressed from {old_status} to {new_status}.",
                        entity_id=wo.id,
                        entity_type=EntityType.SYSTEM,
                    )
                )

                # If completed, repair the system
                if new_status == WO_Status.COMPLETED:
                    repair_event = self._repair_system(wo, session)
                    if repair_event:
                        events.append(repair_event)
                    self._work_order_ages.pop(wo.id, None)

        return events

    def _advance_work_order_status(
        self, wo: WorkOrder, session: SimulationSession
    ) -> WO_Status:
        """Determine next status for a work order based on priority and age."""
        age_ticks = self._work_order_ages.get(wo.id, 0)

        # Priority-based progression speeds
        if wo.priority == WO_Priority.EMERGENCY:
            if wo.status == WO_Status.SUBMITTED and age_ticks >= 1:
                return WO_Status.APPROVED
            if wo.status == WO_Status.APPROVED and age_ticks >= 2:
                return WO_Status.IN_PROGRESS
            if wo.status == WO_Status.IN_PROGRESS and age_ticks >= 3:
                return WO_Status.COMPLETED

        elif wo.priority == WO_Priority.URGENT:
            if wo.status == WO_Status.SUBMITTED and age_ticks >= 2:
                return WO_Status.APPROVED
            if wo.status == WO_Status.APPROVED and age_ticks >= 4:
                return WO_Status.IN_PROGRESS
            if wo.status == WO_Status.IN_PROGRESS and age_ticks >= 6:
                return WO_Status.COMPLETED

        elif wo.priority == WO_Priority.ROUTINE:
            if wo.status == WO_Status.SUBMITTED and age_ticks >= 5:
                return WO_Status.APPROVED
            if wo.status == WO_Status.APPROVED and age_ticks >= 10:
                return WO_Status.IN_PROGRESS
            if wo.status == WO_Status.IN_PROGRESS and age_ticks >= 15:
                return WO_Status.COMPLETED

        else:  # MAINTENANCE
            if wo.status == WO_Status.SUBMITTED and age_ticks >= 10:
                return WO_Status.APPROVED
            if wo.status == WO_Status.APPROVED and age_ticks >= 20:
                return WO_Status.IN_PROGRESS
            if wo.status == WO_Status.IN_PROGRESS and age_ticks >= 30:
                return WO_Status.COMPLETED

        return wo.status

    def _repair_system(
        self, wo: WorkOrder, session: SimulationSession
    ) -> ModuleEvent | None:
        """Repair system when work order completes."""
        system = self._find_system_for_work_order(wo, session)
        if not system or system.condition_index is None:
            return None

        repair_amount = self._calculate_repair_amount(wo)

        old_ci = system.condition_index
        system.condition_index = min(100.0, round(system.condition_index + repair_amount, 2))

        return ModuleEvent(
            code="system_repaired",
            message=(
                f"System {system.id} repaired via work order {wo.id}. "
                f"CI increased from {old_ci:.2f} to {system.condition_index:.2f}."
            ),
            entity_id=system.id,
            entity_type=EntityType.SYSTEM,
        )

    def _find_system_for_work_order(
        self, wo: WorkOrder, session: SimulationSession
    ) -> System | None:
        """Find the system associated with a work order."""
        if wo.system_id:
            return next((s for s in session.systems if s.id == wo.system_id), None)
        return None

    def _calculate_repair_amount(self, wo: WorkOrder) -> float:
        """Calculate CI increase based on work order type and priority."""
        if wo.priority == WO_Priority.EMERGENCY:
            return 25.0
        elif wo.priority == WO_Priority.URGENT:
            return 20.0
        elif wo.work_category == "Preventive Maintenance":
            return 30.0
        else:
            return 15.0