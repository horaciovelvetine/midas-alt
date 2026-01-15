"""Main exporter class for simulated data."""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...domain import Facility, Installation, System
from .config import ExportConfig
from .enums import OutputFormat, OutputLayout
from .formatters import CSVFormatter, ExcelFormatter, JSONFormatter
from .transformers import DataTransformer

if TYPE_CHECKING:
    from ...config import MIDASSettings


class DataExporter:
    """Handles generation and export of simulated data to various file formats.

    This is the main interface for generating and exporting simulated data.
    """

    def __init__(
        self,
        file_name: str,
        output_format: OutputFormat | str,
        output_directory: str | Path = ".",
        include_time_series: bool = False,
        layout: OutputLayout | str = OutputLayout.NORMALIZED,
        generate_metadata: bool = True,
        description: str = "",
        settings: "MIDASSettings | None" = None,
    ) -> None:
        """Initialize the data exporter.

        Args:
            file_name: Base name for the output file (without extension).
            output_format: Format for export (csv, json, xlsx).
            output_directory: Directory where file will be saved.
            include_time_series: Whether to include time series data.
            layout: Output layout - normalized or denormalized.
            generate_metadata: Whether to generate a metadata JSON file.
            description: Optional description for the dataset.
            settings: Application settings for reference data.
        """
        # Lazy imports to avoid circular dependency
        from ...config import MIDASSettings
        from ..generator import DataGenerator
        
        self.settings = settings or MIDASSettings.with_defaults()

        # Create export configuration
        self.config = ExportConfig(
            file_name=file_name,
            output_format=output_format,
            output_directory=output_directory,
            include_time_series=include_time_series,
            layout=layout,
            generate_metadata=generate_metadata,
            description=description,
        )

        # Initialize components
        self.generator = DataGenerator(settings=self.settings)
        self.transformer = DataTransformer(
            settings=self.settings,
            include_time_series=include_time_series,
        )

        # Create formatter based on output format
        self.formatter = self._create_formatter()

    def _create_formatter(self):
        """Create the appropriate formatter based on output format."""
        if self.config.output_format == OutputFormat.CSV:
            return CSVFormatter(self.config, self.transformer)
        elif self.config.output_format == OutputFormat.JSON:
            return JSONFormatter(self.config, self.transformer)
        elif self.config.output_format == OutputFormat.XLSX:
            return ExcelFormatter(self.config, self.transformer)
        else:
            raise ValueError(f"Unsupported output format: {self.config.output_format}")

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
        """Generate simulated data and export to file.

        Args:
            method: Generation method - "default", "installations", or "facilities".
            target_count: Number of items to generate (required for installations/facilities).

        Returns:
            Path to the created file.
        """
        # Generate data
        if method == "installations":
            if target_count is None:
                raise ValueError("target_count is required for 'installations' method")
            installations, facilities, systems = self.generator.generate_installations(target_count)

        elif method == "facilities":
            if target_count is None:
                raise ValueError("target_count is required for 'facilities' method")
            # Generate multiple facilities in one installation
            installation, facilities, systems = self.generator.generate_installation()
            # Generate additional facilities
            for _ in range(target_count - len(facilities)):
                _, new_facilities, new_systems = self.generator.generate_installation()
                facilities.extend(new_facilities)
                systems.extend(new_systems)
            installations = [installation]

        else:  # default
            installation, facilities, systems = self.generator.generate_installation()
            installations = [installation]

        # Create metadata
        metadata = self._create_metadata(method, target_count, installations, facilities, systems)

        # Export using formatter
        return self.formatter.export(installations, facilities, systems, metadata)

    def export_existing(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
    ) -> Path:
        """Export existing data (not generated).

        Args:
            installations: List of installations to export.
            facilities: List of facilities to export.
            systems: List of systems to export.

        Returns:
            Path to the created file.
        """
        metadata = self._create_metadata(
            "existing", None, installations, facilities, systems
        )
        return self.formatter.export(installations, facilities, systems, metadata)

    def _create_metadata(
        self,
        method: str,
        target_count: int | None,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
    ) -> dict:
        """Create metadata dictionary."""
        return {
            "generated_at": datetime.now().isoformat(),
            "description": self.config.description,
            "generation_method": method,
            "target_count": target_count,
            "output_format": self.config.output_format.value,
            "layout": self.config.layout.value,
            "include_time_series": self.config.include_time_series,
            "counts": {
                "installations": len(installations),
                "facilities": len(facilities),
                "systems": len(systems),
            },
        }
