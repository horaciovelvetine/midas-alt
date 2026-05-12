"""Factory functions for creating menu handlers."""

from rich.console import Console

from src.cli.handlers.config_handlers import (
    handle_reload_configuration,
    handle_save_configuration,
    handle_view_config_values,
    handle_view_facility_types_summary,
    handle_view_installation_locations_summary,
    handle_view_system_types_summary,
)
from src.cli.handlers.simulate_handlers import (
    handle_generate_data,
    handle_quick_generate,
    handle_run_time_simulation,
    handle_view_facility_and_system,
    handle_view_simulated_data_examples,
)
from src.cli.menu.menu_builder import MenuBuilder

console = Console()


def get_configuration_menu():
    """Create and return the configuration menu."""
    builder = MenuBuilder("Configuration Menu")
    builder.add_item(
        "View Facility Types Summary",
        handle_view_facility_types_summary,
        description="Display a summary of all facility types loaded from the configuration file",
    )
    builder.add_item(
        "View System Types Summary",
        handle_view_system_types_summary,
        description="Display a summary of all system types loaded from the configuration file",
    )
    builder.add_item(
        "View Installation Locations Summary",
        handle_view_installation_locations_summary,
        description="Display a summary of all installation locations loaded from the configuration file",
    )
    builder.add_item(
        "View Config Values",
        handle_view_config_values,
        description="View all current configuration values used by the MIDAS application",
    )
    builder.add_separator()
    builder.add_item(
        "Reload Configuration Values from File",
        handle_reload_configuration,
        description="Reload reference data and JSON state from disk after making changes",
    )
    builder.add_item(
        "Save Current Settings to JSON",
        handle_save_configuration,
        description="Persist current MIDAS settings to output/midas_settings.json so they reload at next startup",
    )
    return builder.build()


def get_simulation_menu():
    """Create and return the simulation menu."""
    builder = MenuBuilder("Simulation Menu")
    builder.add_item(
        "Explore Simulated Data",
        handle_view_simulated_data_examples,
        description="Interactive navigation through installation, facility, system, and work-order entities",
    )
    builder.add_item(
        "View Single Facility + System",
        handle_view_facility_and_system,
        description="Generate one installation, pick a facility/system, and list or open full detail for generated work orders",
    )
    builder.add_item(
        "Quick Generate & Stats",
        handle_quick_generate,
        description="Quickly generate data and view summary statistics including work-order counts and status/priority breakdown",
    )
    builder.add_item(
        "Generate & Export Dataset",
        handle_generate_data,
        description="Full wizard to generate and export data (CSV, Excel)",
    )
    return builder.build()


def get_main_menu():
    """Create and return the main menu."""

    def handle_configuration() -> None:
        """Navigate to configuration menu."""
        get_configuration_menu().run()

    def handle_simulation() -> None:
        """Navigate to simulation menu."""
        get_simulation_menu().run()

    # def handle_ml_prediction() -> None:
    #     """Navigate to ML prediction menu."""
    #     get_ml_prediction_menu().run()

    builder = MenuBuilder("Main Menu")
    builder.set_root_menu(True)
    builder.add_item(
        "Run Time Simulation",
        handle_run_time_simulation,
        description="Load or generate one installation and run a live time-stepped simulation shell (dashboard includes work-order status counts)",
    )
    builder.add_item(
        "Data Generation & Schema",
        handle_simulation,
        description="Explore generated data (including work orders), inspect hierarchies, and export simulation datasets",
    )
    builder.add_item(
        "Configuration",
        handle_configuration,
        description="View and manage facility types, system types, and configuration values",
    )
    return builder.build()
