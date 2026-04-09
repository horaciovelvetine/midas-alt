"""Transform domain entities to exportable formats."""

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from src.config.app_state import get_app_state
from src.models import Facility, Installation, System, WorkOrder

if TYPE_CHECKING:
    from src.config.settings import MIDASSettings


class DataTransformer:
    """Build normalized tables, denormalized rows, and nested dicts for exporters."""

    def __init__(
        self,
        settings: "MIDASSettings | None" = None,
        include_time_series: bool = False,
    ) -> None:
        """Use ``settings`` (or app state) and optionally materialize time-series tables."""
        self.settings = settings or get_app_state().settings
        self.include_time_series = include_time_series

    def _facility_type_title(self, facility: Facility) -> str:
        """Resolve facility type title from denormalized data or reference lookup."""
        facility_type = self.settings.get_facility_type(facility.facility_type_key or 0)
        return (facility.facility_type_title or "").strip() or (
            facility_type.title if facility_type else ""
        )

    def create_normalized_tables(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
    ) -> dict[str, pd.DataFrame | None]:
        """Return keyed DataFrames for each logical export table (time series optional)."""
        # Build lookup for facilities and systems
        facilities_by_install = {}
        for f in facilities:
            if f.installation_id not in facilities_by_install:
                facilities_by_install[f.installation_id] = []
            facilities_by_install[f.installation_id].append(f)

        systems_by_facility = {}
        for s in systems:
            if s.facility_id not in systems_by_facility:
                systems_by_facility[s.facility_id] = []
            systems_by_facility[s.facility_id].append(s)

        # Create installations table
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

        # Create facilities table
        facilities_rows = []
        for facility in facilities:
            facility_type = self.settings.get_facility_type(
                facility.facility_type_key or 0
            )
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
                    "resiliency_grade": (
                        facility.resiliency_grade.value
                        if facility.resiliency_grade
                        else None
                    ),
                    "life_expectancy": (
                        facility_type.life_expectancy if facility_type else None
                    ),
                    "mission_criticality": (
                        facility_type.mission_criticality if facility_type else None
                    ),
                }
            )

        # Create systems table
        systems_rows = []
        for system in systems:
            system_type = self.settings.get_system_type(system.system_type_key or 0)
            systems_rows.append(
                {
                    "id": system.id,
                    "facility_id": system.facility_id,
                    "system_type_key": system.system_type_key,
                    "title": system_type.title if system_type else "",
                    "year_constructed": system.year_constructed,
                    "age_years": system.age_years,
                    "condition_index": system.condition_index,
                    "life_expectancy": (
                        system_type.life_expectancy if system_type else None
                    ),
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
                    "room_area": work_order.room_area,
                    "impacts_mission": work_order.impacts_mission,
                    "status": work_order.status.value if work_order.status else None,
                    "priority": (
                        work_order.priority.value if work_order.priority else None
                    ),
                    "trade": work_order.trade.value if work_order.trade else None,
                    "request_datetime": work_order.request_datetime,
                    "completion_datetime": work_order.completion_datetime,
                    "problem_description": work_order.problem_description,
                    "requested_action": work_order.requested_action,
                    "actions_taken": work_order.actions_taken,
                }
            )

        tables = {
            "installations": (
                pd.DataFrame(installations_rows) if installations_rows else None
            ),
            "facilities": pd.DataFrame(facilities_rows) if facilities_rows else None,
            "systems": pd.DataFrame(systems_rows) if systems_rows else None,
            "work_orders": pd.DataFrame(work_orders_rows) if work_orders_rows else None,
        }

        # Generate time series data if requested
        if self.include_time_series:
            tables["facility_time_series"] = self._generate_facility_time_series(
                facilities
            )
            tables["system_time_series"] = self._generate_system_time_series(systems)
        else:
            tables["facility_time_series"] = None
            tables["system_time_series"] = None

        return tables

    def create_denormalized_rows(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
    ) -> list[dict]:
        """One flat dict per work order with denormalized installation/facility/system fields."""
        # Build lookups
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

            facility_type = self.settings.get_facility_type(
                facility.facility_type_key or 0
            )
            system_type = self.settings.get_system_type(system.system_type_key or 0)

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
                "facility_resiliency_grade": (
                    facility.resiliency_grade.value
                    if facility.resiliency_grade
                    else None
                ),
                "system_id": system.id,
                "system_type_key": system.system_type_key,
                "system_title": system_type.title if system_type else "",
                "system_year_constructed": system.year_constructed,
                "system_age_years": system.age_years,
                "system_condition_index": system.condition_index,
                "work_order_id": work_order.id,
                "work_order_status": (
                    work_order.status.value if work_order.status else None
                ),
                "work_order_priority": (
                    work_order.priority.value if work_order.priority else None
                ),
                "work_order_trade": (
                    work_order.trade.value if work_order.trade else None
                ),
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
        """Nested list/dict tree: installations → facilities → systems → work orders."""
        # Build lookups
        facilities_by_install = {}
        for f in facilities:
            if f.installation_id not in facilities_by_install:
                facilities_by_install[f.installation_id] = []
            facilities_by_install[f.installation_id].append(f)

        systems_by_facility = {}
        for s in systems:
            if s.facility_id not in systems_by_facility:
                systems_by_facility[s.facility_id] = []
            systems_by_facility[s.facility_id].append(s)

        work_orders_by_system: dict[str, list[WorkOrder]] = {}
        for work_order in work_orders:
            if not work_order.system_id:
                continue
            if work_order.system_id not in work_orders_by_system:
                work_orders_by_system[work_order.system_id] = []
            work_orders_by_system[work_order.system_id].append(work_order)

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
                facility_type = self.settings.get_facility_type(
                    facility.facility_type_key or 0
                )
                facility_data = {
                    "id": facility.id,
                    "facility_type_key": facility.facility_type_key,
                    "title": self._facility_type_title(facility),
                    "year_constructed": facility.year_constructed,
                    "age_years": facility.age_years,
                    "condition_index": facility.condition_index,
                    "dependency_chain": facility.dependency_position,
                    "resiliency_grade": (
                        facility.resiliency_grade.value
                        if facility.resiliency_grade
                        else None
                    ),
                    "systems": [],
                }

                for system in systems_by_facility.get(facility.id, []):
                    system_type = self.settings.get_system_type(
                        system.system_type_key or 0
                    )
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
                                "status": (
                                    work_order.status.value
                                    if work_order.status
                                    else None
                                ),
                                "priority": (
                                    work_order.priority.value
                                    if work_order.priority
                                    else None
                                ),
                                "trade": (
                                    work_order.trade.value if work_order.trade else None
                                ),
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

    # ! ====================================================================================>
    # ! Sunsetted Condition Index Time Series code...
    # ! Originally used to generate Condition Index history using (Spacecom J4 provided) PERT
    # !   modelling curve, commented out here to provide historical context to early iterations
    # !   of functionality through the early stages of MIDAS.
    # ! ====================================================================================>

    def _generate_facility_time_series(
        self,
        facilities: list[Facility],
    ) -> pd.DataFrame | None:
        """Generate historical condition index time series for facilities."""
        rows = []

        for facility in facilities:
            if facility.condition_index is None or facility.year_constructed is None:
                continue

            title = self._facility_type_title(facility)

            time_series = self._calculate_historical_ci(
                current_ci=facility.condition_index,
                year_constructed=facility.year_constructed,
                initial_ci=self.settings.degradation.initial_condition_index,
            )

            for months_ago, ci_value, date_str in time_series:
                rows.append(
                    {
                        "entity_id": facility.id,
                        "entity_type": "facility",
                        "facility_type_key": facility.facility_type_key,
                        "title": title,
                        "date": date_str,
                        "months_ago": months_ago,
                        "condition_index": ci_value,
                    }
                )

        return pd.DataFrame(rows) if rows else None

    def _generate_system_time_series(
        self,
        systems: list[System],
    ) -> pd.DataFrame | None:
        """Generate historical condition index time series for systems."""
        rows = []

        for system in systems:
            if system.condition_index is None or system.year_constructed is None:
                continue

            system_type = self.settings.get_system_type(system.system_type_key or 0)
            title = system_type.title if system_type else ""

            time_series = self._calculate_historical_ci(
                current_ci=system.condition_index,
                year_constructed=system.year_constructed,
                initial_ci=self.settings.degradation.initial_condition_index,
            )

            for months_ago, ci_value, date_str in time_series:
                rows.append(
                    {
                        "entity_id": system.id,
                        "entity_type": "system",
                        "system_type_key": system.system_type_key,
                        "facility_id": system.facility_id,
                        "title": title,
                        "date": date_str,
                        "months_ago": months_ago,
                        "condition_index": ci_value,
                    }
                )

        return pd.DataFrame(rows) if rows else None

    def _calculate_historical_ci(
        self,
        current_ci: float,
        year_constructed: int,
        initial_ci: float = 99.99,
    ) -> list[tuple[int, float, str]]:
        """Calculate historical condition index values using exponential decay."""
        current_date = datetime.now()

        years = current_date.year - year_constructed
        age_months = years * 12 + current_date.month - 1

        if age_months <= 0:
            return [(0, current_ci, current_date.strftime("%Y-%m"))]

        ratio = current_ci / initial_ci
        if ratio <= 0 or ratio >= 1:
            return self._generate_flat_series(current_ci, age_months, current_date)

        try:
            decay_rate = 1 - ratio ** (1 / age_months)
            if decay_rate <= 0 or decay_rate >= 1:
                return self._generate_flat_series(current_ci, age_months, current_date)
        except (ValueError, ZeroDivisionError):
            return self._generate_flat_series(current_ci, age_months, current_date)

        time_series = []
        sample_points = self._get_sample_points(age_months)

        for months_ago in sample_points:
            total_months = current_date.year * 12 + current_date.month - 1
            past_total_months = total_months - months_ago
            past_year = past_total_months // 12
            past_month = (past_total_months % 12) + 1
            date_str = f"{past_year:04d}-{past_month:02d}"

            age_at_point = age_months - months_ago
            if age_at_point <= 0:
                ci_at_point = initial_ci
            else:
                ci_at_point = initial_ci * ((1 - decay_rate) ** age_at_point)

            time_series.append((months_ago, round(ci_at_point, 2), date_str))

        return time_series

    def _get_sample_points(self, age_months: int) -> list[int]:
        """Get adaptive sample points for historical condition-index series."""
        max_months = self.settings.degradation.max_time_series_years * 12
        effective_age = min(age_months, max_months)

        points = [0]
        for month in range(1, min(25, effective_age + 1)):
            points.append(month)
        for month in range(27, min(121, effective_age + 1), 3):
            points.append(month)
        for month in range(132, effective_age + 1, 12):
            points.append(month)

        if effective_age not in points and effective_age > 0:
            points.append(effective_age)

        return sorted(set(points))

    def _generate_flat_series(
        self,
        current_ci: float,
        age_months: int,
        current_date: datetime,
    ) -> list[tuple[int, float, str]]:
        """Generate a flat time series for edge cases that cannot infer decay."""
        sample_points = self._get_sample_points(age_months)
        time_series = []

        for months_ago in sample_points:
            total_months = current_date.year * 12 + current_date.month - 1
            past_total_months = total_months - months_ago
            past_year = past_total_months // 12
            past_month = (past_total_months % 12) + 1
            date_str = f"{past_year:04d}-{past_month:02d}"
            time_series.append((months_ago, round(current_ci, 2), date_str))

        return time_series
