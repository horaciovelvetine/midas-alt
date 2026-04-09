"""Vertical depth and shared dependency groups for facilities."""

import string
from dataclasses import dataclass, field

# All valid vertical positions (A-Z)
VERTICAL_POSITIONS = list(string.ascii_uppercase)


@dataclass
class DependencyPosition:
    """Represents an entity's position in a dependency hierarchy.

    Members belong to a containing-class entity (e.g. Installation -> Facilities).

    Position format: "{vertical_position}{group_ids}" e.g. "A1" or "B12"
      - vertical_position: a single letter "A"-"Z", where "A" is the top of the
        hierarchy and each subsequent letter represents a deeper dependency level.
      - group_ids: any combination of integers 1-9, each representing membership
        in one of 9 possible groups. Entities sharing a group_id within the same
        hierarchy are considered related.

    Hierarchy rule: an entity at position N (e.g. "B") depends on entities at
    positions above it (e.g. "A") that share at least one group_id.
    """

    vertical_position: str = "A"
    group_ids: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate and normalize."""
        self.vertical_position = self.vertical_position.upper()
        if self.vertical_position not in VERTICAL_POSITIONS:
            raise ValueError(
                f"vertical_position must be a single letter A-Z, got '{self.vertical_position}'"
            )
        if any(g < 1 or g > 9 for g in self.group_ids):
            raise ValueError(f"group_ids must be integers 1-9, got {self.group_ids}")

    def __str__(self) -> str:
        """Format as position string, e.g. 'A1', 'B23'."""
        groups = "".join(str(g) for g in sorted(self.group_ids))
        return f"{self.vertical_position}{groups}"

    @property
    def depth(self) -> int:
        """Return the 0-based depth of this position (A=0, B=1, ...)."""
        return ord(self.vertical_position) - ord("A")

    def has_shared_group(self, other: "DependencyPosition") -> bool:
        """Check if this position shares at least one group with another."""
        return bool(set(self.group_ids) & set(other.group_ids))

    def is_above(self, other: "DependencyPosition") -> bool:
        """Check if this position is higher in the hierarchy than another."""
        return self.depth < other.depth

    @classmethod
    def from_string(cls, position_str: str) -> "DependencyPosition":
        """Parse a position string like 'A1', 'B23' into a DependencyPosition."""
        if not position_str or len(position_str) < 1:
            raise ValueError(f"Invalid position string: '{position_str}'")
        vertical = position_str[0].upper()
        group_ids = [int(c) for c in position_str[1:] if c.isdigit()]
        return cls(vertical_position=vertical, group_ids=group_ids)
