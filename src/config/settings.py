"""Immutable configuration settings for MIDAS.

Configuration is loaded once and passed to services via dependency injection.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .reference_data import FacilityType, SystemType

if TYPE_CHECKING:
    from ..simulation.distributions import ProbabilityDistribution


@dataclass(frozen=True)
class DegradationSettings:
    """Settings related to degradation thresholds and calculations."""

    condition_index_degraded_threshold: float = 25.0
    resiliency_grade_threshold: int = 70
    initial_condition_index: float = 99.99
    max_time_series_years: int = 10


@dataclass(frozen=True)
class SimulationSettings:
    """Settings for data simulation/generation."""

    facilities_per_installation: tuple[int, int] = (8, 14)
    dependency_chain_group_range: tuple[int, int] = (1, 3)
    maximum_system_age: int = 80
    maximum_facility_age: int = 80
    facility_condition_randomly_degrades_chance: int = 35


@dataclass(frozen=True)
class OutputSettings:
    """Settings for data export/output."""

    json_indent: int = 2
    excel_sheet_main: str = "Main Data"
    excel_sheet_facility_ts: str = "Facility Time Series"
    excel_sheet_system_ts: str = "System Time Series"
    excel_sheet_metadata: str = "_metadata"
    metadata_file_suffix: str = "_metadata.json"
    csv_table_separator: str = "_"


@dataclass
class SimulationDistributions:
    """Probability distributions for simulation data generation.
    
    These distributions control how random values are generated for
    condition indices, ages, and resiliency grades.
    """
    
    condition_index: "ProbabilityDistribution | None" = None
    age: "ProbabilityDistribution | None" = None
    grade: "ProbabilityDistribution | None" = None
    
    def __post_init__(self) -> None:
        """Initialize default distributions if not provided."""
        from ..simulation.distributions import ProbabilityDistribution, ProbabilitySegment
        
        if self.condition_index is None:
            object.__setattr__(self, 'condition_index', ProbabilityDistribution([
                ProbabilitySegment(7, "1-50"),
                ProbabilitySegment(88, "50-85"),
                ProbabilitySegment(5, "85-100"),
            ]))
        
        if self.age is None:
            object.__setattr__(self, 'age', ProbabilityDistribution([
                ProbabilitySegment(50, "20-40"),
                ProbabilitySegment(20, "10-20"),
                ProbabilitySegment(20, "41-80"),
                ProbabilitySegment(10, "0-9"),
            ]))
        
        if self.grade is None:
            object.__setattr__(self, 'grade', ProbabilityDistribution([
                ProbabilitySegment(52, "1"),
                ProbabilitySegment(32, "2"),
                ProbabilitySegment(12, "3"),
                ProbabilitySegment(4, "4"),
            ]))


@dataclass
class MIDASSettings:
    """Main configuration container for MIDAS application.

    This is the single source of truth for configuration. Create once
    at application startup and pass to services.
    """

    degradation: DegradationSettings = field(default_factory=DegradationSettings)
    simulation: SimulationSettings = field(default_factory=SimulationSettings)
    output: OutputSettings = field(default_factory=OutputSettings)
    distributions: SimulationDistributions = field(default_factory=SimulationDistributions)

    # Reference data (loaded from Excel)
    facility_types: dict[int, FacilityType] = field(default_factory=dict)
    system_types: dict[int, SystemType] = field(default_factory=dict)

    def get_facility_type(self, key: int) -> FacilityType | None:
        """Get facility type by key."""
        return self.facility_types.get(key)

    def get_system_type(self, key: int) -> SystemType | None:
        """Get system type by key."""
        return self.system_types.get(key)

    def get_random_facility_type(self, excluded_keys: list[int] | None = None) -> FacilityType | None:
        """Get a random facility type, optionally excluding certain keys."""
        import random
        excluded = excluded_keys or []
        available = [ft for ft in self.facility_types.values() if ft.key not in excluded]
        return random.choice(available) if available else None

    def get_random_system_type_for_facility(self, facility_key: int) -> "SystemType | None":
        """Get a random system type that belongs to the given facility type."""
        import random
        system_types = self.get_system_types_for_facility(facility_key)
        return random.choice(system_types) if system_types else None

    def get_system_types_for_facility(self, facility_key: int) -> list[SystemType]:
        """Get all system types that belong to a facility type."""
        return [
            st for st in self.system_types.values() if facility_key in st.facility_keys
        ]

    @classmethod
    def with_defaults(cls) -> "MIDASSettings":
        """Create settings with all defaults (no reference data)."""
        return cls()

    @classmethod
    def from_excel(cls, path: Path) -> "MIDASSettings":
        """Load settings from Excel configuration file.

        Args:
            path: Path to midas_config_values.xlsx

        Returns:
            Configured MIDASSettings instance.
        """
        from .loader import load_settings_from_excel

        return load_settings_from_excel(path)
    
    @classmethod
    def default_config_path(cls) -> Path:
        """Get the default configuration file path."""
        return Path(__file__).parent / "midas_config_values.xlsx"
