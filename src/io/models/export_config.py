"""Normalized export run settings for paths, format, and layout."""

from dataclasses import dataclass
from pathlib import Path

from ..enums import OutputFileType, OutputLayoutSchema


@dataclass
class ExportConfig:
    """Paths, format, and layout for one export run (creates output subdirectory)."""

    file_name: str
    output_format: OutputFileType | str
    output_directory: Path | str = "."
    layout: OutputLayoutSchema | str = OutputLayoutSchema.NORMALIZED
    generate_metadata: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        """Normalize types and create output directory."""
        if not isinstance(self.output_format, OutputFileType):
            if isinstance(self.output_format, str):
                self.output_format = OutputFileType(self.output_format.lower())
            else:
                self.output_format = OutputFileType(str(self.output_format.value).lower())

        if not isinstance(self.layout, OutputLayoutSchema):
            if isinstance(self.layout, str):
                self.layout = OutputLayoutSchema(self.layout.lower())
            else:
                self.layout = OutputLayoutSchema(str(self.layout.value).lower())

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
        from src.config.midas_settings import MidasSettings

        suffix = MidasSettings().get_value("metadata_file_suffix")
        return self.output_directory / f"{self.file_name}{suffix}"
