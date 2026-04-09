"""Maintainable system asset under a facility (condition, type, work orders)."""

from dataclasses import dataclass, field
from datetime import datetime

from src.functions import generate_id

from .work_order import WorkOrder


@dataclass
class System:
    """Leaf asset with direct condition index, type key, and embedded work orders."""

    id: str = field(default_factory=generate_id)

    # Type reference (key into reference data)
    system_type_key: int | None = None

    # Core attributes
    year_constructed: int | None = None
    condition_index: float | None = None

    # Parent reference
    facility_id: str | None = None

    # Computed properties (set by services, cached here)
    _age_months: int | None = field(default=None, repr=False)
    _life_expectancy_months: int | None = field(default=None, repr=False)

    # Store associated work order ID's
    work_orders: list[WorkOrder] = field(default_factory=list)

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
        """Get age in months (computed or cached)."""
        if self._age_months is not None:
            return self._age_months
        if self.year_constructed is None:
            return None
        now = datetime.now()
        years = now.year - self.year_constructed
        return years * 12 + now.month - 1
