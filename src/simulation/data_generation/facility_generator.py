"""Create facilities, dependency positions, and child systems/work orders."""

from collections import defaultdict

from src.enums import UFCGrade
from src.functions import generate_id
from src.models import DependencyPosition, Facility, System, WorkOrder

from .data_generator_base import DataGeneratorBase
from .system_generator import SystemGenerator


class FacilityGenerator(DataGeneratorBase):
    """Generate facilities and their descendant entities for installations."""

    def __init__(self, seed: int | None = None) -> None:
        """Initialize facility generator with optional seed."""
        super().__init__(seed=seed)

    def generate_by_count(
        self, installation_id: str, count: int
    ) -> tuple[list[Facility], list[System], list[WorkOrder]]:
        """Generate facility hierarchies for a single installation."""
        if count <= 0:
            return [], [], []

        all_facility: list[Facility] = []
        all_systems: list[System] = []
        all_work_orders: list[WorkOrder] = []
        created_facility_type_keys: list[int] = []
        available_facility_types = list(self.config_data.facility_types.keys())
        dependency_positions = self._generate_dependency_position_set(count)
        system_generator = SystemGenerator(seed=None)
        max_facility_age = self.settings.get_value("maximum_facility_age")

        for idx in range(count):
            if available_facility_types:
                uncreated = [
                    key
                    for key in available_facility_types
                    if key not in created_facility_type_keys
                ]
                candidate_pool = uncreated if uncreated else available_facility_types
                facility_type_key = self.random_choice(candidate_pool)
            else:
                facility_type_key = idx + 1

            created_facility_type_keys.append(facility_type_key)
            facility_type = self.config_data.get_facility_type(facility_type_key or 0)
            facility = Facility(
                id=generate_id(),
                installation_id=installation_id,
                facility_type_key=facility_type_key,
                facility_type_title=facility_type.title if facility_type else None,
                year_constructed=self.sample_year_constructed(max_facility_age),
                dependency_position=dependency_positions[idx],
            )

            generated_systems, generated_work_orders = (
                system_generator.generate_by_facility(facility)
            )
            for work_order in generated_work_orders:
                work_order.installation_id = installation_id
            facility.system_ids = [system.id for system in generated_systems]
            facility.condition_index = self.average_condition_index(generated_systems)

            all_facility.append(facility)
            all_systems.extend(generated_systems)
            all_work_orders.extend(generated_work_orders)

        self._assign_resiliency_grades(all_facility)
        return all_facility, all_systems, all_work_orders

    def _generate_dependency_position_set(self, count: int) -> list[DependencyPosition]:
        """Generate a validated set of dependency positions for a given count."""
        positions: list[DependencyPosition] = []
        if count == 0:
            return positions
        if count == 1:
            return [DependencyPosition(vertical_position="A", group_ids=[1])]

        for _ in range(count):
            vertical_position = (
                self.settings.get_random_dependency_chain_vertical_position()
            )
            group_ids = self.settings.get_random_dependency_chain_group_ids()
            positions.append(
                DependencyPosition(
                    vertical_position=vertical_position, group_ids=group_ids
                )
            )
        return self._validate_dependency_positions_set(positions=positions)

    def _validate_dependency_positions_set(
        self, positions: list[DependencyPosition]
    ) -> list[DependencyPosition]:
        """Ensure dependency positions form valid hierarchies."""
        for _ in range(10):
            group_levels: dict[int, set[str]] = defaultdict(set)
            for pos in positions:
                for gid in pos.group_ids:
                    group_levels[gid].add(pos.vertical_position)

            fixed = True
            new_positions: list[DependencyPosition] = []
            for pos in positions:
                if pos.vertical_position == "A":
                    new_positions.append(pos)
                    continue

                has_support = False
                for gid in pos.group_ids:
                    levels_in_group = group_levels[gid]
                    if any(level < pos.vertical_position for level in levels_in_group):
                        has_support = True
                        break

                if has_support:
                    new_positions.append(pos)
                else:
                    new_positions.append(
                        DependencyPosition(
                            vertical_position="A",
                            group_ids=[pos.group_ids[0]] if pos.group_ids else [1],
                        )
                    )
                    fixed = False

            positions = new_positions
            if fixed:
                break
        return positions

    def _assign_resiliency_grades(self, facilities: list[Facility]) -> None:
        """Assign resiliency grades based on dependency relationships."""
        levels = self.settings.get_dependency_chain_vertical_positions()
        facilities_by_level: dict[str, list[Facility]] = {level: [] for level in levels}

        for facility in facilities:
            level = facility.dependency_position.vertical_position
            if level in facilities_by_level:
                facilities_by_level[level].append(facility)

        for level in reversed(levels):
            deeper_levels = [candidate for candidate in levels if candidate > level]
            if not deeper_levels:
                for facility in facilities_by_level[level]:
                    facility.resiliency_grade = self.sample_ufc_resiliency_grade()
                continue

            for facility in facilities_by_level[level]:
                dependents = self._find_dependents(facility, facilities, deeper_levels)
                facility.resiliency_grade = self._calculate_grade_from_dependents(
                    dependents
                )

    def _find_dependents(
        self,
        facility: Facility,
        all_facilities: list[Facility],
        target_levels: list[str],
    ) -> list[Facility]:
        """Find facilities at target levels sharing at least one group ID."""
        results: list[Facility] = []
        for candidate in all_facilities:
            if candidate.dependency_position.vertical_position not in target_levels:
                continue
            if facility.dependency_position.has_shared_group(
                candidate.dependency_position
            ):
                results.append(candidate)
        return results

    def _calculate_grade_from_dependents(self, dependents: list[Facility]) -> UFCGrade:
        """Compute grade from dependent facility grades using threshold logic."""
        if not dependents:
            return self.sample_ufc_resiliency_grade()

        scores = [
            int(facility.resiliency_grade.value)
            for facility in dependents
            if facility.resiliency_grade
        ]
        if not scores:
            return UFCGrade.G1

        threshold_pct = self.settings.get_value("resiliency_grade_rating_threshold")
        threshold = max(0.0, min(1.0, threshold_pct / 100.0))
        total = len(scores)

        if sum(1 for score in scores if score >= 4) / total >= threshold:
            return UFCGrade.G4
        if sum(1 for score in scores if score >= 3) / total >= threshold:
            return UFCGrade.G3
        if sum(1 for score in scores if score >= 2) / total >= threshold:
            return UFCGrade.G2
        return UFCGrade.G1
