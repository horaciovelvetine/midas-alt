"""Transform domain entities to exportable formats."""

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

import pandas as pd

from ...domain import Facility, Installation, System

if TYPE_CHECKING:
    from ...config import MIDASSettings


class DataTransformer:
    """Transforms domain entities into exportable formats (tables, dicts).
    
    Works with the new dataclass-based domain entities.
    """

    def __init__(
        self,
        settings: "MIDASSettings | None" = None,
        include_time_series: bool = False,
    ) -> None:
        """Initialize transformer.

        Args:
            settings: Application settings for reference data lookup.
            include_time_series: Whether to include time series data.
        """
        # Lazy import to avoid circular dependency
        from ...config import MIDASSettings
        self.settings = settings or MIDASSettings.with_defaults()
        self.include_time_series = include_time_series

    def create_normalized_tables(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
    ) -> dict[str, pd.DataFrame | None]:
        """Create normalized tables from domain entities.

        Args:
            installations: List of installations.
            facilities: List of facilities.
            systems: List of systems.

        Returns:
            Dictionary mapping table names to DataFrames.
        """
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
            installations_rows.append({
                "id": install.id,
                "title": install.title,
                "condition_index": install.condition_index,
                "facility_count": len(install.facility_ids),
            })

        # Create facilities table
        facilities_rows = []
        for facility in facilities:
            facility_type = self.settings.get_facility_type(facility.facility_type_key or 0)
            facilities_rows.append({
                "id": facility.id,
                "installation_id": facility.installation_id,
                "facility_type_key": facility.facility_type_key,
                "title": facility_type.title if facility_type else "",
                "year_constructed": facility.year_constructed,
                "age_years": facility.age_years,
                "condition_index": facility.condition_index,
                "dependency_chain": facility.dependency_position,
                "resiliency_grade": facility.resiliency_grade.value if facility.resiliency_grade else None,
                "life_expectancy": facility_type.life_expectancy if facility_type else None,
                "mission_criticality": facility_type.mission_criticality if facility_type else None,
            })

        # Create systems table
        systems_rows = []
        for system in systems:
            system_type = self.settings.get_system_type(system.system_type_key or 0)
            systems_rows.append({
                "id": system.id,
                "facility_id": system.facility_id,
                "system_type_key": system.system_type_key,
                "title": system_type.title if system_type else "",
                "year_constructed": system.year_constructed,
                "age_years": system.age_years,
                "condition_index": system.condition_index,
                "life_expectancy": system_type.life_expectancy if system_type else None,
            })

        tables = {
            "installations": pd.DataFrame(installations_rows) if installations_rows else None,
            "facilities": pd.DataFrame(facilities_rows) if facilities_rows else None,
            "systems": pd.DataFrame(systems_rows) if systems_rows else None,
        }

        # Time series tables would require simulation of historical data
        # For now, set to None (can be enhanced later)
        tables["facility_time_series"] = None
        tables["system_time_series"] = None

        return tables

    def create_denormalized_rows(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
    ) -> list[dict]:
        """Create flattened rows for denormalized export.

        Args:
            installations: List of installations.
            facilities: List of facilities.
            systems: List of systems.

        Returns:
            List of flattened row dictionaries.
        """
        # Build lookups
        install_map = {i.id: i for i in installations}
        facility_map = {f.id: f for f in facilities}

        rows = []
        for system in systems:
            facility = facility_map.get(system.facility_id)
            if not facility:
                continue
            install = install_map.get(facility.installation_id)
            if not install:
                continue

            facility_type = self.settings.get_facility_type(facility.facility_type_key or 0)
            system_type = self.settings.get_system_type(system.system_type_key or 0)

            row = {
                "installation_id": install.id,
                "installation_title": install.title,
                "installation_condition_index": install.condition_index,
                "facility_id": facility.id,
                "facility_type_key": facility.facility_type_key,
                "facility_title": facility_type.title if facility_type else "",
                "facility_year_constructed": facility.year_constructed,
                "facility_age_years": facility.age_years,
                "facility_condition_index": facility.condition_index,
                "facility_dependency_chain": facility.dependency_position,
                "facility_resiliency_grade": facility.resiliency_grade.value if facility.resiliency_grade else None,
                "system_id": system.id,
                "system_type_key": system.system_type_key,
                "system_title": system_type.title if system_type else "",
                "system_year_constructed": system.year_constructed,
                "system_age_years": system.age_years,
                "system_condition_index": system.condition_index,
            }
            rows.append(row)

        return rows

    def create_nested_dict(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
    ) -> dict:
        """Create nested dictionary structure for JSON export.

        Args:
            installations: List of installations.
            facilities: List of facilities.
            systems: List of systems.

        Returns:
            Dictionary with nested installation structure.
        """
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

        data = []
        for install in installations:
            install_data = {
                "id": install.id,
                "title": install.title,
                "condition_index": install.condition_index,
                "facilities": [],
            }

            for facility in facilities_by_install.get(install.id, []):
                facility_type = self.settings.get_facility_type(facility.facility_type_key or 0)
                facility_data = {
                    "id": facility.id,
                    "facility_type_key": facility.facility_type_key,
                    "title": facility_type.title if facility_type else "",
                    "year_constructed": facility.year_constructed,
                    "age_years": facility.age_years,
                    "condition_index": facility.condition_index,
                    "dependency_chain": facility.dependency_position,
                    "resiliency_grade": facility.resiliency_grade.value if facility.resiliency_grade else None,
                    "systems": [],
                }

                for system in systems_by_facility.get(facility.id, []):
                    system_type = self.settings.get_system_type(system.system_type_key or 0)
                    system_data = {
                        "id": system.id,
                        "system_type_key": system.system_type_key,
                        "title": system_type.title if system_type else "",
                        "year_constructed": system.year_constructed,
                        "age_years": system.age_years,
                        "condition_index": system.condition_index,
                    }
                    facility_data["systems"].append(system_data)

                install_data["facilities"].append(facility_data)

            data.append(install_data)

        return {"installations": data}
