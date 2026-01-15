"""Domain entities for MIDAS.

Pure data containers with no business logic. All computation is handled
by services in the prediction/ and simulation/ modules.
"""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from .enums import DependencyTier, UFCGrade


def _generate_id() -> str:
    """Generate a unique identifier."""
    return str(uuid4())


@dataclass
class DependencyChain:
    """Represents a facility's position in the dependency hierarchy.

    Position format: "{tier}{group_ids}" e.g., "P12" = Primary, groups 1 and 2
    """

    tier: DependencyTier | None = None
    group_ids: list[int] = field(default_factory=list)

    @property
    def position(self) -> str | None:
        """Get position string (e.g., 'P12')."""
        if self.tier is None or not self.group_ids:
            return None
        return f"{self.tier.value}{''.join(str(g) for g in sorted(self.group_ids))}"

    @classmethod
    def from_position(cls, position: str | None) -> "DependencyChain":
        """Parse position string into DependencyChain."""
        if not position:
            return cls()

        tier = DependencyTier.from_value(position)
        if tier is None:
            return cls()

        # Extract digits as group IDs
        group_ids = [int(ch) for ch in position[1:] if ch.isdigit()]
        return cls(tier=tier, group_ids=group_ids)

    def depends_on(self, other: "DependencyChain") -> bool:
        """Check if this chain depends on another (is higher in hierarchy)."""
        if self.tier is None or other.tier is None:
            return False

        ordered = DependencyTier.ordered()
        self_idx = ordered.index(self.tier)
        other_idx = ordered.index(other.tier)

        # Must be higher in chain (lower index) and share group IDs
        if self_idx >= other_idx:
            return False

        return bool(set(self.group_ids) & set(other.group_ids))


@dataclass
class System:
    """A system within a facility.

    Systems are the lowest level of the hierarchy and have directly
    measured/simulated condition indices.
    """

    id: str = field(default_factory=_generate_id)

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

    @property
    def age_years(self) -> int | None:
        """Calculate age in years from year_constructed."""
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


@dataclass
class Facility:
    """A facility within an installation.

    Facilities contain systems and have aggregate condition indices
    calculated from their systems.
    """

    id: str = field(default_factory=_generate_id)

    # Type reference (key into reference data)
    facility_type_key: int | None = None

    # Core attributes
    year_constructed: int | None = None
    dependency_chain: DependencyChain = field(default_factory=DependencyChain)
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
        now = datetime.now()
        years = now.year - self.year_constructed
        return years * 12 + now.month - 1

    @property
    def dependency_tier(self) -> DependencyTier | None:
        """Get dependency tier shortcut."""
        return self.dependency_chain.tier

    @property
    def dependency_position(self) -> str | None:
        """Get dependency position string shortcut."""
        return self.dependency_chain.position


@dataclass
class Installation:
    """An installation containing multiple facilities.

    Top level of the domain hierarchy.
    """

    id: str = field(default_factory=_generate_id)
    title: str = ""

    # Child references (IDs only)
    facility_ids: list[str] = field(default_factory=list)

    # Computed/aggregate values (set by services)
    condition_index: float | None = None


# Type alias for any entity that can have condition index predicted
PredictableEntity = Facility | System
