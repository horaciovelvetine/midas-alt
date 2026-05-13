"""CLI command handlers."""

from .config_handlers import (
    handle_edit_midas_settings,
    handle_reload_configuration,
    handle_save_configuration,
    handle_view_loaded_config_data,
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
    "handle_view_loaded_config_data",
    # Simulate handlers
    "handle_generate_data",
    "handle_quick_generate",
    "handle_view_facility_and_system",
    "handle_view_installation_interactive",
    "handle_view_simulated_data_examples",
]
