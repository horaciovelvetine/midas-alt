"""Load the MIDAS configuration workbook into settings objects."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from pandas import ExcelFile

from src.config.settings import MIDASSettings
from src.models import FacilityType, InstallationLocation, SystemType

from .config_workbook_config_values import _load_config_values, _load_distributions
from .config_workbook_work_order_text import _load_work_order_text_cache

logger = logging.getLogger(__name__)


class ConfigWorkbookLoadError(Exception):
    """Raised when the MIDAS configuration workbook cannot be loaded."""


class ConfigWorkbookLoader:
    """Load `midas_config_values.xlsx` into a configured `MIDASSettings`."""

    def load(self, workbook_path: str | Path) -> MIDASSettings:
        """Load settings and reference data from an Excel workbook."""
        path = Path(workbook_path).expanduser().resolve()
        if not path.exists():
            raise ConfigWorkbookLoadError(f"Configuration file not found: {path}")

        try:
            excel_file = ExcelFile(path)
        except (OSError, ValueError) as exc:
            raise ConfigWorkbookLoadError(
                f"Configuration load error: failed to open workbook at '{path}' ({exc})"
            ) from exc

        facility_types = _load_facility_types(excel_file)
        system_types = _load_system_types(excel_file)
        locations = _load_install_locations(excel_file)
        degradation, simulation, output, config_dict = _load_config_values(excel_file)
        distributions = _load_distributions(config_dict)
        wo_text_cache = _load_work_order_text_cache(excel_file)

        return MIDASSettings(
            degradation=degradation,
            simulation=simulation,
            output=output,
            distributions=distributions,
            facility_types=facility_types,
            system_types=system_types,
            installation_locations=locations,
            config_workbook_path=path,
            work_order_text_cache=wo_text_cache,
        )


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    """Find a matching column name from a list of candidates."""
    normalized_columns = {
        col.lower().replace(" ", "").replace("_", ""): col for col in columns
    }

    for candidate in candidates:
        normalized_candidate = candidate.lower().replace(" ", "").replace("_", "")
        if normalized_candidate in normalized_columns:
            return normalized_columns[normalized_candidate]

    return None


def _is_numeric(value: str) -> bool:
    """Check whether a string can be converted to a number."""
    try:
        float(value)
        return True
    except ValueError:
        return False


def _load_facility_types(excel_file: ExcelFile) -> dict[int, FacilityType]:
    """Load facility types from the `Facilities` sheet."""
    if "Facilities" not in excel_file.sheet_names:
        logger.warning("No 'Facilities' sheet found in config file")
        return {}

    df = pd.read_excel(excel_file, sheet_name="Facilities")
    facility_types: dict[int, FacilityType] = {}

    for _, row in df.iterrows():
        try:
            key = int(row.get("Key", 0))
            if pd.isna(key) or key == 0:
                continue

            facility_type = FacilityType(
                key=key,
                title=str(row.get("Title", "")).strip(),
                life_expectancy=int(row.get("Life Expectancy", 50)),
                mission_criticality=(
                    int(row.get("Mission Criticality", 1))
                    if not pd.isna(row.get("Mission Criticality"))
                    else 1
                ),
            )
            facility_types[key] = facility_type
        except (TypeError, ValueError) as exc:
            logger.warning("Failed to parse facility type row: %s", exc)

    logger.info("Loaded %s facility types", len(facility_types))
    return facility_types


def _load_system_types(excel_file: ExcelFile) -> dict[int, SystemType]:
    """Load system types from the `Systems` sheet."""
    if "Systems" not in excel_file.sheet_names:
        logger.warning("No 'Systems' sheet found in config file")
        return {}

    df = pd.read_excel(excel_file, sheet_name="Systems")
    system_types: dict[int, SystemType] = {}
    facility_keys_column = _find_column(
        list(df.columns),
        [
            "Facility Key(s)",
            "Facility Keys",
            "FacilityKeys",
            "Facility_Keys",
            "facility_keys",
        ],
    )

    if not facility_keys_column:
        logger.warning(
            "No 'Facility Key(s)' column found in Systems sheet. Available columns: %s. "
            "System types will have empty facility_keys.",
            list(df.columns),
        )

    for _, row in df.iterrows():
        try:
            key = int(row.get("Key", 0))
            if pd.isna(key) or key == 0:
                continue

            facility_keys_raw = (
                row.get(facility_keys_column, "") if facility_keys_column else ""
            )
            if pd.isna(facility_keys_raw):
                facility_keys = ()
            elif isinstance(facility_keys_raw, (int, float)):
                facility_keys = (int(facility_keys_raw),)
            else:
                facility_keys = tuple(
                    int(float(item.strip()))
                    for item in str(facility_keys_raw).split(",")
                    if item.strip() and _is_numeric(item.strip())
                )

            system_type = SystemType(
                key=key,
                title=str(row.get("Title", "")).strip(),
                life_expectancy=int(row.get("Life Expectancy", 30)),
                facility_keys=facility_keys,
            )
            system_types[key] = system_type
        except (TypeError, ValueError) as exc:
            logger.warning("Failed to parse system type row: %s", exc)

    logger.info("Loaded %s system types", len(system_types))
    return system_types


def _load_install_locations(excel_file: ExcelFile) -> list[InstallationLocation]:
    """Load installation locations from the workbook."""
    if "Installation Locations" not in excel_file.sheet_names:
        logger.warning("No 'Installation Locations' sheet found in config file")
        return []

    df = pd.read_excel(excel_file, sheet_name="Installation Locations")
    locations: list[InstallationLocation] = []

    for _, row in df.iterrows():
        try:
            locations.append(
                InstallationLocation(
                    title=row.get("Title", ""),
                    location=row.get("Location", ""),
                    region=row.get("Region", ""),
                    coordinates=row.get("Coordinates", ""),
                )
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Installation location parse error: invalid row data (%s)", exc
            )

    logger.info("Loaded %s Installation Locations", len(locations))
    return locations
