"""Transform domain entities to exportable formats."""

import json
from dataclasses import asdict
from datetime import datetime
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

        # Generate time series data if requested
        if self.include_time_series:
            tables["facility_time_series"] = self._generate_facility_time_series(facilities)
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

    def _generate_facility_time_series(
        self,
        facilities: list[Facility],
    ) -> pd.DataFrame | None:
        """Generate historical condition index time series for facilities.

        Uses exponential decay model to back-calculate historical CI values
        from current state and age.

        Args:
            facilities: List of facilities to generate time series for.

        Returns:
            DataFrame with time series data, or None if no data generated.
        """
        rows = []
        current_date = datetime.now()

        for facility in facilities:
            if facility.condition_index is None or facility.year_constructed is None:
                continue

            facility_type = self.settings.get_facility_type(facility.facility_type_key or 0)
            title = facility_type.title if facility_type else ""

            time_series = self._calculate_historical_ci(
                current_ci=facility.condition_index,
                year_constructed=facility.year_constructed,
                initial_ci=99.99,
            )

            for months_ago, ci_value, date_str in time_series:
                rows.append({
                    "entity_id": facility.id,
                    "entity_type": "facility",
                    "facility_type_key": facility.facility_type_key,
                    "title": title,
                    "date": date_str,
                    "months_ago": months_ago,
                    "condition_index": ci_value,
                })

        return pd.DataFrame(rows) if rows else None

    def _generate_system_time_series(
        self,
        systems: list[System],
    ) -> pd.DataFrame | None:
        """Generate historical condition index time series for systems.

        Uses exponential decay model to back-calculate historical CI values
        from current state and age.

        Args:
            systems: List of systems to generate time series for.

        Returns:
            DataFrame with time series data, or None if no data generated.
        """
        rows = []
        current_date = datetime.now()

        for system in systems:
            if system.condition_index is None or system.year_constructed is None:
                continue

            system_type = self.settings.get_system_type(system.system_type_key or 0)
            title = system_type.title if system_type else ""

            time_series = self._calculate_historical_ci(
                current_ci=system.condition_index,
                year_constructed=system.year_constructed,
                initial_ci=99.99,
            )

            for months_ago, ci_value, date_str in time_series:
                rows.append({
                    "entity_id": system.id,
                    "entity_type": "system",
                    "system_type_key": system.system_type_key,
                    "facility_id": system.facility_id,
                    "title": title,
                    "date": date_str,
                    "months_ago": months_ago,
                    "condition_index": ci_value,
                })

        return pd.DataFrame(rows) if rows else None

    def _calculate_historical_ci(
        self,
        current_ci: float,
        year_constructed: int,
        initial_ci: float = 99.99,
    ) -> list[tuple[int, float, str]]:
        """Calculate historical condition index values using exponential decay.

        Uses the formula: CI(t) = CI_0 * (1 - R)^t
        Solving for R: R = 1 - (CI_current / CI_0)^(1/age_months)
        Back-calculating: CI(t) = CI_0 * (1 - R)^t

        Args:
            current_ci: Current condition index value.
            year_constructed: Year the entity was constructed.
            initial_ci: Initial condition index (default 99.99).

        Returns:
            List of (months_ago, condition_index, date_string) tuples.
        """
        current_date = datetime.now()
        
        # Calculate age in months
        years = current_date.year - year_constructed
        age_months = years * 12 + current_date.month - 1
        
        if age_months <= 0:
            return [(0, current_ci, current_date.strftime("%Y-%m"))]

        # Calculate decay rate: R = 1 - (CI_current / CI_0)^(1/age)
        ratio = current_ci / initial_ci
        if ratio <= 0 or ratio >= 1:
            # No valid decay rate - return flat line at current CI
            return self._generate_flat_series(current_ci, age_months, current_date)

        try:
            decay_rate = 1 - ratio ** (1 / age_months)
            if decay_rate <= 0 or decay_rate >= 1:
                return self._generate_flat_series(current_ci, age_months, current_date)
        except (ValueError, ZeroDivisionError):
            return self._generate_flat_series(current_ci, age_months, current_date)

        # Generate time series by calculating CI at each month
        time_series = []
        
        # Sample points: monthly for first 2 years, then quarterly, then yearly
        sample_points = self._get_sample_points(age_months)
        
        for months_ago in sample_points:
            # Calculate what month this was
            total_months = current_date.year * 12 + current_date.month - 1
            past_total_months = total_months - months_ago
            past_year = past_total_months // 12
            past_month = (past_total_months % 12) + 1
            date_str = f"{past_year:04d}-{past_month:02d}"
            
            # CI at (age_months - months_ago) months old
            age_at_point = age_months - months_ago
            if age_at_point <= 0:
                ci_at_point = initial_ci
            else:
                ci_at_point = initial_ci * ((1 - decay_rate) ** age_at_point)
            
            time_series.append((months_ago, round(ci_at_point, 2), date_str))

        return time_series

    def _get_sample_points(self, age_months: int) -> list[int]:
        """Get sample points for time series generation.

        Uses adaptive sampling:
        - Monthly for months 0-24 (recent data more important)
        - Quarterly for months 24-120 (2-10 years)
        - Yearly for older data

        Args:
            age_months: Total age in months.

        Returns:
            List of months_ago values to sample.
        """
        points = []
        
        # Current month (months_ago = 0)
        points.append(0)
        
        # Monthly for first 24 months
        for m in range(1, min(25, age_months + 1)):
            points.append(m)
        
        # Quarterly from 24-120 months (2-10 years)
        for m in range(27, min(121, age_months + 1), 3):
            points.append(m)
        
        # Yearly beyond 10 years
        for m in range(132, age_months + 1, 12):
            points.append(m)
        
        # Always include the construction date
        if age_months not in points:
            points.append(age_months)
        
        return sorted(set(points))

    def _generate_flat_series(
        self,
        current_ci: float,
        age_months: int,
        current_date: datetime,
    ) -> list[tuple[int, float, str]]:
        """Generate a flat time series (no decay) for edge cases.

        Args:
            current_ci: Current condition index.
            age_months: Age in months.
            current_date: Current datetime.

        Returns:
            List of (months_ago, condition_index, date_string) tuples.
        """
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
