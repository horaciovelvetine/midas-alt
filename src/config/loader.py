"""Configuration loader for Excel-based settings.

Loads reference data (facility types, system types) and settings
from the midas_config_values.xlsx file.
"""

import logging
from pathlib import Path

import pandas as pd
from pandas import DataFrame, ExcelFile

from .reference_data import FacilityType, SystemType
from .settings import (
    DegradationSettings,
    MIDASSettings,
    OutputSettings,
    SimulationDistributions,
    SimulationSettings,
)

logger = logging.getLogger(__name__)


class ConfigLoadError(Exception):
    """Raised when configuration loading fails."""

    pass


def load_settings_from_excel(path: Path) -> MIDASSettings:
    """Load MIDAS settings from Excel configuration file.

    Args:
        path: Path to the Excel configuration file.

    Returns:
        Configured MIDASSettings instance.

    Raises:
        ConfigLoadError: If the file cannot be loaded or is invalid.
    """
    if not path.exists():
        raise ConfigLoadError(f"Configuration file not found: {path}")

    try:
        excel_file = ExcelFile(path)
    except Exception as e:
        raise ConfigLoadError(f"Failed to open Excel file: {e}") from e

    # Load reference data
    facility_types = _load_facility_types(excel_file)
    system_types = _load_system_types(excel_file)

    # Load settings from Config sheet (if present)
    degradation, simulation, output = _load_config_values(excel_file)
    
    # Distributions use defaults (could be extended to load from Excel)
    distributions = SimulationDistributions()

    return MIDASSettings(
        degradation=degradation,
        simulation=simulation,
        output=output,
        distributions=distributions,
        facility_types=facility_types,
        system_types=system_types,
    )


def _load_facility_types(excel_file: ExcelFile) -> dict[int, FacilityType]:
    """Load facility types from Facilities sheet."""
    if "Facilities" not in excel_file.sheet_names:
        logger.warning("No 'Facilities' sheet found in config file")
        return {}

    df = pd.read_excel(excel_file, sheet_name="Facilities")
    facility_types = {}

    for _, row in df.iterrows():
        try:
            key = int(row.get("Key", 0))
            if pd.isna(key) or key == 0:
                continue

            facility_type = FacilityType(
                key=key,
                title=str(row.get("Title", "")).strip(),
                life_expectancy=int(row.get("Life Expectancy", 50)),
                mission_criticality=int(row.get("Mission Criticality", 1))
                if not pd.isna(row.get("Mission Criticality"))
                else 1,
            )
            facility_types[key] = facility_type
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse facility type row: {e}")
            continue

    logger.info(f"Loaded {len(facility_types)} facility types")
    return facility_types


def _load_system_types(excel_file: ExcelFile) -> dict[int, SystemType]:
    """Load system types from Systems sheet."""
    if "Systems" not in excel_file.sheet_names:
        logger.warning("No 'Systems' sheet found in config file")
        return {}

    df = pd.read_excel(excel_file, sheet_name="Systems")
    system_types = {}

    for _, row in df.iterrows():
        try:
            key = int(row.get("Key", 0))
            if pd.isna(key) or key == 0:
                continue

            # Parse facility keys (comma-separated or single value)
            facility_keys_raw = row.get("Facility Key(s)", "")
            if pd.isna(facility_keys_raw):
                facility_keys = ()
            elif isinstance(facility_keys_raw, (int, float)):
                facility_keys = (int(facility_keys_raw),)
            else:
                # Parse comma-separated string
                facility_keys = tuple(
                    int(k.strip())
                    for k in str(facility_keys_raw).split(",")
                    if k.strip().isdigit()
                )

            system_type = SystemType(
                key=key,
                title=str(row.get("Title", "")).strip(),
                life_expectancy=int(row.get("Life Expectancy", 30)),
                facility_keys=facility_keys,
            )
            system_types[key] = system_type
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse system type row: {e}")
            continue

    logger.info(f"Loaded {len(system_types)} system types")
    return system_types


def _load_config_values(
    excel_file: ExcelFile,
) -> tuple[DegradationSettings, SimulationSettings, OutputSettings]:
    """Load configuration values from Config sheet."""
    # Return defaults if no Config sheet
    if "Config" not in excel_file.sheet_names:
        return DegradationSettings(), SimulationSettings(), OutputSettings()

    df = pd.read_excel(excel_file, sheet_name="Config")

    # Build a key-value dict from the sheet
    config_dict = {}
    for _, row in df.iterrows():
        key = row.get("Key") or row.get("Setting")
        value = row.get("Value")
        if not pd.isna(key) and not pd.isna(value):
            config_dict[str(key).strip().lower()] = value

    # Parse degradation settings
    degradation = DegradationSettings(
        condition_index_degraded_threshold=float(
            config_dict.get("condition_index_degraded_threshold", 25.0)
        ),
        resiliency_grade_threshold=int(
            config_dict.get("resiliency_grade_threshold", 70)
        ),
    )

    # Parse simulation settings
    facilities_range = _parse_range(
        config_dict.get("facilities_per_installation", "8-14")
    )
    dep_chain_range = _parse_range(
        config_dict.get("dependency_chain_group_range", "1-3")
    )

    simulation = SimulationSettings(
        facilities_per_installation=facilities_range,
        dependency_chain_group_range=dep_chain_range,
        maximum_system_age=int(config_dict.get("maximum_system_age", 80)),
        maximum_facility_age=int(config_dict.get("maximum_facility_age", 80)),
    )

    # Output settings (use defaults for now)
    output = OutputSettings()

    return degradation, simulation, output


def _parse_range(value: str | int | float) -> tuple[int, int]:
    """Parse a range value like '8-14' or single value like '10'."""
    if isinstance(value, (int, float)):
        v = int(value)
        return (v, v)

    value_str = str(value).strip()
    if "-" in value_str:
        parts = value_str.split("-")
        if len(parts) == 2:
            try:
                return (int(parts[0].strip()), int(parts[1].strip()))
            except ValueError:
                pass
    try:
        v = int(value_str)
        return (v, v)
    except ValueError:
        return (8, 14)  # Default
