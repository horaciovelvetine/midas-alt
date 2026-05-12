"""CLI command handlers."""

from .config_handlers import (
    handle_edit_midas_settings,
    handle_reload_configuration,
    handle_save_configuration,
    handle_view_config_values,
    handle_view_facility_types_summary,
    handle_view_installation_locations_summary,
    handle_view_system_types_summary,
)
from .simulate_handlers import (
    handle_generate_data,
    handle_quick_generate,
    handle_view_facility_and_system,
    handle_view_installation_interactive,
    handle_view_simulated_data_examples,
)

__all__ = [
    # Config handlers
    "handle_edit_midas_settings",
    "handle_reload_configuration",
    "handle_save_configuration",
    "handle_view_config_values",
    "handle_view_facility_types_summary",
    "handle_view_installation_locations_summary",
    "handle_view_system_types_summary",
    # Simulate handlers
    "handle_generate_data",
    "handle_quick_generate",
    "handle_view_facility_and_system",
    "handle_view_installation_interactive",
    "handle_view_simulated_data_examples",
]
