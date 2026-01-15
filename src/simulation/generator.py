"""Data generator for creating simulated installations, facilities, and systems.

This module creates domain entities with realistic simulated values
for use in training ML models and testing the application.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

from ..config.settings import MIDASSettings
from ..domain import DependencyChain, DependencyTier, Facility, Installation, System, UFCGrade
from .distributions import ProbabilityDistribution, ProbabilitySegment


class DegradationPattern(Enum):
    """Types of degradation curves for simulation."""

    LINEAR = "linear"  # Steady decline
    EXPONENTIAL = "exponential"  # Accelerating decline
    STEPPED = "stepped"  # Sudden drops
    BATHTUB = "bathtub"  # Early failures, stable, then wear-out


@dataclass
class SimpleSegment:
    """A simple segment for probability distributions (dataclass version)."""

    probability: float  # 0-100
    min_value: float
    max_value: float

    def sample(self) -> float:
        """Sample a random value from this segment."""
        return random.uniform(self.min_value, self.max_value)


@dataclass
class SimulationConfig:
    """Configuration for data generation."""

    # Range settings
    facilities_per_installation: tuple[int, int] = (8, 14)
    dependency_group_range: tuple[int, int] = (1, 3)
    max_facility_age: int = 80
    max_system_age: int = 80

    # Probability distributions (using SimpleSegment dataclass)
    condition_index_distribution: list[SimpleSegment] = field(
        default_factory=lambda: [
            SimpleSegment(7, 1, 50),
            SimpleSegment(88, 50, 85),
            SimpleSegment(5, 85, 100),
        ]
    )

    age_distribution: list[SimpleSegment] = field(
        default_factory=lambda: [
            SimpleSegment(10, 0, 9),
            SimpleSegment(20, 10, 20),
            SimpleSegment(50, 20, 40),
            SimpleSegment(20, 41, 80),
        ]
    )

    grade_distribution: list[SimpleSegment] = field(
        default_factory=lambda: [
            SimpleSegment(52, 1, 1),
            SimpleSegment(32, 2, 2),
            SimpleSegment(12, 3, 3),
            SimpleSegment(4, 4, 4),
        ]
    )

    @classmethod
    def from_settings(cls, settings: MIDASSettings) -> "SimulationConfig":
        """Create SimulationConfig from MIDASSettings."""
        return cls(
            facilities_per_installation=settings.simulation.facilities_per_installation,
            dependency_group_range=settings.simulation.dependency_chain_group_range,
            max_facility_age=settings.simulation.maximum_facility_age,
            max_system_age=settings.simulation.maximum_system_age,
        )


class DataGenerator:
    """Generates simulated domain entities for training and testing."""

    def __init__(
        self,
        settings: MIDASSettings | None = None,
        config: SimulationConfig | None = None,
        seed: int | None = None,
    ):
        """Initialize the generator.

        Args:
            settings: Application settings (for reference data lookup).
            config: Simulation configuration. If None, uses defaults.
            seed: Random seed for reproducibility.
        """
        self.settings = settings or MIDASSettings.with_defaults()
        self.config = config or SimulationConfig.from_settings(self.settings)

        if seed is not None:
            random.seed(seed)

    def generate_installation(self) -> tuple[Installation, list[Facility], list[System]]:
        """Generate a complete installation with facilities and systems.

        Returns:
            Tuple of (installation, facilities, systems).
        """
        installation = Installation(
            id=str(uuid4()),
            title=f"SIM_INSTALL_{str(uuid4())[:8]}",
        )

        # Generate facilities
        facility_count = random.randint(*self.config.facilities_per_installation)
        facilities, all_systems = self._generate_facilities(
            installation.id, facility_count
        )

        # Update installation with facility IDs
        installation.facility_ids = [f.id for f in facilities]

        # Calculate installation condition index (average of facilities)
        ci_values = [f.condition_index for f in facilities if f.condition_index]
        if ci_values:
            installation.condition_index = round(sum(ci_values) / len(ci_values), 2)

        # Assign resiliency grades based on dependencies
        self._assign_resiliency_grades(facilities)

        return installation, facilities, all_systems

    def generate_installations(
        self, count: int
    ) -> tuple[list[Installation], list[Facility], list[System]]:
        """Generate multiple installations.

        Args:
            count: Number of installations to generate.

        Returns:
            Tuple of (installations, all_facilities, all_systems).
        """
        all_installations = []
        all_facilities = []
        all_systems = []

        for _ in range(count):
            installation, facilities, systems = self.generate_installation()
            all_installations.append(installation)
            all_facilities.extend(facilities)
            all_systems.extend(systems)

        return all_installations, all_facilities, all_systems

    def _generate_facilities(
        self, installation_id: str, count: int
    ) -> tuple[list[Facility], list[System]]:
        """Generate facilities for an installation."""
        facilities = []
        all_systems = []
        used_facility_type_keys: list[int] = []

        # Generate dependency chains
        dependency_chains = self._generate_dependency_chains(count)

        # Get available facility types
        available_types = list(self.settings.facility_types.keys())

        for i in range(count):
            # Select facility type (prefer unused)
            if available_types:
                available_for_selection = [
                    k for k in available_types if k not in used_facility_type_keys
                ]
                if not available_for_selection:
                    available_for_selection = available_types
                facility_type_key = random.choice(available_for_selection)
                used_facility_type_keys.append(facility_type_key)
            else:
                facility_type_key = random.randint(1, 20)

            # Create facility
            facility = Facility(
                id=str(uuid4()),
                facility_type_key=facility_type_key,
                year_constructed=self._sample_year_constructed(
                    self.config.max_facility_age
                ),
                dependency_chain=dependency_chains[i] if i < len(dependency_chains) else DependencyChain(),
                installation_id=installation_id,
            )

            # Generate systems for this facility
            systems = self._generate_systems(facility)
            facility.system_ids = [s.id for s in systems]

            # Calculate facility condition index from systems
            ci_values = [s.condition_index for s in systems if s.condition_index]
            if ci_values:
                facility.condition_index = round(sum(ci_values) / len(ci_values), 2)

            facilities.append(facility)
            all_systems.extend(systems)

        return facilities, all_systems

    def _generate_systems(self, facility: Facility) -> list[System]:
        """Generate systems for a facility."""
        systems = []

        # Get system types for this facility
        system_types = self.settings.get_system_types_for_facility(
            facility.facility_type_key or 0
        )

        # If no system types defined, generate random systems
        if not system_types:
            system_count = random.randint(3, 8)
            for i in range(system_count):
                system = System(
                    id=str(uuid4()),
                    system_type_key=i + 1,
                    year_constructed=self._sample_year_constructed(
                        self.config.max_system_age
                    ),
                    condition_index=self._sample_condition_index(),
                    facility_id=facility.id,
                )
                systems.append(system)
        else:
            # Generate one system per type
            for system_type in system_types:
                system = System(
                    id=str(uuid4()),
                    system_type_key=system_type.key,
                    year_constructed=self._sample_year_constructed(
                        self.config.max_system_age
                    ),
                    condition_index=self._sample_condition_index(),
                    facility_id=facility.id,
                )
                systems.append(system)

        return systems

    def _generate_dependency_chains(self, count: int) -> list[DependencyChain]:
        """Generate valid dependency chains for a set of facilities."""
        if count == 0:
            return []

        if count == 1:
            return [DependencyChain(tier=DependencyTier.PRIMARY, group_ids=[1])]

        chains = []
        group_range = self.config.dependency_group_range

        for _ in range(count):
            tier = random.choice(list(DependencyTier))
            group_count = random.randint(*group_range)
            group_ids = sorted(
                random.sample(
                    range(group_range[0], group_range[1] + 1),
                    min(group_count, group_range[1] - group_range[0] + 1),
                )
            )
            chains.append(DependencyChain(tier=tier, group_ids=group_ids))

        # Validate and fix chains
        return self._validate_dependency_chains(chains)

    def _validate_dependency_chains(
        self, chains: list[DependencyChain]
    ) -> list[DependencyChain]:
        """Ensure dependency chains form valid hierarchies."""
        # Count tiers per group
        from collections import defaultdict

        for _ in range(10):  # Max iterations to prevent infinite loop
            group_tiers = defaultdict(lambda: {"P": 0, "S": 0, "T": 0})

            for chain in chains:
                if chain.tier:
                    for gid in chain.group_ids:
                        group_tiers[gid][chain.tier.value] += 1

            fixed = True
            new_chains = []

            for chain in chains:
                if chain.tier is None:
                    new_chains.append(chain)
                    continue

                needs_fix = False

                # Check for floaters (S or T with no support)
                if chain.tier in [DependencyTier.SECONDARY, DependencyTier.TERTIARY]:
                    has_support = False
                    for gid in chain.group_ids:
                        if chain.tier == DependencyTier.SECONDARY:
                            if group_tiers[gid]["P"] > 0:
                                has_support = True
                                break
                        elif chain.tier == DependencyTier.TERTIARY:
                            if group_tiers[gid]["P"] > 0 or group_tiers[gid]["S"] > 0:
                                has_support = True
                                break

                    if not has_support:
                        # Elevate to Primary
                        new_chains.append(
                            DependencyChain(
                                tier=DependencyTier.PRIMARY,
                                group_ids=[chain.group_ids[0]] if chain.group_ids else [1],
                            )
                        )
                        fixed = False
                        needs_fix = True

                if not needs_fix:
                    new_chains.append(chain)

            chains = new_chains

            if fixed:
                break

        return chains

    def _assign_resiliency_grades(self, facilities: list[Facility]) -> None:
        """Assign resiliency grades based on dependency relationships."""
        # Group by tier
        by_tier = {tier: [] for tier in DependencyTier}
        for f in facilities:
            if f.dependency_chain.tier:
                by_tier[f.dependency_chain.tier].append(f)

        # Assign grades bottom-up
        # Tertiary: Random grades
        for f in by_tier[DependencyTier.TERTIARY]:
            f.resiliency_grade = self._sample_grade()

        # Secondary: Based on tertiary dependents
        for f in by_tier[DependencyTier.SECONDARY]:
            dependents = self._find_dependents(f, facilities, DependencyTier.TERTIARY)
            f.resiliency_grade = self._calculate_grade_from_dependents(dependents)

        # Primary: Based on all dependents
        for f in by_tier[DependencyTier.PRIMARY]:
            t_deps = self._find_dependents(f, facilities, DependencyTier.TERTIARY)
            s_deps = self._find_dependents(f, facilities, DependencyTier.SECONDARY)
            f.resiliency_grade = self._calculate_grade_from_dependents(t_deps + s_deps)

    def _find_dependents(
        self,
        facility: Facility,
        all_facilities: list[Facility],
        target_tier: DependencyTier,
    ) -> list[Facility]:
        """Find facilities that depend on the given facility."""
        dependents = []
        for other in all_facilities:
            if other.dependency_chain.tier == target_tier:
                if facility.dependency_chain.depends_on(other.dependency_chain):
                    dependents.append(other)
        return dependents

    def _calculate_grade_from_dependents(
        self, dependents: list[Facility]
    ) -> UFCGrade:
        """Calculate grade based on dependent facilities' grades."""
        if not dependents:
            return self._sample_grade()

        grades = [f.resiliency_grade.value for f in dependents if f.resiliency_grade]
        if not grades:
            return UFCGrade.G1

        # Use majority rule with 70% threshold
        total = len(grades)

        if sum(1 for g in grades if g >= 4) / total >= 0.7:
            return UFCGrade.G4
        if sum(1 for g in grades if g >= 3) / total >= 0.7:
            return UFCGrade.G3
        if sum(1 for g in grades if g >= 2) / total >= 0.7:
            return UFCGrade.G2

        return UFCGrade.G1

    def _sample_condition_index(self) -> float:
        """Sample a condition index from the distribution."""
        return round(self._sample_from_distribution(
            self.config.condition_index_distribution
        ), 2)

    def _sample_year_constructed(self, max_age: int) -> int:
        """Sample a year constructed based on age distribution."""
        age = int(self._sample_from_distribution(self.config.age_distribution))
        age = min(age, max_age)
        return datetime.now().year - age

    def _sample_grade(self) -> UFCGrade:
        """Sample a UFC grade from the distribution."""
        grade_value = int(
            self._sample_from_distribution(self.config.grade_distribution)
        )
        return UFCGrade(min(max(grade_value, 1), 4))

    def _sample_from_distribution(
        self, distribution: list[SimpleSegment]
    ) -> float:
        """Sample a value from a probability distribution."""
        total_prob = sum(s.probability for s in distribution)
        r = random.uniform(0, total_prob)

        cumulative = 0
        for segment in distribution:
            cumulative += segment.probability
            if r <= cumulative:
                return segment.sample()

        # Fallback to last segment
        return distribution[-1].sample() if distribution else 50.0
