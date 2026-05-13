"""Integration tests for generation hierarchy and export outputs."""

from datetime import datetime
from pathlib import Path

import pytest

from src.config import MidasConfigData, MidasSettings
from src.enums import UFCGrade, WO_Priority, WO_Status
from src.io import DataExporter, DataTransformer
from src.models import Facility, System
from src.simulation import DataGenerator
from src.simulation.data_generation.work_order_generator import WorkOrderGenerator

# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


def test_generate_installations_hierarchy_shape_is_consistent() -> None:
    """Generated entities should preserve parent-child ID relationships."""
    generator = DataGenerator(seed=42)
    result = generator.generate_installations(2)

    assert len(result.installations) == 2
    assert result.facilities
    assert result.systems

    installation_ids = {installation.id for installation in result.installations}
    facility_ids = {facility.id for facility in result.facilities}
    system_ids = {system.id for system in result.systems}

    for facility in result.facilities:
        assert facility.installation_id in installation_ids

    for system in result.systems:
        assert system.facility_id in facility_ids

    for work_order in result.work_orders:
        assert work_order.system_id in system_ids
        if work_order.facility_id is not None:
            assert work_order.facility_id in facility_ids
        if work_order.installation_id is not None:
            assert work_order.installation_id in installation_ids


@pytest.mark.parametrize(
    ("output_format", "layout"),
    [
        ("csv", "normalized"),
        ("csv", "denormalized"),
        ("xlsx", "normalized"),
        ("xlsx", "denormalized"),
    ],
)
def test_export_matrix_writes_expected_files(tmp_path: Path, output_format: str, layout: str) -> None:
    """Exporter should produce files for each supported format/layout combination."""
    file_name = f"integration_{output_format}_{layout}"
    exporter = DataExporter(
        file_name=file_name,
        output_format=output_format,
        output_directory=tmp_path,
        layout=layout,
        generate_metadata=True,
    )

    output_path = exporter.generate_and_export(method="installations", target_count=2)
    output_dir = output_path.parent

    assert output_dir.exists()

    if output_format == "csv":
        csv_files = list(output_dir.glob("*.csv"))
        assert csv_files, f"Expected CSV output files in {output_dir}"
        assert exporter.metadata_path.exists(), "Expected JSON metadata file for CSV export"
    else:
        assert output_path.exists(), f"Expected Excel file at {output_path}"
        assert output_path.suffix == ".xlsx"
        assert not exporter.metadata_path.exists(), "Excel metadata should be written as a sheet, not a JSON sidecar"


@pytest.mark.parametrize("method", ["installations", "facilities"])
def test_generate_and_export_requires_target_count_for_count_methods(tmp_path: Path, method: str) -> None:
    """Methods that require explicit counts should raise clear errors when missing."""
    exporter = DataExporter(
        file_name="integration_missing_count",
        output_format="csv",
        output_directory=tmp_path,
        layout="normalized",
    )

    with pytest.raises(ValueError, match="target_count is required"):
        exporter.generate_and_export(method=method)


