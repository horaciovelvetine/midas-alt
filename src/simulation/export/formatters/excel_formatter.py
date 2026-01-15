"""Excel formatter for data export."""

from pathlib import Path

from ....domain import Facility, Installation, System
from ..config import ExportConfig
from ..enums import OutputLayout
from ..transformers import DataTransformer
from .base import BaseFormatter


class ExcelFormatter(BaseFormatter):
    """Export data to Excel format."""

    def export(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        metadata: dict | None = None,
    ) -> Path:
        """Export data to Excel file.

        Creates separate sheets for each table in normalized layout.
        Creates a single sheet for denormalized layout.

        Args:
            installations: List of installations.
            facilities: List of facilities.
            systems: List of systems.
            metadata: Optional metadata dictionary.

        Returns:
            Path to the output file.
        """
        import pandas as pd

        if self.config.layout == OutputLayout.NORMALIZED:
            return self._export_normalized(installations, facilities, systems, metadata)
        else:
            return self._export_denormalized(installations, facilities, systems, metadata)

    def _export_normalized(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        metadata: dict | None = None,
    ) -> Path:
        """Export normalized tables to separate Excel sheets."""
        import pandas as pd

        tables = self.transformer.create_normalized_tables(installations, facilities, systems)

        # Update metadata
        if metadata:
            metadata["record_counts"] = {
                name: len(df) if df is not None else 0
                for name, df in tables.items()
            }

        # Write to Excel with separate sheets
        with pd.ExcelWriter(self.config.file_path, engine="openpyxl") as writer:
            for table_name, df in tables.items():
                if df is not None and not df.empty:
                    sheet_name = table_name.replace("_", " ").title()
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Write metadata sheet if requested
            if metadata:
                meta_df = pd.DataFrame([
                    {"key": k, "value": str(v)}
                    for k, v in metadata.items()
                    if not isinstance(v, dict)
                ])
                if not meta_df.empty:
                    meta_df.to_excel(writer, sheet_name="_metadata", index=False)

        # Also write separate metadata file
        if metadata and self.config.generate_metadata:
            self._write_metadata(metadata)

        return self.config.file_path

    def _export_denormalized(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        metadata: dict | None = None,
    ) -> Path:
        """Export denormalized data to single Excel sheet."""
        import pandas as pd

        rows = self.transformer.create_denormalized_rows(installations, facilities, systems)
        df = pd.DataFrame(rows)

        # Update metadata
        if metadata:
            metadata["record_counts"] = {"main_data": len(df)}

        # Write to Excel
        with pd.ExcelWriter(self.config.file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Main Data", index=False)

            # Write metadata sheet if requested
            if metadata:
                meta_df = pd.DataFrame([
                    {"key": k, "value": str(v)}
                    for k, v in metadata.items()
                    if not isinstance(v, dict)
                ])
                if not meta_df.empty:
                    meta_df.to_excel(writer, sheet_name="_metadata", index=False)

        # Also write separate metadata file
        if metadata and self.config.generate_metadata:
            self._write_metadata(metadata)

        return self.config.file_path
