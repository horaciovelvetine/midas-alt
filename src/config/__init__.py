"""Configuration module for the MIDAS application.

Provides:

- ``MidasSettings``: singleton container of configurable runtime settings
- ``MidasConfigData``: singleton container of reference data (facility/system
  types, installation locations, work-order text cache)
- ``ApplicationState``: thin facade that loads JSON state + workbook reference data
- ``configure_logging``: root logger bootstrap helper
- Display helpers for the Rich-based CLI summaries
"""

from .app_state import ApplicationState, get_app_state, reset_app_state, set_app_state
from .configure_logging import configure_logging
from .display import (
    create_config_values_panel,
    create_facility_types_table,
    create_installation_locations_table,
    create_settings_summary_text,
    create_system_types_table,
)
from .midas_config_data import MidasConfigData
from .midas_settings import MidasSettings
from .setting_state import (
    DistributionSettingState,
    FloatSettingState,
    IntegerSettingState,
    RangeSettingState,
    SettingState,
    StringSettingState,
)

__all__ = [
    "MidasSettings",
    "MidasConfigData",
    "SettingState",
    "FloatSettingState",
    "IntegerSettingState",
    "RangeSettingState",
    "StringSettingState",
    "DistributionSettingState",
    "ApplicationState",
    "get_app_state",
    "set_app_state",
    "reset_app_state",
    "create_facility_types_table",
    "create_system_types_table",
    "create_installation_locations_table",
    "create_config_values_panel",
    "create_settings_summary_text",
    "configure_logging",
]
