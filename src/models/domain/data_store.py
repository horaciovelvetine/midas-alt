"""Flat collections of installations, facilities, systems, and work orders."""

from dataclasses import dataclass, field

from .facility import Facility
from .installation import Installation
from .system import System
from .work_order import WorkOrder


@dataclass
class DataStore:
    """Primary container for storing MIDAS entities."""

    installations: list[Installation] = field(default_factory=list)
    facilities: list[Facility] = field(default_factory=list)
    systems: list[System] = field(default_factory=list)
    work_orders: list[WorkOrder] = field(default_factory=list)

    @classmethod
    def from_single_installation(
        cls,
        installation: Installation,
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
    ) -> "DataStore":
        """Build a result object for a single generated installation."""
        return cls(
            installations=[installation],
            facilities=facilities,
            systems=systems,
            work_orders=work_orders,
        )
