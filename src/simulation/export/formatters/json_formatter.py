"""JSON formatter for data export."""

import json
from pathlib import Path

from ....domain import Facility, Installation, System
from ..config import ExportConfig
from ..enums import OutputLayout
from ..transformers import DataTransformer
from .base import BaseFormatter


class JSONFormatter(BaseFormatter):
    """Export data to JSON format."""

    def export(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        metadata: dict | None = None,
    ) -> Path:
        """Export data to JSON file.

        For normalized layout, creates a JSON with separate arrays.
        For denormalized layout, creates nested JSON structure.

        Args:
            installations: List of installations.
            facilities: List of facilities.
            systems: List of systems.
            metadata: Optional metadata dictionary.

        Returns:
            Path to the output file.
        """
        if self.config.layout == OutputLayout.NORMALIZED:
            return self._export_normalized(installations, facilities, systems, metadata)
        else:
            return self._export_nested(installations, facilities, systems, metadata)

    def _export_normalized(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        metadata: dict | None = None,
    ) -> Path:
        """Export normalized tables to JSON with separate arrays."""
        tables = self.transformer.create_normalized_tables(installations, facilities, systems)

        data = {}
        for table_name, df in tables.items():
            if df is not None and not df.empty:
                data[table_name] = df.to_dict(orient="records")
            else:
                data[table_name] = []

        # Update metadata
        if metadata:
            metadata["record_counts"] = {
                name: len(records) for name, records in data.items()
            }

        # Include metadata in output if requested
        output = {"data": data}
        if metadata:
            output["metadata"] = metadata

        # Write JSON
        with open(self.config.file_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        # Also write separate metadata file
        if metadata and self.config.generate_metadata:
            self._write_metadata(metadata)

        return self.config.file_path

    def _export_nested(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        metadata: dict | None = None,
    ) -> Path:
        """Export nested/denormalized JSON structure."""
        data = self.transformer.create_nested_dict(installations, facilities, systems)

        # Update metadata
        if metadata:
            metadata["record_counts"] = {
                "installations": len(installations),
                "facilities": len(facilities),
                "systems": len(systems),
            }

        # Include metadata in output if requested
        output = data
        if metadata:
            output["metadata"] = metadata

        # Write JSON
        with open(self.config.file_path, "w") as f:
            json.dump(output, f, indent=2, default=str)

        # Also write separate metadata file
        if metadata and self.config.generate_metadata:
            self._write_metadata(metadata)

        return self.config.file_path
