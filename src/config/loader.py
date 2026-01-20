"""Configuration loader for Excel-based settings.

Loads reference data (facility types, system types) and settings
from the midas_config_values.xlsx file.
"""

import logging
import re
from pathlib import Path
from typing import Any

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
    degradation, simulation, output, config_dict = _load_config_values(excel_file)
    
    # Load distributions from config (falls back to defaults if not specified)
    distributions = _load_distributions(config_dict)

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


# Mapping from human-readable Excel parameter names to internal setting keys
PARAMETER_KEY_MAP: dict[str, str] = {
    # Degradation settings
    "condition index degraded threshold": "condition_index_degraded_threshold",
    "resiliency grade threshold": "resiliency_grade_threshold",
    "initial condition index": "initial_condition_index",
    "maximum time series years history": "max_time_series_years",
    # Simulation settings
    "facilities per installation": "facilities_per_installation",
    "dependency chain group range": "dependency_chain_group_range",
    "maximum system age": "maximum_system_age",
    "maximum facility age": "maximum_facility_age",
    "facility condition randomly degrades chance": "facility_condition_randomly_degrades_chance",
    # Output settings
    "output excel sheet main name": "excel_sheet_main",
    "output excel sheet facility ts name": "excel_sheet_facility_ts",
    "output excel sheet system ts name": "excel_sheet_system_ts",
    "output excel sheet metadata name": "excel_sheet_metadata",
    "outputed metadata file suffix": "metadata_file_suffix",
    "outputs csv table separator": "csv_table_separator",
    # Distribution settings
    "simulated condition index distribution": "condition_index_distribution",
    "simulated age distribution": "age_distribution",
    "simulated grade distribution": "grade_distribution",
}


def _normalize_parameter_key(param: str) -> str:
    """Normalize a parameter name to a lookup key.
    
    Handles both human-readable names (from Excel Parameter column) and
    internal snake_case names (from Key/Setting column).
    """
    normalized = str(param).strip().lower()
    # If it's a human-readable name, map it to the internal key
    if normalized in PARAMETER_KEY_MAP:
        return PARAMETER_KEY_MAP[normalized]
    # Otherwise assume it's already a valid internal key
    return normalized.replace(" ", "_")


