"""Integration tests for Excel-backed configuration loading."""

from pathlib import Path

import pytest

from src.config import (
    ApplicationState,
    MidasConfigData,
    MidasSettings,
    reset_app_state,
)
from src.enums import WO_Priority, WO_TradeSkill
from src.io import ConfigWorkbookLoadError, MidasConfigDataLoader
from src.models import WorkOrderText
from src.models.distributions import (
    EventRateDistribution,
    WeightedProbabilityDistribution,
)

# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


def test_default_config_path_exists() -> None:
    """Ensure the expected Excel configuration workbook is present."""
    config_path = MidasSettings.DEFAULT_CONFIG_DATA_PATH
    assert config_path.exists(), f"Expected config workbook at {config_path}"


def test_config_workbook_loader_populates_expected_containers() -> None:
    """Load reference data from workbook and verify core config shapes."""
    config_data = MidasConfigData()
    assert isinstance(config_data.facility_types, dict)
    assert isinstance(config_data.system_types, dict)
    assert isinstance(config_data.installation_locations, list)
    assert isinstance(config_data.config_workbook_path, Path)
    assert config_data.config_workbook_path.exists()

    assert config_data.facility_types, "Expected at least one facility type"
    assert config_data.system_types, "Expected at least one system type"
    assert config_data.installation_locations, "Expected at least one installation location"


def test_work_order_requesting_organization_distribution_is_available() -> None:
    """Requesting organization distribution should load from defaults/state file."""
    config_data = MidasConfigData()
    samples = {config_data.get_random_work_order_requesting_organization() for _ in range(24)}
    assert samples
    assert samples.issubset({"J1", "J2", "J3", "J4", "J5", "J6"})


def test_work_order_text_cache_uses_typed_samples() -> None:
    """Workbook-loaded work-order text should use the dedicated domain model when present."""
    config_data = MidasConfigData()

    valid_trades = {member.value for member in WO_TradeSkill}
    valid_categories = {member.value for member in WO_Priority}

    for sample_group in config_data.work_order_text_cache.values():
        assert sample_group
        for sample in sample_group:
            assert isinstance(sample, WorkOrderText)
            assert sample.trade in valid_trades, f"Unexpected trade: {sample.trade!r}"
            assert sample.work_category in valid_categories, f"Unexpected work category: {sample.work_category!r}"
            assert sample.priority_code is None or 1 <= sample.priority_code <= 4, (
                f"Unexpected priority code: {sample.priority_code!r}"
            )

    system_type_title = next(iter(config_data.system_types.values())).title
    sampled = config_data.sample_work_order_template(system_type_title)
    assert sampled is None or isinstance(sampled, WorkOrderText)


# ---------------------------------------------------------------------------
# Scalar settings defaults
# ---------------------------------------------------------------------------


def test_degradation_settings_values_have_valid_defaults() -> None:
    """Degradation-related setting states should have sane numeric defaults."""
    settings = MidasSettings()

    threshold = settings.get_value("condition_index_degraded_threshold")
    assert isinstance(threshold, (int, float))
    assert 0 < threshold <= 100

    resiliency = settings.get_value("resiliency_grade_rating_threshold")
    assert isinstance(resiliency, int)
    assert 0 < resiliency <= 100

    initial_ci = settings.get_value("initial_condition_index_default")
    assert isinstance(initial_ci, (int, float))
    assert 0 < initial_ci <= 100


