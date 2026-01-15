"""Base formatter class for export formats."""

from abc import ABC, abstractmethod
from pathlib import Path

from ....domain import Facility, Installation, System
from ..config import ExportConfig
from ..transformers import DataTransformer


class BaseFormatter(ABC):
    """Base class for format-specific exporters."""

    def __init__(
        self,
        config: ExportConfig,
        transformer: DataTransformer,
    ) -> None:
        """Initialize formatter.

        Args:
            config: Export configuration.
            transformer: Data transformer instance.
        """
        self.config = config
        self.transformer = transformer

    @abstractmethod
    def export(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        metadata: dict | None = None,
    ) -> Path:
        """Export data to file.

        Args:
            installations: List of installations.
            facilities: List of facilities.
            systems: List of systems.
            metadata: Optional metadata dictionary.

        Returns:
            Path to the created file.
        """
        pass

    def _write_metadata(self, metadata: dict) -> None:
        """Write metadata to JSON file.

        Args:
            metadata: Metadata dictionary to write.
        """
        import json

        with open(self.config.metadata_path, "w") as f:
            json.dump(metadata, f, indent=2, default=str)
