"""Load the MIDAS reference-data workbook into the ``MidasConfigData`` singleton."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pandas import ExcelFile

from src.config.midas_config_data import MidasConfigData

logger = logging.getLogger(__name__)


class ConfigWorkbookLoadError(Exception):
    """Raised when the MIDAS reference-data workbook cannot be loaded."""


@dataclass
class ConfigDataLoadResult:
    """Summary of a reference-data load (counts and any warnings)."""

    facility_types_loaded: int = 0
    system_types_loaded: int = 0
    installation_locations_loaded: int = 0
    work_order_texts_loaded: int = 0

    # For surfacing unloaded details...
    warnings: list[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        """Append a non-fatal warning emitted during load."""
        self.warnings.append(message)


class MidasConfigDataLoader:
    """Load reference data from ``docs/midas_config_data.xlsx`` into the singleton."""

    def load(self, workbook_path: str | Path | None = None) -> ConfigDataLoadResult:
        """Populate the ``MidasConfigData`` singleton from ``workbook_path``.

        Args:
            workbook_path: Optional override; defaults to
                :attr:`src.config.midas_settings.MidasSettings.DEFAULT_CONFIG_DATA_PATH`.

        Returns:
            A :class:`ConfigDataLoadResult` with per-sheet counts and warnings.

        Raises:
            ConfigWorkbookLoadError: If the workbook cannot be opened or located.

        """
        from src.config.midas_settings import MidasSettings
        from src.io.loaders.config_data import (
            load_facility_types_config_data,
            load_install_locations_config_data,
            load_system_types_config_data,
            load_work_order_text_config_data,
        )

        path = Path(workbook_path if workbook_path is not None else MidasSettings.DEFAULT_CONFIG_DATA_PATH).expanduser().resolve()
        if not path.exists():
            raise ConfigWorkbookLoadError(f"Configuration file not found: {path}")

        try:
            excel_file = ExcelFile(path)
        except (OSError, ValueError) as exc:
            raise ConfigWorkbookLoadError(f"Configuration load error: failed to open workbook at '{path}' ({exc})") from exc

        result = ConfigDataLoadResult()

        facility_types = load_facility_types_config_data(excel_file, result)
        system_types = load_system_types_config_data(excel_file, result)
        locations = load_install_locations_config_data(excel_file, result)
        wo_text_cache = load_work_order_text_config_data(excel_file, result)

        MidasConfigData().replace_reference_data(
            facility_types=facility_types,
            system_types=system_types,
            installation_locations=locations,
            work_order_text_cache=wo_text_cache,
            config_workbook_path=path,
        )

        result.facility_types_loaded = len(facility_types)
        result.system_types_loaded = len(system_types)
        result.installation_locations_loaded = len(locations)

        from src.io.loaders.config_data.load_work_order_text_config_data import (
            FALLBACK_KEY,
        )

        result.work_order_texts_loaded = len(wo_text_cache.get(FALLBACK_KEY, []))
        return result
