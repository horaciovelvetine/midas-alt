import logging

import pandas as pd
from pandas import ExcelFile

from src.io.loaders.midas_config_data_loader import ConfigDataLoadResult
from src.models import InstallationLocation

logger = logging.getLogger(__name__)


def load_install_locations_config_data(excel_file: ExcelFile, result: ConfigDataLoadResult) -> list[InstallationLocation]:
    """Load installation locations from the workbook.

    Accepts ``Installations`` (preferred, new schema) or the legacy
    ``Installation Locations`` sheet name.
    """
    from src.config.midas_settings import MidasSettings

    sheet_name: str | None = None
    for candidate in ("Installations", "Installation Locations"):
        if candidate in excel_file.sheet_names:
            sheet_name = candidate
            break

    if sheet_name is None:
        result.add_warning(
            f"Unable to find the 'Installations' sheet in the {MidasSettings.DEFAULT_CONFIG_DATA_FILENAME} excel file."
        )
        return []

    df = pd.read_excel(excel_file, sheet_name=sheet_name)
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
            logger.warning("Installation location parse error: invalid row data (%s)", exc)

    logger.info(
        "Loaded %d installation locations from %s in the %s excel file.",
        len(locations),
        sheet_name,
        MidasSettings.DEFAULT_CONFIG_DATA_FILENAME,
    )
    return locations