def test_work_order_generation_is_age_correlated_and_lifecycle_consistent() -> None:
    """Older systems should generate more work orders with valid lifecycle fields."""
    config_data = MidasConfigData()
    generator = WorkOrderGenerator(seed=123)
    first_system_type_key = next(iter(config_data.system_types))

    old_system = System(
        system_type_key=first_system_type_key,
        year_constructed=1980,
        facility_id="fac-old",
    )
    new_system = System(
        system_type_key=first_system_type_key,
        year_constructed=datetime.now().year - 2,
        facility_id="fac-new",
    )

    old_total = 0
    new_total = 0
    seen_statuses: set[WO_Status] = set()
    seen_priorities: set[WO_Priority] = set()
    seen_requesting_orgs: set[str] = set()
    for _ in range(120):
        old_work_orders = generator.generate_by_system(old_system)
        new_work_orders = generator.generate_by_system(new_system)
        old_total += len(old_work_orders)
        new_total += len(new_work_orders)

        for work_order in old_work_orders + new_work_orders:
            assert isinstance(work_order.status, WO_Status)
            assert isinstance(work_order.priority, WO_Priority)
            assert work_order.requesting_organization in {
                "J1",
                "J2",
                "J3",
                "J4",
                "J5",
                "J6",
            }
            assert isinstance(work_order.impacts_mission, bool)
            assert work_order.request_datetime is not None
            assert work_order.request_datetime <= datetime.now()
            assert work_order.request_datetime.year >= (
                old_system.year_constructed if work_order.system_id == old_system.id else new_system.year_constructed
            )
            seen_statuses.add(work_order.status)
            seen_priorities.add(work_order.priority)
            seen_requesting_orgs.add(work_order.requesting_organization)

            assert work_order.problem_description is not None
            assert work_order.requested_action is not None

            if work_order.status in {WO_Status.SUBMITTED, WO_Status.APPROVED}:
                assert work_order.actions_taken is None
                assert work_order.completion_datetime is None
            elif work_order.status == WO_Status.IN_PROGRESS:
                assert work_order.completion_datetime is None
            else:
                assert work_order.actions_taken is not None
                assert work_order.completion_datetime is not None
                assert work_order.completion_datetime >= work_order.request_datetime
                assert work_order.completion_datetime <= datetime.now()

    assert old_total > new_total
    assert len(seen_statuses) > 1, "Expected multiple work-order statuses across the generated history"
    assert len(seen_priorities) > 1, "Expected multiple work-order priorities across the generated history"
    assert len(seen_requesting_orgs) > 1, "Expected multiple requesting organizations across the generated history"


def test_normalized_export_uses_renamed_requesting_organization_field() -> None:
    """Normalized work-order table should expose renamed organization column."""
    result = DataGenerator(seed=42).generate_installations(1)
    tables = DataTransformer().create_normalized_tables(
        installations=result.installations,
        facilities=result.facilities,
        systems=result.systems,
        work_orders=result.work_orders,
    )
    work_orders_table = tables["work_orders"]
    assert work_orders_table is not None
    assert "requesting_organization" in work_orders_table.columns


# ---------------------------------------------------------------------------
# Config-driven generation bounds
# ---------------------------------------------------------------------------


def test_facility_count_within_configured_range() -> None:
    """Facility count per installation should respect facilities_per_installation range."""
    settings = MidasSettings()
    low, high = settings.get_value("facilities_per_installation")
    generator = DataGenerator(seed=7)

    for _ in range(5):
        result = generator.generate_installation()
        facility_count = len(result.facilities)
        assert low <= facility_count <= high, f"Expected {low}-{high} facilities, got {facility_count}"


def test_system_ages_within_configured_max() -> None:
    """Every generated system's age should not exceed maximum_system_age."""
    settings = MidasSettings()
    max_age = settings.get_value("maximum_system_age")
    result = DataGenerator(seed=42).generate_installations(2)

    for system in result.systems:
        assert system.age_years is not None
        assert system.age_years <= max_age, f"System age {system.age_years} exceeds max {max_age}"


def test_facility_ages_within_configured_max() -> None:
    """Every generated facility's age should not exceed maximum_facility_age."""
    settings = MidasSettings()
    max_age = settings.get_value("maximum_facility_age")
    result = DataGenerator(seed=42).generate_installations(2)

    for facility in result.facilities:
        assert facility.age_years is not None
        assert facility.age_years <= max_age, f"Facility age {facility.age_years} exceeds max {max_age}"


def test_sampled_condition_indices_within_bounds() -> None:
    """All system condition indices should be in [0, 100]."""
    result = DataGenerator(seed=42).generate_installations(3)

    for system in result.systems:
        assert system.condition_index is not None
        assert 0 <= system.condition_index <= 100, f"System CI {system.condition_index} out of [0, 100]"


# ---------------------------------------------------------------------------
# System-type-to-facility-type mapping
# ---------------------------------------------------------------------------


def test_system_types_belong_to_parent_facility_type() -> None:
    """Each system's type should list its parent facility's type in facility_keys."""
    config_data = MidasConfigData()
    result = DataGenerator(seed=42).generate_installations(2)

    facility_map = {f.id: f for f in result.facilities}
    for system in result.systems:
        facility = facility_map.get(system.facility_id)
        assert facility is not None, f"System {system.id} has orphaned facility_id"

        system_type = config_data.get_system_type(system.system_type_key)
        assert system_type is not None, f"System {system.id} has unknown system_type_key {system.system_type_key}"

        assert facility.facility_type_key in system_type.facility_keys, (
            f"SystemType {system_type.key} ({system_type.title}) does not list "
            f"facility key {facility.facility_type_key} in its facility_keys {system_type.facility_keys}"
        )