def test_simulation_settings_values_have_valid_defaults() -> None:
    """Simulation-related setting states should expose valid ranges and helpers."""
    settings = MidasSettings()

    low, high = settings.get_value("facilities_per_installation")
    assert isinstance(low, int) and isinstance(high, int)
    assert 0 < low <= high

    dep_low, dep_high = settings.get_value("dependency_chain_group_range")
    assert isinstance(dep_low, int) and isinstance(dep_high, int)
    assert 0 <= dep_low <= dep_high

    max_depth = settings.get_value("maximum_vertical_dependency_depth")
    assert isinstance(max_depth, int) and max_depth > 0
    assert len(settings.get_dependency_chain_vertical_positions()) == max_depth

    assert settings.get_value("maximum_system_age") > 0
    assert settings.get_value("maximum_facility_age") > 0
    assert 0.0 <= settings.get_value("random_system_degradation_chance") <= 100.0
    assert 0.0 <= settings.get_value("random_system_degradation_ci_drop") <= 100.0


def test_output_settings_values_have_valid_defaults() -> None:
    """Output-related setting states should hold non-empty strings."""
    settings = MidasSettings()

    assert isinstance(settings.get_value("excel_sheet_main"), str)
    assert settings.get_value("excel_sheet_main")
    assert settings.get_value("excel_sheet_metadata")
    assert settings.get_value("excel_sheet_work_orders")
    assert settings.get_value("metadata_file_suffix")
    separator = settings.get_value("csv_table_separator")
    assert separator and isinstance(separator, str)
    assert len(separator) <= 3, "Separator should be short"


# ---------------------------------------------------------------------------
# Reference data field validity
# ---------------------------------------------------------------------------


def test_facility_types_have_valid_fields() -> None:
    """Every loaded FacilityType should have a positive key, non-empty title, and sane numerics."""
    config_data = MidasConfigData()

    for key, ft in config_data.facility_types.items():
        assert key == ft.key
        assert ft.key > 0, f"FacilityType key must be positive, got {ft.key}"
        assert ft.title and ft.title.strip(), f"FacilityType {ft.key} has empty title"
        assert ft.life_expectancy > 0, f"FacilityType {ft.key} life_expectancy must be positive"
        assert ft.mission_criticality >= 1, f"FacilityType {ft.key} mission_criticality must be >= 1"
        assert ft.life_expectancy_months == ft.life_expectancy * 12


def test_system_types_have_valid_fields_and_facility_key_references() -> None:
    """Every SystemType should reference valid FacilityType keys."""
    config_data = MidasConfigData()

    for key, st in config_data.system_types.items():
        assert key == st.key
        assert st.key > 0, f"SystemType key must be positive, got {st.key}"
        assert st.title and st.title.strip(), f"SystemType {st.key} has empty title"
        assert st.life_expectancy > 0, f"SystemType {st.key} life_expectancy must be positive"
        assert isinstance(st.facility_keys, tuple), f"SystemType {st.key} facility_keys should be a tuple"
        assert st.facility_keys, f"SystemType {st.key} has no facility_keys"

        for fk in st.facility_keys:
            assert fk in config_data.facility_types, (
                f"SystemType {st.key} references facility key {fk} which is not in loaded facility_types"
            )


def test_installation_locations_have_valid_fields() -> None:
    """Every InstallationLocation should have non-empty core fields."""
    config_data = MidasConfigData()
    assert config_data.installation_locations

    for loc in config_data.installation_locations:
        assert loc.title and str(loc.title).strip(), f"Location missing title: {loc}"
        assert loc.location and str(loc.location).strip(), f"Location missing location: {loc}"
        assert loc.region and str(loc.region).strip(), f"Location missing region: {loc}"


# ---------------------------------------------------------------------------
# Distribution loading
# ---------------------------------------------------------------------------


