"""Instantiate required systems per facility type and attach work orders."""

from src.functions import generate_id
from src.models import Facility, System, WorkOrder
from .data_generator_base import DataGeneratorBase
from .work_order_generator import WorkOrderGenerator


class SystemGenerator(DataGeneratorBase):
    """Generate systems for facilities and attach generated work orders."""

    def __init__(self, settings=None, seed=None):
        """Initialize system generator with shared settings and seed."""
        super().__init__(settings, seed)

    def generate_by_facility(
        self, facility: Facility
    ) -> tuple[list[System], list[WorkOrder]]:
        """Generate systems and work orders for a facility."""
        all_systems: list[System] = []
        all_work_orders: list[WorkOrder] = []
        required_system_types = self.settings.get_system_types_for_facility(
            facility.facility_type_key or 0
        )
        if not required_system_types:
            return [], []

        max_age = self.settings.simulation.maximum_system_age
        for system_type in required_system_types:
            system = System(
                id=generate_id(),
                system_type_key=system_type.key,
                year_constructed=self.sample_year_constructed(max_age),
                condition_index=self.sample_condition_index(),
                facility_id=facility.id,
            )
            all_systems.append(system)

        wo_generator = WorkOrderGenerator(settings=self.settings, seed=None)
        for system in all_systems:
            generated = wo_generator.generate_by_system(system)
            system.work_orders.extend(generated)
            all_work_orders.extend(generated)

        return all_systems, all_work_orders
