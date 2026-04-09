"""Reference row for a system archetype and allowed parent facility types."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemType:
    """Workbook-defined system archetype and compatible facility type keys."""

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