# ---------------------------------------------------------------------------
# Condition index propagation
# ---------------------------------------------------------------------------


def test_condition_index_propagation_facility_is_avg_of_systems() -> None:
    """Facility CI should equal the rounded average of its child systems' CIs."""
    result = DataGenerator(seed=42).generate_installations(2)

    systems_by_facility: dict[str, list[System]] = {}
    for system in result.systems:
        systems_by_facility.setdefault(system.facility_id, []).append(system)

    for facility in result.facilities:
        child_systems = systems_by_facility.get(facility.id, [])
        if not child_systems:
            continue
        expected_ci = round(sum(s.condition_index for s in child_systems) / len(child_systems), 2)
        assert facility.condition_index == expected_ci, (
            f"Facility {facility.id} CI {facility.condition_index} != avg of system CIs {expected_ci}"
        )


def test_condition_index_propagation_installation_is_avg_of_facilities() -> None:
    """Installation CI should equal the rounded average of its child facilities' CIs."""
    result = DataGenerator(seed=42).generate_installations(2)

    facilities_by_install: dict[str, list[Facility]] = {}
    for facility in result.facilities:
        facilities_by_install.setdefault(facility.installation_id, []).append(facility)

    for installation in result.installations:
        child_facilities = facilities_by_install.get(installation.id, [])
        ci_values = [f.condition_index for f in child_facilities if f.condition_index is not None]
        if not ci_values:
            continue
        expected_ci = round(sum(ci_values) / len(ci_values), 2)
        assert installation.condition_index == expected_ci, (
            f"Installation {installation.id} CI {installation.condition_index} != avg of facility CIs {expected_ci}"
        )


# ---------------------------------------------------------------------------
# Dependency positions and resiliency grades
# ---------------------------------------------------------------------------


def test_all_facilities_have_resiliency_grade() -> None:
    """Every generated facility should have a non-None UFCGrade."""
    result = DataGenerator(seed=42).generate_installations(2)

    for facility in result.facilities:
        assert facility.resiliency_grade is not None, f"Facility {facility.id} has no resiliency_grade"
        assert isinstance(facility.resiliency_grade, UFCGrade), (
            f"Facility {facility.id} grade is {type(facility.resiliency_grade)}, expected UFCGrade"
        )


def test_dependency_positions_are_valid() -> None:
    """Facility dependency positions should use configured vertical levels and valid group_ids."""
    settings = MidasSettings()
    valid_levels = set(settings.get_dependency_chain_vertical_positions())
    result = DataGenerator(seed=42).generate_installations(2)

    for facility in result.facilities:
        pos = facility.dependency_position
        assert pos.vertical_position in valid_levels, (
            f"Facility {facility.id} vertical_position '{pos.vertical_position}' not in configured levels {valid_levels}"
        )
        for gid in pos.group_ids:
            assert 1 <= gid <= 9, f"Facility {facility.id} group_id {gid} out of range 1-9"


# ---------------------------------------------------------------------------
# Installation location data and single-install generation
# ---------------------------------------------------------------------------


def test_installation_uses_location_data_from_config() -> None:
    """Generated installations should carry location data from loaded config."""
    config_data = MidasConfigData()
    assert config_data.installation_locations, "Test requires loaded locations"

    result = DataGenerator(seed=42).generate_installations(3)
    for installation in result.installations:
        assert installation.title and installation.title.strip(), f"Installation {installation.id} has empty title"
        assert installation.location and installation.location.strip(), f"Installation {installation.id} has empty location"
        assert installation.region and installation.region.strip(), f"Installation {installation.id} has empty region"


def test_single_installation_generation_returns_valid_result() -> None:
    """DataGenerator.generate_installation() should produce exactly one installation."""
    result = DataGenerator(seed=99).generate_installation()

    assert len(result.installations) == 1
    assert result.facilities, "Expected at least one facility"
    assert result.systems, "Expected at least one system"

    installation = result.installations[0]
    assert installation.facility_ids
    assert len(installation.facility_ids) == len(result.facilities)

    facility_ids = {f.id for f in result.facilities}
    for fid in installation.facility_ids:
        assert fid in facility_ids