def test_all_distributions_are_loaded_and_sampleable() -> None:
    """All 7 distribution slots should be populated and sample without error."""
    settings = MidasSettings()

    condition_index = settings.get_value("generated_condition_index_distribution")
    age = settings.get_value("generated_age_distribution")
    grade = settings.get_value("generated_resiliency_grade_distribution")
    wo_count = settings.get_value("generated_work_order_count_distribution")
    wo_status = settings.get_value("generated_work_order_status_distribution")
    wo_priority = settings.get_value("generated_work_order_priority_distribution")
    wo_org = settings.get_value("generated_work_order_requesting_organization_distribution")

    assert condition_index is not None
    assert age is not None
    assert grade is not None
    assert wo_count is not None
    assert wo_status is not None
    assert wo_priority is not None
    assert wo_org is not None

    for _ in range(20):
        assert isinstance(condition_index.sample(), (int, float, str))
        assert isinstance(age.sample(), (int, float, str))
        assert isinstance(grade.sample(), (int, float, str))

    assert isinstance(wo_count, (WeightedProbabilityDistribution, EventRateDistribution))

    valid_statuses = {"Submitted", "Approved", "In Progress", "Completed"}
    status_samples = {str(wo_status.sample()).strip() for _ in range(50)}
    assert status_samples.issubset(valid_statuses), f"Unexpected statuses: {status_samples - valid_statuses}"

    valid_priorities = {"Emergency", "Urgent", "Routine", "Preventive Maintenance"}
    priority_samples = {str(wo_priority.sample()).strip() for _ in range(50)}
    assert priority_samples.issubset(valid_priorities), f"Unexpected priorities: {priority_samples - valid_priorities}"

    valid_orgs = {"J1", "J2", "J3", "J4", "J5", "J6"}
    org_samples = {str(wo_org.sample()).strip() for _ in range(50)}
    assert org_samples.issubset(valid_orgs), f"Unexpected orgs: {org_samples - valid_orgs}"


# ---------------------------------------------------------------------------
# ApplicationState and error handling
# ---------------------------------------------------------------------------


def test_application_state_initialize_reports_correct_counts() -> None:
    """ApplicationState.initialize() should succeed and report matching counts."""
    reset_app_state()
    state = ApplicationState.initialize()

    assert state.initialized_successfully
    assert not state.has_errors

    assert state.load_result.facility_types_loaded == len(state.config_data.facility_types)
    assert state.load_result.system_types_loaded == len(state.config_data.system_types)
    assert state.load_result.installation_locations_loaded == len(state.config_data.installation_locations)

    assert state.load_result.facility_types_loaded > 0
    assert state.load_result.system_types_loaded > 0
    assert state.load_result.installation_locations_loaded > 0


def test_load_settings_from_nonexistent_path_raises_config_workbook_load_error() -> None:
    """Config workbook loading with a bad path should raise ConfigWorkbookLoadError."""
    with pytest.raises(ConfigWorkbookLoadError):
        MidasConfigDataLoader().load(Path("/tmp/does_not_exist_midas_test.xlsx"))


def test_application_state_with_defaults_uses_fallback_settings() -> None:
    """ApplicationState.with_defaults() should succeed with a warning."""
    state = ApplicationState.with_defaults()

    assert state.initialized_successfully
    assert state.has_warnings
    assert not state.config_data.facility_types
    assert not state.config_data.system_types


def test_load_state_round_trips_through_json_file(tmp_path: Path) -> None:
    """``save_state``/``load_state`` should preserve setting values across reloads."""
    settings = MidasSettings()
    settings.set_value("condition_index_degraded_threshold", 42.5)
    settings.set_value("excel_sheet_main", "Custom Main")

    target = tmp_path / "midas_settings.json"
    written = settings.save_state(target)
    assert written.exists()

    MidasSettings.reset()
    reloaded = MidasSettings()
    assert reloaded.get_value("condition_index_degraded_threshold") == 25.0
    assert reloaded.get_value("excel_sheet_main") == "Main Data"

    assert reloaded.load_state(target) is True
    assert reloaded.get_value("condition_index_degraded_threshold") == 42.5
    assert reloaded.get_value("excel_sheet_main") == "Custom Main"


def test_load_state_returns_false_when_file_missing(tmp_path: Path) -> None:
    """``load_state`` should report False (not raise) for missing files."""
    settings = MidasSettings()
    assert settings.load_state(tmp_path / "missing.json") is False
