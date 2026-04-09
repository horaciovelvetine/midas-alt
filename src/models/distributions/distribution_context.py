"""Optional age, life expectancy, and condition context for samplers."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DistributionContext:
    """Optional runtime context used by lifecycle-aware distributions."""

    age_years: float | None = None
    life_expectancy_years: float | None = None
    condition_index: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_ratio(self) -> float | None:
        """Return normalized age ratio when possible."""
        if self.age_years is None or self.life_expectancy_years in (None, 0):
            return None
        return self.age_years / self.life_expectancy_years
