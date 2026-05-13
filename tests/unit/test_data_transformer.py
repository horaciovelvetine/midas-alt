"""Unit tests for ``DataTransformer`` table, row, and nested-dict builders."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.config import MidasConfigData
from src.enums import UFCGrade, WO_Priority, WO_Status, WO_TradeSkill
from src.io.models.data_transformer import DataTransformer
from src.models import (
    DependencyPosition,
    Facility,
    FacilityType,
    Installation,
    System,
    SystemType,
    WorkOrder,
)


def _install_known_reference_data() -> tuple[FacilityType, SystemType]:
    """Replace singleton reference data with one facility/system type pair."""
    facility_type = FacilityType(
        key=101, title="Hangar", life_expectancy=50, mission_criticality=4
    )
    system_type = SystemType(
        key=201, title="HVAC", life_expectancy=20, facility_keys=(101,)
    )
    MidasConfigData().replace_reference_data(
        facility_types={facility_type.key: facility_type},
        system_types={system_type.key: system_type},
    )
    return facility_type, system_type


def _build_dataset() -> (
    tuple[list[Installation], list[Facility], list[System], list[WorkOrder]]
):
    """Construct a minimal installation/facility/system/work-order set."""
    install = Installation(
        id="inst-1",
        title="Test Base",
        location="Anywhere",
        region="US",
        coordinates="0,0",
        condition_index=72.5,
        facility_ids=["fac-1"],
    )
    facility = Facility(
        id="fac-1",
        installation_id=install.id,
        facility_type_key=101,
        facility_type_title="Hangar",
        year_constructed=2000,
        dependency_position=DependencyPosition(),
        resiliency_grade=UFCGrade.G3,
        system_ids=["sys-1"],
        condition_index=70.0,
    )
    system = System(
        id="sys-1",
        facility_id=facility.id,
        system_type_key=201,
        year_constructed=2005,
        condition_index=80.0,
    )
    work_order = WorkOrder(
        id="wo-1",
        installation_id=install.id,
        facility_id=facility.id,
        system_id=system.id,
        requesting_organization="Maintenance",
        work_category="Routine",
        status=WO_Status.SUBMITTED,
        priority=WO_Priority.ROUTINE,
        trade=WO_TradeSkill.HVAC,
        request_datetime=datetime(2025, 6, 1, 12, 0),
        problem_description="Filter replacement",
        impacts_mission=False,
    )
    return [install], [facility], [system], [work_order]


def test_create_normalized_tables_returns_dataframes_for_each_table() -> None:
    """All four normalized tables are produced with expected columns and lengths."""
    _install_known_reference_data()
    installs, facilities, systems, work_orders = _build_dataset()

    tables = DataTransformer().create_normalized_tables(
        installs, facilities, systems, work_orders
    )

    assert set(tables.keys()) == {
        "installations",
        "facilities",
        "systems",
        "work_orders",
    }
    for df in tables.values():
        assert isinstance(df, pd.DataFrame)
    assert len(tables["installations"]) == 1
    assert tables["installations"].iloc[0]["title"] == "Test Base"
    assert tables["facilities"].iloc[0]["title"] == "Hangar"
    assert tables["facilities"].iloc[0]["resiliency_grade"] == "3"
    assert tables["facilities"].iloc[0]["life_expectancy"] == 50
    assert tables["facilities"].iloc[0]["mission_criticality"] == 4
    assert tables["systems"].iloc[0]["title"] == "HVAC"
    assert tables["systems"].iloc[0]["life_expectancy"] == 20
    assert tables["work_orders"].iloc[0]["status"] == "Submitted"
    assert tables["work_orders"].iloc[0]["priority"] == "Routine"
    assert tables["work_orders"].iloc[0]["trade"] == "HVAC"


def test_create_normalized_tables_returns_none_for_empty_sections() -> None:
    """Empty input lists short-circuit to ``None`` for the affected tables."""
    tables = DataTransformer().create_normalized_tables([], [], [], [])
    assert tables == {
        "installations": None,
        "facilities": None,
        "systems": None,
        "work_orders": None,
    }


def test_facility_type_title_falls_back_to_reference_lookup() -> None:
    """When the facility lacks a denormalized title, the reference cache is used."""
    _install_known_reference_data()
    installs, facilities, systems, work_orders = _build_dataset()
    facilities[0].facility_type_title = ""

    tables = DataTransformer().create_normalized_tables(
        installs, facilities, systems, work_orders
    )

    assert tables["facilities"].iloc[0]["title"] == "Hangar"


def test_facility_type_title_uses_blank_when_reference_missing() -> None:
    """A missing facility type AND missing denormalized title yields the empty string."""
    MidasConfigData().clear()
    installs, facilities, systems, work_orders = _build_dataset()
    facilities[0].facility_type_title = None

    tables = DataTransformer().create_normalized_tables(
        installs, facilities, systems, work_orders
    )

    assert tables["facilities"].iloc[0]["title"] == ""
    assert tables["facilities"].iloc[0]["life_expectancy"] is None
    assert tables["systems"].iloc[0]["title"] == ""
    assert tables["systems"].iloc[0]["life_expectancy"] is None


def test_create_denormalized_rows_emits_one_row_per_resolvable_work_order() -> None:
    """Work orders missing parent references are silently dropped."""
    _install_known_reference_data()
    installs, facilities, systems, work_orders = _build_dataset()
    orphan = WorkOrder(id="wo-orphan", system_id="missing")
    work_orders.append(orphan)

    rows = DataTransformer().create_denormalized_rows(
        installs, facilities, systems, work_orders
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["installation_id"] == "inst-1"
    assert row["facility_id"] == "fac-1"
    assert row["system_id"] == "sys-1"
    assert row["facility_title"] == "Hangar"
    assert row["system_title"] == "HVAC"
    assert row["facility_resiliency_grade"] == "3"
    assert row["work_order_status"] == "Submitted"


def test_create_denormalized_rows_skips_unknown_facility_or_installation() -> None:
    """Rows are dropped when facility or installation cannot be resolved."""
    _install_known_reference_data()
    installs, facilities, systems, work_orders = _build_dataset()
    systems[0].facility_id = "ghost-facility"

    rows = DataTransformer().create_denormalized_rows(
        installs, facilities, systems, work_orders
    )
    assert rows == []

    systems[0].facility_id = "fac-1"
    facilities[0].installation_id = "ghost-install"
    rows = DataTransformer().create_denormalized_rows(
        installs, facilities, systems, work_orders
    )
    assert rows == []


def test_create_nested_dict_builds_full_tree() -> None:
    """The nested dict mirrors the entity hierarchy with embedded work orders."""
    _install_known_reference_data()
    installs, facilities, systems, work_orders = _build_dataset()

    nested = DataTransformer().create_nested_dict(
        installs, facilities, systems, work_orders
    )

    assert list(nested.keys()) == ["installations"]
    assert len(nested["installations"]) == 1
    install_node = nested["installations"][0]
    assert install_node["id"] == "inst-1"
    assert len(install_node["facilities"]) == 1
    facility_node = install_node["facilities"][0]
    assert facility_node["title"] == "Hangar"
    assert len(facility_node["systems"]) == 1
    system_node = facility_node["systems"][0]
    assert system_node["title"] == "HVAC"
    assert len(system_node["work_orders"]) == 1
    assert system_node["work_orders"][0]["status"] == "Submitted"


def test_create_nested_dict_skips_work_orders_without_system_id() -> None:
    """Work orders without a ``system_id`` never appear in the nested tree."""
    _install_known_reference_data()
    installs, facilities, systems, work_orders = _build_dataset()
    work_orders.append(WorkOrder(id="wo-loose", system_id=None))

    nested = DataTransformer().create_nested_dict(
        installs, facilities, systems, work_orders
    )

    all_wo_ids = [
        wo["id"]
        for install in nested["installations"]
        for facility in install["facilities"]
        for system in facility["systems"]
        for wo in system["work_orders"]
    ]
    assert all_wo_ids == ["wo-1"]
