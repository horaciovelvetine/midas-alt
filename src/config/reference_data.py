"""Reference data types loaded from configuration.

These are the "type" definitions for facilities and systems,
loaded from the Excel configuration file.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FacilityType:
    """Definition of a facility type from configuration.

    Attributes:
        key: Unique identifier for this facility type
        title: Human-readable name
        life_expectancy: Expected lifespan in years
        mission_criticality: Importance rating (1-5 typically)
    """

    key: int
    title: str
    life_expectancy: int
    mission_criticality: int = 1

    @property
    def life_expectancy_months(self) -> int:
        """Life expectancy in months."""
        return self.life_expectancy * 12


@dataclass(frozen=True)
class SystemType:
    """Definition of a system type from configuration.

    Attributes:
        key: Unique identifier for this system type
        title: Human-readable name
        life_expectancy: Expected lifespan in years
        facility_keys: List of facility type keys this system can belong to
    """

    key: int
    title: str
    life_expectancy: int
    facility_keys: tuple[int, ...]  # Immutable tuple for frozen dataclass

    @property
    def life_expectancy_months(self) -> int:
        """Life expectancy in months."""
        return self.life_expectancy * 12

    def belongs_to_facility(self, facility_key: int) -> bool:
        """Check if this system type belongs to a facility type."""
        return facility_key in self.facility_keys
