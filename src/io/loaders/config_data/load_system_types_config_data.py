import logging

import pandas as pd
from pandas import ExcelFile

from src.config.midas_settings import MidasSettings
from src.io.loaders.midas_config_data_loader import (
    ConfigDataLoadResult,
)
from src.models import SystemType

logger = logging.getLogger(__name__)


def load_system_types_config_data(excel_file: ExcelFile, result: ConfigDataLoadResult) -> dict[int, SystemType]:
    """Load ``SystemType`` instances from the ``Systems`` config data excel sheet."""
    if "Systems" not in excel_file.sheet_names:
        result.add_warning(f"Unable to find 'Systems' sheet in the {MidasSettings.DEFAULT_CONFIG_DATA_FILENAME} excel file.")
        return {}

    df = pd.read_excel(excel_file, sheet_name="Systems")
    system_types: dict[int, SystemType] = {}
    facility_keys_column = find_column(
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

            facility_keys_raw = row.get(facility_keys_column, "") if facility_keys_column else ""
            if pd.isna(facility_keys_raw):
                facility_keys: tuple[int, ...] = ()
            elif isinstance(facility_keys_raw, (int, float)):
                facility_keys = (int(facility_keys_raw),)
            else:
                facility_keys = tuple(
                    int(float(item.strip()))
                    for item in str(facility_keys_raw).split(",")
                    if item.strip() and is_numeric(item.strip())
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

    logger.info(
        "Loaded %s System Type(s) from 'Systems' in the %s excel file.",
        len(system_types),
        MidasSettings.DEFAULT_CONFIG_DATA_FILENAME,
    )
    return system_types


def find_column(columns: list[str], candidates: list[str]) -> str | None:
    """Find a matching column name from a list of candidates."""
    normalized_columns = {col.lower().replace(" ", "").replace("_", ""): col for col in columns}
    for candidate in candidates:
        normalized_candidate = candidate.lower().replace(" ", "").replace("_", "")
        if normalized_candidate in normalized_columns:
            return normalized_columns[normalized_candidate]
    return None


def is_numeric(value: str) -> bool:
    """Check whether a string can be converted to a number."""
    try:
        float(value)
        return True
    except ValueError:
        return False
