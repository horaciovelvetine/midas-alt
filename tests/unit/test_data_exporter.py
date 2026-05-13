"""Unit tests for :class:`DataExporter` branching not covered by integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.io import DataExporter
from src.io.enums import OutputFileType, OutputLayoutSchema
from src.io.file_formatting import CSVFormatter, ExcelFormatter
from src.io.models.export_config import ExportConfig


def test_init_dispatches_to_csv_formatter(tmp_path: Path) -> None:
    """Initializing with ``csv`` selects ``CSVFormatter``."""
    exporter = DataExporter(
        file_name="test_csv",
        output_format="csv",
        output_directory=tmp_path,
    )
    assert isinstance(exporter.formatter, CSVFormatter)
    assert exporter.file_path == exporter.config.file_path
    assert exporter.metadata_path == exporter.config.metadata_path


def test_init_dispatches_to_excel_formatter(tmp_path: Path) -> None:
    """Initializing with ``xlsx`` selects ``ExcelFormatter``."""
    exporter = DataExporter(
        file_name="test_xlsx",
        output_format="xlsx",
        output_directory=tmp_path,
    )
    assert isinstance(exporter.formatter, ExcelFormatter)


def test_from_config_reuses_existing_export_config(tmp_path: Path) -> None:
    """``from_config`` keeps the supplied ``ExportConfig`` instance."""
    config = ExportConfig(
        file_name="from_config",
        output_format=OutputFileType.CSV,
        output_directory=tmp_path,
        layout=OutputLayoutSchema.NORMALIZED,
    )

    exporter = DataExporter.from_config(config)

    assert exporter.config is config
    assert isinstance(exporter.formatter, CSVFormatter)


def test_create_formatter_raises_for_unsupported_format(tmp_path: Path) -> None:
    """An unsupported ``output_format`` value raises ``ValueError``."""
    exporter = DataExporter(
        file_name="invalid",
        output_format="csv",
        output_directory=tmp_path,
    )

    class _BadFormat:
        value = "tsv"

    exporter.config.output_format = _BadFormat()

    with pytest.raises(ValueError, match="Invalid output format"):
        exporter._create_formatter()


def test_generate_and_export_facilities_method_extends_until_target_count(
    tmp_path: Path,
) -> None:
    """``facilities`` mode keeps generating installations until reaching ``target_count``."""
    exporter = DataExporter(
        file_name="facilities_dataset",
        output_format="csv",
        output_directory=tmp_path,
        generate_metadata=False,
    )

    output_path = exporter.generate_and_export(method="facilities", target_count=5)

    assert output_path.parent.exists()
    csv_files = list(output_path.parent.glob("*.csv"))
    assert csv_files, "facilities-mode CSV export should produce per-table files"


def test_generate_and_export_rejects_facilities_without_target_count(
    tmp_path: Path,
) -> None:
    """``facilities`` mode without a ``target_count`` raises early."""
    exporter = DataExporter(
        file_name="no_target",
        output_format="csv",
        output_directory=tmp_path,
        generate_metadata=False,
    )

    with pytest.raises(ValueError, match="target_count is required"):
        exporter.generate_and_export(method="facilities")


def test_generate_and_export_writes_metadata_sidecar_for_csv(tmp_path: Path) -> None:
    """CSV exports write a JSON metadata sidecar with run details."""
    exporter = DataExporter(
        file_name="metadata_csv",
        output_format="csv",
        output_directory=tmp_path,
        generate_metadata=True,
        description="Test export",
    )

    exporter.generate_and_export(method="default")
    metadata_path = exporter.metadata_path

    assert metadata_path.exists()
    payload = json.loads(metadata_path.read_text())
    assert payload["description"] == "Test export"
    assert payload["generation_method"] == "default"
    assert payload["output_format"] == "csv"
    assert payload["counts"]["installations"] >= 1


def test_export_existing_writes_files_and_metadata(tmp_path: Path) -> None:
    """``export_existing`` produces files for caller-supplied entities."""
    from src.simulation import DataGenerator

    result = DataGenerator(seed=7).generate_installation()
    exporter = DataExporter(
        file_name="existing_dataset",
        output_format="csv",
        output_directory=tmp_path,
        generate_metadata=True,
    )

    output_path = exporter.export_existing(
        installations=result.installations,
        facilities=result.facilities,
        systems=result.systems,
        work_orders=result.work_orders,
    )

    assert output_path.parent.exists()
    metadata_payload = json.loads(exporter.metadata_path.read_text())
    assert metadata_payload["generation_method"] == "existing"
    assert metadata_payload["counts"]["installations"] == len(result.installations)
