"""Facility entity: systems, dependency placement, and aggregate condition."""

from dataclasses import dataclass, field
from datetime import datetime

from src.enums import UFCGrade
from src.functions import generate_id

from .dependency_position import DependencyPosition


@dataclass
class Facility:
    """Installation child asset grouping; aggregates condition from its systems."""

    id: str = field(default_factory=generate_id)

    # Type reference (key into reference data)
    facility_type_key: int | None = None
    # Denormalized from reference data at generation/load time (avoids global settings lookup).
    facility_type_title: str | None = None

    # Core attributes
    year_constructed: int | None = None
    dependency_position: DependencyPosition = field(default_factory=DependencyPosition)
    resiliency_grade: UFCGrade | None = None

    # Parent reference
    installation_id: str | None = None

    # Child references (IDs only, not objects)
    system_ids: list[str] = field(default_factory=list)

    # Computed/aggregate values (set by services)
    condition_index: float | None = None
    _age_months: int | None = field(default=None, repr=False)
    _life_expectancy_months: int | None = field(default=None, repr=False)
    _mission_criticality: int | None = field(default=None, repr=False)

    @property
    def age_years(self) -> int | None:
        """Calculate age in years from year_constructed."""
        if self._age_months is not None:
            return self._age_months // 12
        if self.year_constructed is None:
            return None
        return datetime.now().year - self.year_constructed

    @property
    def age_months(self) -> int | None:
        """Get age in months."""
        if self._age_months is not None:
            return self._age_months
        if self.year_constructed is None:
            return None
        now: datetime = datetime.now()
        years = now.year - self.year_constructed
        return years * 12 + now.month - 1

    @property
    def title(self) -> str | None:
        """Facility type display title (populated when the facility is generated or loaded)."""
        return self.facility_type_title
