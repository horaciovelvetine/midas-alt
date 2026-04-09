"""Reference row for a facility archetype from the configuration workbook."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FacilityType:
    """Workbook-defined facility archetype (life expectancy, mission criticality)."""

    key: int
    title: str
    life_expectancy: int
    mission_criticality: int = 1

    @property
    def life_expectancy_months(self) -> int:
        """Life expectancy in months."""
        return self.life_expectancy * 12
