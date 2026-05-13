"""Configuration-related command handlers."""

import logging

from src.cli.handlers.settings_editor import run_settings_editor
from src.cli.handlers.settings_persistence import maybe_prompt_save
from src.cli.utils import DisplayHelper, InputHelper, NavigationHelper
from src.config import (
    MidasConfigData,
    MidasSettings,
    create_facility_types_table,
    create_installation_locations_table,
    create_system_types_table,
    create_work_order_text_summary_table,
    create_work_order_texts_for_system_table,
    format_work_order_text_detail,
    iter_work_order_text_groups,
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


def handle_edit_midas_settings() -> None:
    """Open the interactive editor for MIDAS settings; prompt to save on return."""
    run_settings_editor()
    maybe_prompt_save()


def handle_save_configuration() -> None:
    """Persist current MidasSettings state to the default JSON file."""
    try:
        target = MidasSettings().save_state()
        DisplayHelper.print_success(f"Saved current settings to: {target}", title="MIDAS")
    except OSError as exc:
        DisplayHelper.print_error(f"Failed to save settings: {exc}", title="MIDAS")
        logger.exception("Failed to write MidasSettings state")
    InputHelper.wait_for_continue()


def handle_view_loaded_config_data() -> None:
    """Open a sub-menu for browsing reference data loaded from the config workbook."""
    from src.cli.menu.menu_builder import MenuBuilder

    builder = MenuBuilder("Loaded Configuration Data")
    builder.add_item(
        "Facility Types",
        _view_facility_types_summary,
        description="List every facility type loaded from the 'Facilities' sheet",
    )
    builder.add_item(
        "System Types",
        _view_system_types_summary,
        description="List every system type loaded from the 'Systems' sheet with its parent facility keys",
    )
    builder.add_item(
        "Installation Locations",
        _view_installation_locations_summary,
        description="List every installation location loaded from the 'Installations' sheet",
    )
    builder.add_item(
        "Work Order Templates",
        _view_work_order_text_summary,
        description="Browse work-order templates grouped by system title and drill into individual rows",
    )
    builder.build().run()


def _view_facility_types_summary() -> None:
    """View facility types summary."""
    table = create_facility_types_table(MidasConfigData())
    DisplayHelper.print_table(table)
    InputHelper.wait_for_continue()


def _view_system_types_summary() -> None:
    """View system types summary."""
    table = create_system_types_table(MidasConfigData())
    DisplayHelper.print_table(table)
    InputHelper.wait_for_continue()


def _view_installation_locations_summary() -> None:
    """View installation locations summary."""
    table = create_installation_locations_table(MidasConfigData())
    DisplayHelper.print_table(table)
    InputHelper.wait_for_continue()


def _view_work_order_text_summary() -> None:
    """Interactively browse loaded work-order templates by system group."""
    config_data = MidasConfigData()
    while True:
        DisplayHelper.clear_screen()
        DisplayHelper.print_table(create_work_order_text_summary_table(config_data))
        groups = iter_work_order_text_groups(config_data)
        if not groups:
            InputHelper.wait_for_continue()
            return

        choice = InputHelper.get_input_with_backspace(
            f"Select a system (1-{len(groups)}) to view its templates, Enter / b / q to return",
            allow_empty=True,
        )
        if choice is None or choice == "" or NavigationHelper.can_go_back(choice) or NavigationHelper.should_quit_to_menu(choice):
            return

        try:
            index = int(choice) - 1
        except ValueError:
            DisplayHelper.print_error("Invalid input. Please enter a number.")
            InputHelper.wait_for_continue()
            continue
        if not 0 <= index < len(groups):
            DisplayHelper.print_error(f"Invalid selection. Please enter 1-{len(groups)}.")
            InputHelper.wait_for_continue()
            continue

        system_title, rows = groups[index]
        _view_work_order_text_group(system_title, rows)


def _view_work_order_text_group(system_title: str, rows: list) -> None:
    """Show templates for one system title and allow drill-down into a single row."""
    while True:
        DisplayHelper.clear_screen()
        DisplayHelper.print_table(create_work_order_texts_for_system_table(rows, system_title=system_title))

        choice = InputHelper.get_input_with_backspace(
            f"Select a template (1-{len(rows)}) for full text, Enter / b / q to return",
            allow_empty=True,
        )
        if choice is None or choice == "" or NavigationHelper.can_go_back(choice) or NavigationHelper.should_quit_to_menu(choice):
            return

        try:
            index = int(choice) - 1
        except ValueError:
            DisplayHelper.print_error("Invalid input. Please enter a number.")
            InputHelper.wait_for_continue()
            continue
        if not 0 <= index < len(rows):
            DisplayHelper.print_error(f"Invalid selection. Please enter 1-{len(rows)}.")
            InputHelper.wait_for_continue()
            continue

        DisplayHelper.print_panel(
            content=format_work_order_text_detail(rows[index]),
            title=f"Work Order Template #{index + 1}: {system_title}",
        )
        InputHelper.wait_for_continue()
