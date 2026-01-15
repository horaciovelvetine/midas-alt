"""Domain enumerations for MIDAS.

Contains all enums used throughout the domain model.
"""

from enum import Enum


class UFCGrade(Enum):
    """UFC 4-141-03 Resiliency Grades.

    Grades indicate facility redundancy and fault-tolerance levels:
    - G1: No redundancy, maintenance causes downtime
    - G2: Some component redundancy, single path to critical loads
    - G3: Concurrently maintainable, N+1 redundancy
    - G4: Fault-tolerant, 2N redundancy with automatic failover
    """

    G1 = 1
    G2 = 2
    G3 = 3
    G4 = 4

    @classmethod
    def from_value(cls, value: int | str) -> "UFCGrade | None":
        """Get grade from integer or string value."""
        try:
            int_val = int(value)
            return cls(int_val)
        except (ValueError, TypeError):
            return None


class DependencyTier(Enum):
    """Facility dependency hierarchy tiers.

    Hierarchy (top to bottom):
    - PRIMARY: Top-level facilities with no dependencies
    - SECONDARY: Mid-level, depends on Primary
    - TERTIARY: Bottom-level, depends on Secondary or Primary
    """

    PRIMARY = "P"
    SECONDARY = "S"
    TERTIARY = "T"

    @classmethod
    def from_value(cls, value: str) -> "DependencyTier | None":
        """Get tier from string value (first character)."""
        if not value:
            return None
        char = value[0].upper()
        for tier in cls:
            if tier.value == char:
                return tier
        return None

    @classmethod
    def ordered(cls) -> list["DependencyTier"]:
        """Return tiers in hierarchical order (top to bottom)."""
        return [cls.PRIMARY, cls.SECONDARY, cls.TERTIARY]


class EntityType(Enum):
    """Type of domain entity for ML feature extraction."""

    INSTALLATION = "installation"
    FACILITY = "facility"
    SYSTEM = "system"
