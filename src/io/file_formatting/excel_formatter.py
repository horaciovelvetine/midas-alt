"""Excel formatter for data export."""

from pathlib import Path

from src.models import Installation, Facility, System, WorkOrder
from .base_formatter import BaseFormatter


class ExcelFormatter(BaseFormatter):
    """Export data to Excel format."""

    def export(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
        metadata: dict | None = None,
    ) -> Path:
        """Export data to Excel file.

        Creates separate sheets for each table in normalized layout.
        Creates a single sheet for denormalized layout.

        Args:
            installations: List of installations.
            facilities: List of facilities.
            systems: List of systems.
            work_orders: List of work orders.
            metadata: Optional metadata dictionary.

        Returns:
            Path to the output file.

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
        """Export normalized tables to separate Excel sheets."""
        import pandas as pd

        tables = self.transformer.create_normalized_tables(
            installations, facilities, systems, work_orders
        )
        output = self.transformer.settings.output

        # Update metadata
        if metadata:
            metadata["record_counts"] = {
                name: len(df) if df is not None else 0 for name, df in tables.items()
            }

        # Write to Excel with separate sheets
        with pd.ExcelWriter(self.config.file_path, engine="openpyxl") as writer:
            for table_name, df in tables.items():
                if df is not None and not df.empty:
                    sheet_name_map = {
                        "installations": "Installations",
                        "facilities": "Facilities",
                        "systems": "Systems",
                        "work_orders": output.excel_sheet_work_orders,
                        "facility_time_series": output.excel_sheet_facility_ts,
                        "system_time_series": output.excel_sheet_system_ts,
                    }
                    sheet_name = sheet_name_map.get(
                        table_name, table_name.replace("_", " ").title()
                    )
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Write metadata sheet if requested
            if metadata:
                meta_df = pd.DataFrame(
                    [
                        {"key": k, "value": str(v)}
                        for k, v in metadata.items()
                        if not isinstance(v, dict)
                    ]
                )
                if not meta_df.empty:
                    meta_df.to_excel(
                        writer, sheet_name=output.excel_sheet_metadata, index=False
                    )

        # Note: No separate metadata file for Excel - metadata is included as a sheet

        return self.config.file_path

    def _export_denormalized(
        self,
        installations: list[Installation],
        facilities: list[Facility],
        systems: list[System],
        work_orders: list[WorkOrder],
        metadata: dict | None = None,
    ) -> Path:
        """Export denormalized data to single Excel sheet."""
        import pandas as pd

        rows = self.transformer.create_denormalized_rows(
            installations, facilities, systems, work_orders
        )
        df = pd.DataFrame(rows)
        output = self.transformer.settings.output

        # Update metadata
        if metadata:
            metadata["record_counts"] = {"main_data": len(df)}

        # Write to Excel
        with pd.ExcelWriter(self.config.file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=output.excel_sheet_main, index=False)

            # Write metadata sheet if requested
            if metadata:
                meta_df = pd.DataFrame(
                    [
                        {"key": k, "value": str(v)}
                        for k, v in metadata.items()
                        if not isinstance(v, dict)
                    ]
                )
                if not meta_df.empty:
                    meta_df.to_excel(
                        writer, sheet_name=output.excel_sheet_metadata, index=False
                    )

        # Note: No separate metadata file for Excel - metadata is included as a sheet

        return self.config.file_path
