"""Transform domain entities to exportable formats."""

from __future__ import annotations

import pandas as pd

from src.config.midas_config_data import MidasConfigData
from src.models import Facility, Installation, System, WorkOrder


class DataTransformer:
    """Build normalized tables, denormalized rows, and nested dicts for exporters."""

    def __init__(self) -> None:
        """Use the ``MidasConfigData`` singleton for reference lookups."""
        self.config_data = MidasConfigData()

    def _facility_type_title(self, facility: Facility) -> str:
        """Resolve facility type title from denormalized data or reference lookup."""
        facility_type = self.config_data.get_facility_type(facility.facility_type_key or 0)
        return (facility.facility_type_title or "").strip() or (facility_type.title if facility_type else "")

    def create_normalized_tables(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
    ) -> dict[str, pd.DataFrame | None]:
        """Return keyed DataFrames for each normalized export table."""
        facilities_by_install: dict[str, list[Facility]] = {}
        for f in facilities:
            facilities_by_install.setdefault(f.installation_id, []).append(f)

        systems_by_facility: dict[str, list[System]] = {}
        for s in systems:
            systems_by_facility.setdefault(s.facility_id, []).append(s)

        installations_rows = []
        for install in installations:
            installations_rows.append(
                {
                    "id": install.id,
                    "title": install.title,
                    "location": install.location,
                    "region": install.region,
                    "coordinates": install.coordinates,
                    "condition_index": install.condition_index,
                    "facility_count": len(install.facility_ids),
                }
            )

        facilities_rows = []
        for facility in facilities:
            facility_type = self.config_data.get_facility_type(facility.facility_type_key or 0)
            facilities_rows.append(
                {
                    "id": facility.id,
                    "installation_id": facility.installation_id,
                    "facility_type_key": facility.facility_type_key,
                    "title": self._facility_type_title(facility),
                    "year_constructed": facility.year_constructed,
                    "age_years": facility.age_years,
                    "condition_index": facility.condition_index,
                    "dependency_chain": facility.dependency_position,
                    "resiliency_grade": (facility.resiliency_grade.value if facility.resiliency_grade else None),
                    "life_expectancy": (facility_type.life_expectancy if facility_type else None),
                    "mission_criticality": (facility_type.mission_criticality if facility_type else None),
                }
            )

        systems_rows = []
        for system in systems:
            system_type = self.config_data.get_system_type(system.system_type_key or 0)
            systems_rows.append(
                {
                    "id": system.id,
                    "facility_id": system.facility_id,
                    "system_type_key": system.system_type_key,
                    "title": system_type.title if system_type else "",
                    "year_constructed": system.year_constructed,
                    "age_years": system.age_years,
                    "condition_index": system.condition_index,
                    "life_expectancy": (system_type.life_expectancy if system_type else None),
                }
            )

        work_orders_rows = []
        for work_order in work_orders:
            work_orders_rows.append(
                {
                    "id": work_order.id,
                    "installation_id": work_order.installation_id,
                    "facility_id": work_order.facility_id,
                    "system_id": work_order.system_id,
                    "requesting_organization": work_order.requesting_organization,
                    "work_category": work_order.work_category,
                    "impacts_mission": work_order.impacts_mission,
                    "status": work_order.status.value if work_order.status else None,
                    "priority": (work_order.priority.value if work_order.priority else None),
                    "trade": work_order.trade.value if work_order.trade else None,
                    "request_datetime": work_order.request_datetime,
                    "completion_datetime": work_order.completion_datetime,
                    "problem_description": work_order.problem_description,
                    "requested_action": work_order.requested_action,
                    "actions_taken": work_order.actions_taken,
                }
            )

        return {
            "installations": (pd.DataFrame(installations_rows) if installations_rows else None),
            "facilities": pd.DataFrame(facilities_rows) if facilities_rows else None,
            "systems": pd.DataFrame(systems_rows) if systems_rows else None,
            "work_orders": pd.DataFrame(work_orders_rows) if work_orders_rows else None,
        }

    def create_denormalized_rows(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
    ) -> list[dict]:
        """One flat dict per work order with denormalized installation/facility/system fields."""
        install_map = {i.id: i for i in installations}
        facility_map = {f.id: f for f in facilities}
        system_map = {s.id: s for s in systems}

        rows = []
        for work_order in work_orders:
            system = system_map.get(work_order.system_id or "")
            if not system:
                continue
            facility = facility_map.get(system.facility_id)
            if not facility:
                continue
            install = install_map.get(facility.installation_id)
            if not install:
                continue

            system_type = self.config_data.get_system_type(system.system_type_key or 0)

            row = {
                "installation_id": install.id,
                "installation_title": install.title,
                "installation_location": install.location,
                "installation_region": install.region,
                "installation_coordinates": install.coordinates,
                "installation_condition_index": install.condition_index,
                "facility_id": facility.id,
                "facility_type_key": facility.facility_type_key,
                "facility_title": self._facility_type_title(facility),
                "facility_year_constructed": facility.year_constructed,
                "facility_age_years": facility.age_years,
                "facility_condition_index": facility.condition_index,
                "facility_dependency_chain": facility.dependency_position,
                "facility_resiliency_grade": (facility.resiliency_grade.value if facility.resiliency_grade else None),
                "system_id": system.id,
                "system_type_key": system.system_type_key,
                "system_title": system_type.title if system_type else "",
                "system_year_constructed": system.year_constructed,
                "system_age_years": system.age_years,
                "system_condition_index": system.condition_index,
                "work_order_id": work_order.id,
                "work_order_status": (work_order.status.value if work_order.status else None),
                "work_order_priority": (work_order.priority.value if work_order.priority else None),
                "work_order_trade": (work_order.trade.value if work_order.trade else None),
                "work_order_requesting_organization": work_order.requesting_organization,
                "work_order_impacts_mission": work_order.impacts_mission,
                "work_order_request_datetime": work_order.request_datetime,
                "work_order_completion_datetime": work_order.completion_datetime,
                "work_order_problem_description": work_order.problem_description,
                "work_order_requested_action": work_order.requested_action,
                "work_order_actions_taken": work_order.actions_taken,
            }
            rows.append(row)

        return rows

    def create_nested_dict(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
    ) -> dict:
        """Nested list/dict tree: installations -> facilities -> systems -> work orders."""
        facilities_by_install: dict[str, list[Facility]] = {}
        for f in facilities:
            facilities_by_install.setdefault(f.installation_id, []).append(f)

        systems_by_facility: dict[str, list[System]] = {}
        for s in systems:
            systems_by_facility.setdefault(s.facility_id, []).append(s)

        work_orders_by_system: dict[str, list[WorkOrder]] = {}
        for work_order in work_orders:
            if not work_order.system_id:
                continue
            work_orders_by_system.setdefault(work_order.system_id, []).append(work_order)

        data = []
        for install in installations:
            install_data = {
                "id": install.id,
                "title": install.title,
                "location": install.location,
                "region": install.region,
                "coordinates": install.coordinates,
                "condition_index": install.condition_index,
                "facilities": [],
            }

            for facility in facilities_by_install.get(install.id, []):
                facility_data = {
                    "id": facility.id,
                    "facility_type_key": facility.facility_type_key,
                    "title": self._facility_type_title(facility),
                    "year_constructed": facility.year_constructed,
                    "age_years": facility.age_years,
                    "condition_index": facility.condition_index,
                    "dependency_chain": facility.dependency_position,
                    "resiliency_grade": (facility.resiliency_grade.value if facility.resiliency_grade else None),
                    "systems": [],
                }

                for system in systems_by_facility.get(facility.id, []):
                    system_type = self.config_data.get_system_type(system.system_type_key or 0)
                    system_data = {
                        "id": system.id,
                        "system_type_key": system.system_type_key,
                        "title": system_type.title if system_type else "",
                        "year_constructed": system.year_constructed,
                        "age_years": system.age_years,
                        "condition_index": system.condition_index,
                        "work_orders": [],
                    }
                    for work_order in work_orders_by_system.get(system.id, []):
                        system_data["work_orders"].append(
                            {
                                "id": work_order.id,
                                "status": (work_order.status.value if work_order.status else None),
                                "priority": (work_order.priority.value if work_order.priority else None),
                                "trade": (work_order.trade.value if work_order.trade else None),
                                "requesting_organization": work_order.requesting_organization,
                                "impacts_mission": work_order.impacts_mission,
                                "request_datetime": work_order.request_datetime,
                                "completion_datetime": work_order.completion_datetime,
                                "problem_description": work_order.problem_description,
                                "requested_action": work_order.requested_action,
                                "actions_taken": work_order.actions_taken,
                            }
                        )
                    facility_data["systems"].append(system_data)

                install_data["facilities"].append(facility_data)

            data.append(install_data)

        return {"installations": data}
