"""Configuration-related command handlers."""

import logging

from rich.prompt import Confirm

from src.cli.utils import DisplayHelper, InputHelper
from src.config.app_state import get_app_state, set_app_state, ApplicationState
from src.config.display import (
    create_config_values_panel,
    create_facility_types_table,
    create_system_types_table,
)

logger = logging.getLogger(__name__)


def handle_reload_configuration() -> None:
    """Reload configuration from Excel file."""
    DisplayHelper.print_warning(
        "To update configuration values:\n"
        "1. Open the Excel config file and make your changes\n"
        "2. Save the file\n"
        "3. Return here and confirm to reload",
        title="Configuration Update Instructions",
    )

    if Confirm.ask("Have you saved your changes to the Excel file?", default=False):
        DisplayHelper.print_info("Reloading configuration...", title="MIDAS")
        try:
            # Reload configuration
            new_state = ApplicationState.initialize()
            set_app_state(new_state)

            # Display status
            status_message = new_state.get_status_message()
            
            if new_state.initialized_successfully:
                DisplayHelper.print_success(status_message)
            else:
                DisplayHelper.print_error(status_message, title="MIDAS")

            InputHelper.wait_for_continue()
        except Exception as e:
            error_msg = f"Error reloading configuration: {e}"
            DisplayHelper.print_error(error_msg, title="MIDAS")
            logger.exception("Error during configuration reload")
            InputHelper.wait_for_continue()
    else:
        DisplayHelper.print_warning("Configuration reload cancelled.")


def handle_view_facility_types_summary() -> None:
    """View facility types summary."""
    state = get_app_state()
    table = create_facility_types_table(state.settings)
    DisplayHelper.print_table(table)
    InputHelper.wait_for_continue()


def handle_view_system_types_summary() -> None:
    """View system types summary."""
    state = get_app_state()
    table = create_system_types_table(state.settings)
    DisplayHelper.print_table(table)
    InputHelper.wait_for_continue()


def handle_view_config_values() -> None:
    """View config values summary."""
    from rich.console import Console
    console = Console()
    
    console.print("\n")
    console.print("Config data contains values read on initialization (or subsequent reload)")
    console.print("These are various values used to set parameters in the MIDAS application")
    console.print("They can be changed in the 'midas_config_values.xlsx' spreadsheet.")
    console.print("\n")
    
    state = get_app_state()
    panel = create_config_values_panel(state.settings)
    console.print(panel)
    
    InputHelper.wait_for_continue()
