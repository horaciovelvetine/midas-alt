"""CSV formatter for data export."""

from pathlib import Path

from src.models import Installation, Facility, System, WorkOrder
from .base_formatter import BaseFormatter


class CSVFormatter(BaseFormatter):
    """Export data to CSV format."""

    def export(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
        metadata: dict | None = None,
    ) -> Path:
        """Export data to CSV file(s).

        For normalized layout, creates separate CSV files for each table.
        For denormalized layout, creates a single flattened CSV file.

        Args:
            installations: List of installations.
            facilities: List of facilities.
            systems: List of systems.
            work_orders: List of work orders.
            metadata: Optional metadata dictionary.

        Returns:
            Path to the main output file.

        """
        if self.config.layout.value == "normalized":
            return self._export_normalized(
                installations, facilities, systems, work_orders, metadata
            )
        else:
            return self._export_denormalized(
                installations, facilities, systems, work_orders, metadata
            )

    def _export_normalized(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
        metadata: dict | None = None,
    ) -> Path:
        """Export normalized tables to separate CSV files."""
        tables = self.transformer.create_normalized_tables(
            installations, facilities, systems, work_orders
        )

        # Update metadata with record counts
        if metadata:
            metadata["record_counts"] = {
                name: len(df) if df is not None else 0 for name, df in tables.items()
            }

        # Write each table to a separate file
        separator = self.transformer.settings.output.csv_table_separator
        for table_name, df in tables.items():
            if df is not None and not df.empty:
                file_path = (
                    self.config.output_directory
                    / f"{self.config.file_name}{separator}{table_name}.csv"
                )
                df.to_csv(file_path, index=False)

        # Write metadata
        if metadata and self.config.generate_metadata:
            self._write_metadata(metadata)

        return self.config.file_path

    def _export_denormalized(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
        metadata: dict | None = None,
    ) -> Path:
        """Export denormalized data to single CSV file."""
        import pandas as pd

        rows = self.transformer.create_denormalized_rows(
            installations, facilities, systems, work_orders
        )
        df = pd.DataFrame(rows)

        # Update metadata
        if metadata:
            metadata["record_counts"] = {"main_data": len(df)}

        # Write data
        df.to_csv(self.config.file_path, index=False)

        # Write metadata
        if metadata and self.config.generate_metadata:
            self._write_metadata(metadata)

        return self.config.file_path
