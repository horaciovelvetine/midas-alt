"""
Work order reader for the MIDAS condition index model.

Reads Excel files produced by ce_work_order_generator.py and returns
per-facility, per-timestep work order priority lists compatible with
FacilityConditionModel.step(deferred_reports=..., completed_reports=...).

The generator has the data format. This module parses it.

Deferred vs completed logic:
    - deferred:  submitted before the step window ends, status is not
                 "Completed" (still open at start step)
    - completed: Completion Date falls within the step window [start, end]

Priority codes (1-4) pass through
PRIORITY_WEIGHTS in the condition model.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


_OPEN_STATUSES = {"Submitted", "Approved", "In Progress", "Scheduled"}
_COMPLETED_STATUS = "Completed"


class WorkOrderReader:
    """
    Parses a work order Excel file and serves per-timestep priority lists.

    Loads the full sheet on construction and caches it. All subsequent
    queries are pandas filter operations on the in-memory DataFrame.

    Usage:
        reader = WorkOrderReader(Path("CE_Work_Orders_200.xlsx"))

        deferred, completed = reader.get_for_timestep(
            installation="Peterson SFB",
            facility_number="210",
            step_start=datetime(2026, 2, 1),
            step_end=datetime(2026, 2, 28),
        )
        model.step(deferred_reports=deferred, completed_reports=completed)
    """

    def __init__(self, excel_path: Path) -> None:
        """
        Load and pre-process the work order Excel file.

        Args:
            excel_path: Path to an Excel file produced by ce_work_order_generator.py.
        """
        df = pd.read_excel(excel_path)

        # Parse date columns, gen writes them as strings
        df["Request DateTime"] = pd.to_datetime(df["Request DateTime"], errors="coerce")
        df["Completion Date"]  = pd.to_datetime(df["Completion Date"],  errors="coerce")

        # Normalise string columns for reliable filtering
        df["Installation"]    = df["Installation"].astype(str).str.strip()
        df["Facility Number"] = df["Facility Number"].astype(str).str.strip()
        df["Status"]          = df["Status"].astype(str).str.strip()

        self._df = df

    # Public API
    def get_for_timestep(
        self,
        installation: str,
        facility_number: str,
        step_start: datetime,
        step_end: datetime,
    ) -> tuple[list[int], list[int]]:
        """
        Return deferred and completed priority lists for one timestep.

        Args:
            installation:    Installation name (e.g. "Peterson SFB").
            facility_number: Facility number string (e.g. "210").
            step_start:      Start of the timestep window (inclusive).
            step_end:        End of the timestep window (inclusive).

        Returns:
            (deferred, completed) where each is a list of int priority
            codes (1-4) for work orders in that category this step.
        """
        facility_df = self._filter_facility(installation, facility_number)

        if facility_df.empty:
            return [], []

        step_start = pd.Timestamp(step_start)
        step_end   = pd.Timestamp(step_end)

        # Deferred: submitted before step ends, still open (not completed)
        deferred_mask = (
            (facility_df["Request DateTime"] <= step_end)
            & (facility_df["Status"].isin(_OPEN_STATUSES))
        )

        # Completed: completion date falls within this step window
        completed_mask = (
            (facility_df["Completion Date"] >= step_start)
            & (facility_df["Completion Date"] <= step_end)
        )

        deferred  = facility_df.loc[deferred_mask,  "Priority Code"].dropna().astype(int).tolist()
        completed = facility_df.loc[completed_mask, "Priority Code"].dropna().astype(int).tolist()

        return deferred, completed

    def installations(self) -> list[str]:
        """Return the unique installation names in this dataset."""
        return self._df["Installation"].unique().tolist()

    def facilities(self, installation: str) -> list[str]:
        """Return facility numbers for a given installation."""
        mask = self._df["Installation"] == installation.strip()
        return self._df.loc[mask, "Facility Number"].unique().tolist()

    # Internal
    def _filter_facility(self, installation: str, facility_number: str) -> pd.DataFrame:
        mask = (
            (self._df["Installation"] == installation.strip())
            & (self._df["Facility Number"] == facility_number.strip())
        )
        return self._df.loc[mask].copy()
