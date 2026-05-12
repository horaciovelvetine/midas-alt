"""Configuration-related command handlers."""

import logging

from src.cli.utils import DisplayHelper, InputHelper
from src.config import (
    MidasConfigData,
    MidasSettings,
    create_config_values_panel,
    create_facility_types_table,
    create_installation_locations_table,
    create_system_types_table,
)
from src.config.app_state import ApplicationState, set_app_state

logger = logging.getLogger(__name__)


def handle_reload_configuration() -> None:
    """Reload reference data and JSON state from disk."""
    DisplayHelper.print_warning(
        "To update configuration values:\n"
        "1. Edit docs/midas_config_data.xlsx (reference data)\n"
        "2. Edit or remove output/midas_settings.json (runtime settings)\n"
        "3. Ensure the file is saved\n"
        "4. Return here and confirm to reload",
        title="Configuration Update Instructions",
    )

    if InputHelper.confirm("Have you saved your changes?", default=False):
        DisplayHelper.print_info("Reloading configuration...", title="MIDAS")
        try:
            new_state = ApplicationState.initialize()
            set_app_state(new_state)

            status_message = new_state.get_status_message()
            if new_state.initialized_successfully:
                DisplayHelper.print_success(status_message)
            else:
                DisplayHelper.print_error(status_message, title="MIDAS")

            InputHelper.wait_for_continue()
        except Exception as exc:
            error_msg = f"Error reloading configuration: {exc}"
            DisplayHelper.print_error(error_msg, title="MIDAS")
            logger.exception("Error during configuration reload")
            InputHelper.wait_for_continue()
    else:
        DisplayHelper.print_warning("Configuration reload cancelled.")


def handle_save_configuration() -> None:
    """Persist current MidasSettings state to the default JSON file."""
    try:
        target = MidasSettings().save_state()
        DisplayHelper.print_success(
            f"Saved current settings to: {target}", title="MIDAS"
        )
    except OSError as exc:
        DisplayHelper.print_error(f"Failed to save settings: {exc}", title="MIDAS")
        logger.exception("Failed to write MidasSettings state")
    InputHelper.wait_for_continue()


def handle_view_facility_types_summary() -> None:
    """View facility types summary."""
    table = create_facility_types_table(MidasConfigData())
    DisplayHelper.print_table(table)
    InputHelper.wait_for_continue()


def handle_view_system_types_summary() -> None:
    """View system types summary."""
    table = create_system_types_table(MidasConfigData())
    DisplayHelper.print_table(table)
    InputHelper.wait_for_continue()


def handle_view_installation_locations_summary() -> None:
    """View installation locations summary."""
    table = create_installation_locations_table(MidasConfigData())
    DisplayHelper.print_table(table)
    InputHelper.wait_for_continue()


def handle_view_config_values() -> None:
    """View config values summary."""
    from rich.console import Console

    console = Console()

    console.print("\n")
    console.print(
        "Config values are loaded on startup from output/midas_settings.json (if present)"
    )
    console.print(
        "and reference data from docs/midas_config_data.xlsx; missing files fall back to defaults."
    )
    console.print(
        "Use 'Save Configuration' to persist the current values for next startup."
    )
    console.print("\n")

    panel = create_config_values_panel(MidasSettings())
    console.print(panel)

    InputHelper.wait_for_continue()
