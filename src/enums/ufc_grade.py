"""UFC 4-141-03 resiliency grades (G1–G4) for facilities."""

from enum import Enum


class UFCGrade(Enum):
    """As Defined By: UFC 4-141-03: https://www.wbdg.org/FFC/DOD/UFC/ufc_4_141_03_2024.pdf.

    Enumerates the resiliency grading system for facilities based on redundancy,
    maintainability, and fault-tolerance as defined in DoD and industry standards.

    - G1: No redundant capacity components or redundant distribution pathways.
          Maintenance or failures result in downtime. Comparable to Uptime Institute's
          Tier I, ANSI/TIA-942-B I, ANSI/BICSI 002 Class F1.
    - G2: Single paths to critical loads with some component redundancy
          (but not system-level redundancy). Planned maintenance only possible
          for redundant components. Downtime likely for failures. Comparable to
          Tier II, ANSI/TIA-942-B II, ANSI/BICSI 002 Class F2.
    - G3: Concurrently maintainable, redundant components for critical operations.
          Operations sustained for any scheduled maintenance routine. Systems
          typically N+1 at minimum. Comparable to Tier III, ANSI/TIA-942-B III,
          ANSI/BICSI 002 Class F3.
    - G4: Fault-tolerant facilities with physically isolated redundant paths for
          all critical operations and automatic fault response. Can withstand a
          single failure during operation, but may lose operation if failure occurs
          during maintenance. Systems are 2N or higher. Comparable to Tier IV,
          ANSI/TIA-942-B IV, ANSI/BICSI 002 Class F4.
    """

    G1 = "1"
    """No redundant components or pathways; failures typically cause downtime."""

    G2 = "2"
    """Single path with partial component redundancy; downtime remains likely."""

    G3 = "3"
    """Concurrently maintainable with N+1-style redundancy for critical operations."""

    G4 = "4"
    """Fault-tolerant, isolated redundant paths with automatic fault response."""

    @classmethod
    def from_value(cls, value: int | str) -> "UFCGrade | None":
        """Get grade from integer or string value."""
        try:
            int_val = int(value)
            return cls(str(int_val))
        except (ValueError, TypeError):
            return None
