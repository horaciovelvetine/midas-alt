"""Configuration for data export."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .enums import OutputFormat, OutputLayout


@dataclass
class ExportConfig:
    """Configuration for data export."""

    file_name: str
    output_format: OutputFormat | str
    output_directory: Path | str = "."
    include_time_series: bool = False
    layout: OutputLayout | str = OutputLayout.NORMALIZED
    generate_metadata: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        """Normalize types and create output directory."""
        # Normalize output_format
        if isinstance(self.output_format, str):
            self.output_format = OutputFormat(self.output_format.lower())

        # Normalize layout
        if isinstance(self.layout, str):
            self.layout = OutputLayout(self.layout.lower())

        # Ensure output_directory is a Path
        if isinstance(self.output_directory, str):
            self.output_directory = Path(self.output_directory)

        # Create a dedicated directory for this export run
        self.output_directory = self.output_directory / self.file_name
        self.output_directory.mkdir(parents=True, exist_ok=True)

    @property
    def file_path(self) -> Path:
        """Get the full file path for the output file."""
        return self.output_directory / f"{self.file_name}.{self.output_format.value}"

    @property
    def metadata_path(self) -> Path:
        """Get the path for the metadata file."""
        return self.output_directory / f"{self.file_name}_metadata.json"
