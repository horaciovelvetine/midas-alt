"""Integration tests for loading exported simulation datasets."""

from pathlib import Path

import pytest

from src.enums import UFCGrade, WO_Priority, WO_Status, WO_TradeSkill
from src.io import DataExporter, SimulationDataLoader
from src.models import DependencyPosition
from src.simulation import DataGenerator


@pytest.mark.parametrize("output_format", ["csv", "xlsx"])
def test_loader_round_trips_normalized_exports(tmp_path: Path, output_format: str) -> None:
    """Loader should rebuild hierarchy objects from normalized exports."""
    result = DataGenerator(seed=42).generate_installations(2)
    exporter = DataExporter(
        file_name=f"simulation_loader_{output_format}",
        output_format=output_format,
        output_directory=tmp_path,
        layout="normalized",
        generate_metadata=True,
    )
    output_path = exporter.export_existing(
        installations=result.installations,
        facilities=result.facilities,
        systems=result.systems,
        work_orders=result.work_orders,
    )

    dataset_path = exporter.config.output_directory if output_format == "csv" else output_path
    loaded = SimulationDataLoader().load(dataset_path)

    assert len(loaded.installations) == len(result.installations)
    assert len(loaded.facilities) == len(result.facilities)
    assert len(loaded.systems) == len(result.systems)
    assert len(loaded.work_orders) == len(result.work_orders)

    installation_ids = {installation.id for installation in loaded.installations}
    facility_ids = {facility.id for facility in loaded.facilities}
    system_ids = {system.id for system in loaded.systems}

    assert installation_ids
    assert facility_ids
    assert system_ids

    for installation in loaded.installations:
        assert installation.facility_ids
        assert set(installation.facility_ids).issubset(facility_ids)

    for facility in loaded.facilities:
        assert facility.installation_id in installation_ids
        assert isinstance(facility.dependency_position, DependencyPosition)
        assert facility.resiliency_grade is None or isinstance(facility.resiliency_grade, UFCGrade)
        assert set(facility.system_ids).issubset(system_ids)

    for system in loaded.systems:
        assert system.facility_id in facility_ids
        assert len(system.work_orders) == len([wo for wo in loaded.work_orders if wo.system_id == system.id])

    for work_order in loaded.work_orders:
        assert work_order.system_id in system_ids
        assert work_order.status is None or isinstance(work_order.status, WO_Status)
        assert work_order.priority is None or isinstance(work_order.priority, WO_Priority)
        assert work_order.trade is None or isinstance(work_order.trade, WO_TradeSkill)