def _load_config_values(
    excel_file: ExcelFile,
) -> tuple[DegradationSettings, SimulationSettings, OutputSettings, dict[str, Any]]:
    """Load configuration values from Config sheet.
    
    Returns:
        Tuple of (DegradationSettings, SimulationSettings, OutputSettings, raw_config_dict)
        The raw config dict is returned for additional parsing (e.g., distributions).
    """
    # Return defaults if no Config sheet
    if "Config" not in excel_file.sheet_names:
        return DegradationSettings(), SimulationSettings(), OutputSettings(), {}

    df = pd.read_excel(excel_file, sheet_name="Config")

    # Build a key-value dict from the sheet
    # Support multiple possible column names: Parameter, Key, Setting
    config_dict: dict[str, Any] = {}
    for _, row in df.iterrows():
        # Try different column names for the parameter identifier
        param = row.get("Parameter") or row.get("Key") or row.get("Setting")
        # Use Value column if present, otherwise fall back to Default
        value = row.get("Value")
        if pd.isna(value):
            value = row.get("Default")
        
        if not pd.isna(param) and not pd.isna(value):
            key = _normalize_parameter_key(param)
            config_dict[key] = value

    # Parse degradation settings
    degradation = DegradationSettings(
        condition_index_degraded_threshold=float(
            config_dict.get("condition_index_degraded_threshold", 25.0)
        ),
        resiliency_grade_threshold=int(
            config_dict.get("resiliency_grade_threshold", 70)
        ),
        initial_condition_index=float(
            config_dict.get("initial_condition_index", 99.99)
        ),
        max_time_series_years=int(
            config_dict.get("max_time_series_years", 10)
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
        facility_condition_randomly_degrades_chance=int(
            config_dict.get("facility_condition_randomly_degrades_chance", 35)
        ),
    )

    # Parse output settings
    output = OutputSettings(
        excel_sheet_main=str(
            config_dict.get("excel_sheet_main", "Main Data")
        ).strip(),
        excel_sheet_facility_ts=str(
            config_dict.get("excel_sheet_facility_ts", "Facility Time Series")
        ).strip(),
        excel_sheet_system_ts=str(
            config_dict.get("excel_sheet_system_ts", "System Time Series")
        ).strip(),
        excel_sheet_metadata=str(
            config_dict.get("excel_sheet_metadata", "_metadata")
        ).strip(),
        metadata_file_suffix=str(
            config_dict.get("metadata_file_suffix", "_metadata.json")
        ).strip(),
        csv_table_separator=str(
            config_dict.get("csv_table_separator", "_")
        ).strip(),
    )

    return degradation, simulation, output, config_dict


def _parse_distribution_string(value: str) -> list[tuple[int, str]] | None:
    """Parse a distribution string from Excel into (percentage, value_range) tuples.
    
    Supports formats like:
        - "1: (7: 1-50)\\n2: (88: 50-85)\\n3: (5: 85-100)"
        - "1: (50, 20-40)\\n2: (20, 10-20)"
        - "G1: 52\\nG2: 32\\nG3: 12\\nG4: 4"
    
    Returns:
        List of (percentage, value_string) tuples, or None if parsing fails.
    """
    if not value or pd.isna(value):
        return None
    
    value_str = str(value).strip()
    segments: list[tuple[int, str]] = []
    
    # Split by newline or numbered segments
    lines = re.split(r'\n|(?=\d+:\s*\()', value_str)
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Pattern 1: "N: (percentage, range)" or "N: (percentage: range)"
        # e.g., "1: (7: 1-50)" or "1: (50, 20-40)"
        match = re.match(r'(?:\d+:\s*)?\(?\s*(\d+)\s*[,:]\s*([\d\-]+)\s*\)?', line)
        if match:
            percentage = int(match.group(1))
            value_range = match.group(2).strip()
            segments.append((percentage, value_range))
            continue
        
        # Pattern 2: "GN: percentage" for grade distributions
        # e.g., "G1: 52"
        match = re.match(r'G(\d+)\s*:\s*(\d+)', line)
        if match:
            grade = match.group(1)
            percentage = int(match.group(2))
            segments.append((percentage, grade))
            continue
    
    return segments if segments else None


def _load_distributions(config_dict: dict[str, Any]) -> SimulationDistributions:
    """Load probability distributions from config dictionary.
    
    Parses distribution strings from the config and creates ProbabilityDistribution
    objects. Falls back to defaults if parsing fails or values are not provided.
    """
    from ..simulation.distributions import ProbabilityDistribution, ProbabilitySegment
    
    condition_index = None
    age = None
    grade = None
    
    # Parse condition index distribution
    ci_str = config_dict.get("condition_index_distribution")
    if ci_str:
        segments = _parse_distribution_string(ci_str)
        if segments:
            try:
                condition_index = ProbabilityDistribution([
                    ProbabilitySegment(pct, val) for pct, val in segments
                ])
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse condition index distribution: {e}")
    
    # Parse age distribution
    age_str = config_dict.get("age_distribution")
    if age_str:
        segments = _parse_distribution_string(age_str)
        if segments:
            try:
                age = ProbabilityDistribution([
                    ProbabilitySegment(pct, val) for pct, val in segments
                ])
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse age distribution: {e}")
    
    # Parse grade distribution
    grade_str = config_dict.get("grade_distribution")
    if grade_str:
        segments = _parse_distribution_string(grade_str)
        if segments:
            try:
                grade = ProbabilityDistribution([
                    ProbabilitySegment(pct, val) for pct, val in segments
                ])
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse grade distribution: {e}")
    
    # Create distributions - None values will use defaults from __post_init__
    return SimulationDistributions(
        condition_index=condition_index,
        age=age,
        grade=grade,
    )


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
