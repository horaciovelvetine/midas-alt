"""Main exporter class for simulated data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.config.midas_settings import MidasSettings
from src.io.enums import OutputFileType, OutputLayoutSchema
from src.io.file_formatting import CSVFormatter, ExcelFormatter
from src.models import Facility, Installation, System, WorkOrder

from .data_transformer import DataTransformer
from .export_config import ExportConfig


class DataExporter:
    """Handles generation and export of simulated data to various file formats."""

    def __init__(
        self,
        file_name: str,
        output_format: OutputFileType | str,
        output_directory: str | Path = ".",
        layout: OutputLayoutSchema | str = OutputLayoutSchema.NORMALIZED,
        generate_metadata: bool = True,
        description: str = "",
    ) -> None:
        """Initialize the data exporter.

        Args:
            file_name: Base name for the output file (without extension).
            output_format: Format for export (csv, xlsx).
            output_directory: Directory where files will be saved.
            layout: Output layout (normalized or denormalized).
            generate_metadata: Whether to generate a metadata JSON file.
            description: Optional description for the dataset.
        """
        from src.simulation.data_generation import DataGenerator

        self.settings = MidasSettings()

        self.config = ExportConfig(
            file_name=file_name,
            output_format=output_format,
            output_directory=output_directory,
            layout=layout,
            generate_metadata=generate_metadata,
            description=description,
        )

        self.generator = DataGenerator()
        self.transformer = DataTransformer()
        self.formatter = self._create_formatter()

    @classmethod
    def from_config(cls, config: ExportConfig) -> DataExporter:
        """Build an exporter from an existing :class:`ExportConfig`."""
        from src.simulation.data_generation import DataGenerator

        obj = cls.__new__(cls)
        obj.settings = MidasSettings()
        obj.config = config
        obj.generator = DataGenerator()
        obj.transformer = DataTransformer()
        obj.formatter = obj._create_formatter()
        return obj

    def _create_formatter(self):
        """Create the appropriate formatter based on output format."""
        fmt = self.config.output_format.value
        if fmt == "csv":
            return CSVFormatter(self.config, self.transformer)
        if fmt == "xlsx":
            return ExcelFormatter(self.config, self.transformer)
        raise ValueError(
            f"Invalid output format: expected one of ['csv', 'xlsx'] (got {self.config.output_format!r})"
        )

    @property
    def file_path(self) -> Path:
        """Get the full file path for the output file."""
        return self.config.file_path

    @property
    def metadata_path(self) -> Path:
        """Get the path for the metadata file."""
        return self.config.metadata_path

    def generate_and_export(
        self,
        method: str = "default",
        target_count: int | None = None,
    ) -> Path:
        """Generate simulated data and export to file."""
        if method == "installations":
            if target_count is None:
                raise ValueError(
                    "Invalid argument: target_count is required for method 'installations' (got None)"
                )
            result = self.generator.generate_installations(target_count)

        elif method == "facilities":
            if target_count is None:
                raise ValueError(
                    "Invalid argument: target_count is required for method 'facilities' (got None)"
                )
            result = self.generator.generate_installation()
            installations = list(result.installations)
            facilities = list(result.facilities)
            systems = list(result.systems)
            work_orders = list(result.work_orders)
            for _ in range(target_count - len(facilities)):
                extra = self.generator.generate_installation()
                facilities.extend(extra.facilities)
                systems.extend(extra.systems)
                work_orders.extend(extra.work_orders)
                installations.extend(extra.installations)
            result.installations = installations
            result.facilities = facilities
            result.systems = systems
            result.work_orders = work_orders

        else:
            result = self.generator.generate_installation()

        installations = result.installations
        facilities = result.facilities
        systems = result.systems
        work_orders = result.work_orders
        metadata = self._create_metadata(
            method, target_count, installations, facilities, systems, work_orders
        )

        return self.formatter.export(
            installations, facilities, systems, work_orders, metadata
        )

    def export_existing(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
    ) -> Path:
        """Export existing data (not generated)."""
        metadata = self._create_metadata(
            "existing", None, installations, facilities, systems, work_orders
        )
        return self.formatter.export(
            installations, facilities, systems, work_orders, metadata
        )

    def _create_metadata(
        self,
        method: str,
        target_count: int | None,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
    ) -> dict:
        """Create metadata dictionary."""
        return {
            "generated_at": datetime.now().isoformat(),
            "description": self.config.description,
            "generation_method": method,
            "target_count": target_count,
            "output_format": self.config.output_format.value,
            "layout": self.config.layout.value,
            "counts": {
                "installations": len(installations),
                "facilities": len(facilities),
                "systems": len(systems),
                "work_orders": len(work_orders),
            },
        }
