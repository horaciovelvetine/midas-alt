"""Build installation roots and delegate facility/system/work-order generation."""

from src.functions import generate_id
from src.models import DataStore, Facility, Installation, System, WorkOrder

from .data_generator_base import DataGeneratorBase
from .facility_generator import FacilityGenerator


class InstallGenerator(DataGeneratorBase):
    """Generate installation roots and aggregate generated descendants."""

    def __init__(self, seed: int | None = None) -> None:
        """Initialize installation generator with optional seed."""
        super().__init__(seed=seed)

    def generate(
        self,
    ) -> tuple[Installation, list[Facility], list[System], list[WorkOrder]]:
        """Generate one installation and all downstream entities."""
        install = self._initialize_install_instance()
        target_facility_count = self.settings.get_random_facility_count()
        facility_generator = FacilityGenerator(seed=None)
        facilities, systems, work_orders = facility_generator.generate_by_count(
            installation_id=install.id,
            count=target_facility_count,
        )
        install.facility_ids = [facility.id for facility in facilities]
        install.condition_index = self.average_condition_index(facilities)
        return install, facilities, systems, work_orders

    def generate_by_count(self, count: int) -> DataStore:
        """Generate multiple installations and return a typed aggregate result."""
        installations: list[Installation] = []
        facilities: list[Facility] = []
        systems: list[System] = []
        work_orders: list[WorkOrder] = []

        for _ in range(max(0, count)):
            install, install_facilities, install_systems, install_work_orders = (
                self.generate()
            )
            installations.append(install)
            facilities.extend(install_facilities)
            systems.extend(install_systems)
            work_orders.extend(install_work_orders)

        return DataStore(
            installations=installations,
            facilities=facilities,
            systems=systems,
            work_orders=work_orders,
        )

    def _initialize_install_instance(self) -> Installation:
        """Initialize an installation root entity."""
        location = self.config_data.get_random_location()
        if location:
            return Installation(
                id=generate_id(),
                title=location.title,
                location=location.location,
                region=location.region,
                coordinates=location.coordinates,
            )
        return Installation(
            id=generate_id(),
            title=f"GENERATED_INSTALL_{generate_id()[:4]}",
        )
