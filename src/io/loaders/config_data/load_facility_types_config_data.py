import logging
import pandas as pd
from pandas import ExcelFile

from src.io.loaders.midas_config_data_loader import ConfigDataLoadResult
from src.models import FacilityType

logger = logging.getLogger(__name__)


def load_facility_types_config_data(
    excel_file: ExcelFile, result: ConfigDataLoadResult
) -> dict[int, FacilityType]:
    """Load FacilityType instances from the ``Systems`` config data excel sheet"""
    from src.config.midas_settings import MidasSettings

    if "Facilities" not in excel_file.sheet_names:
        result.add_warning(
            f"Unable to find the 'Facilities' sheet in the {MidasSettings.DEFAULT_CONFIG_DATA_FILENAME} excel file."
        )
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

    logger.info(
        f"Loaded {len(facility_types)} Facility Type(s) from the 'Facilities' sheet in the {MidasSettings.DEFAULT_CONFIG_DATA_FILENAME} excel file.",
    )
    return facility_types
