"""Configuration module for MIDAS application.

Provides:
- MIDASSettings: Immutable configuration container
- ApplicationState: Runtime state management for CLI
- Display utilities for configuration visualization
- Reference data types (FacilityType, SystemType)
"""

from .app_state import ApplicationState, get_app_state, reset_app_state, set_app_state
from .display import (
    create_config_values_panel,
    create_facility_types_table,
    create_settings_summary_text,
    create_system_types_table,
)
from .functions.configure_logging import configure_logging
from .loader import ConfigLoadError, load_settings_from_excel
from .reference_data import FacilityType, SystemType
from .settings import (
    DegradationSettings,
    MIDASSettings,
    OutputSettings,
    SimulationDistributions,
    SimulationSettings,
)

__all__ = [
    # Main settings
    "MIDASSettings",
    "DegradationSettings",
    "SimulationSettings",
    "SimulationDistributions",
    "OutputSettings",
    # Reference data types
    "FacilityType",
    "SystemType",
    # Application state
    "ApplicationState",
    "get_app_state",
    "set_app_state",
    "reset_app_state",
    # Display utilities
    "create_facility_types_table",
    "create_system_types_table",
    "create_config_values_panel",
    "create_settings_summary_text",
    # Loading utilities
    "load_settings_from_excel",
    "ConfigLoadError",
    "configure_logging",
]
