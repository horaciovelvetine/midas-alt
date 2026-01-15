"""Factory functions for creating menu handlers."""

from rich.console import Console

from src.cli.handlers import (
    handle_create_training_dataset,
    handle_generate_data,
    handle_make_predictions,
    handle_quick_generate,
    handle_reload_configuration,
    handle_train_and_compare_models,
    handle_view_config_values,
    handle_view_facility_types_summary,
    handle_view_features,
    handle_view_simulated_data_examples,
    handle_view_system_types_summary,
)
from src.cli.menu import MenuBuilder

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
        "View Config Values",
        handle_view_config_values,
        description="View all current configuration values used by the MIDAS application",
    )
    builder.add_separator()
    builder.add_item(
        "Reload Configuration Values from File",
        handle_reload_configuration,
        description="Reload configuration values from the Excel file after making changes",
    )
    builder.add_separator()
    builder.add_item(
        "Exit back to Main Menu",
        lambda: None,
        exit_menu=True,
        description="Return to the main menu",
    )
    return builder.build()


def get_simulation_menu():
    """Create and return the simulation menu."""
    builder = MenuBuilder("Simulation Menu")
    builder.add_item(
        "Explore Simulated Data",
        handle_view_simulated_data_examples,
        description="Interactive navigation through Installation, Facility, and System entities",
    )
    builder.add_item(
        "Quick Generate & Stats",
        handle_quick_generate,
        description="Quickly generate data and view summary statistics",
    )
    builder.add_item(
        "Generate & Export Dataset",
        handle_generate_data,
        description="Full wizard to generate and export data (CSV, JSON, Excel)",
    )
    builder.add_separator()
    builder.add_item(
        "Back to Main Menu",
        lambda: None,
        exit_menu=True,
        description="Return to the main menu",
    )
    return builder.build()


def get_ml_prediction_menu():
    """Create and return the ML prediction menu."""
    builder = MenuBuilder("ML Prediction Menu")
    builder.add_item(
        "View Feature Extraction",
        handle_view_features,
        description="See what features are extracted from entities for ML models",
    )
    builder.add_item(
        "Create Training Dataset",
        handle_create_training_dataset,
        description="Generate labeled datasets for training prediction models",
    )
    builder.add_item(
        "Train & Compare Models",
        handle_train_and_compare_models,
        description="Train multiple models and compare their performance metrics",
    )
    builder.add_item(
        "Make Predictions",
        handle_make_predictions,
        description="Predict degradation timing for sample entities with confidence intervals",
    )
    builder.add_separator()
    builder.add_item(
        "Back to Main Menu",
        lambda: None,
        exit_menu=True,
        description="Return to the main menu",
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

    def handle_ml_prediction() -> None:
        """Navigate to ML prediction menu."""
        get_ml_prediction_menu().run()

    def handle_exit() -> None:
        """Exit the application."""
        console.print("\n[cyan]Exiting MIDAS[/cyan]\n")

    builder = MenuBuilder("Main Menu")
    builder.add_item(
        "Configuration",
        handle_configuration,
        description="View and manage facility types, system types, and configuration values",
    )
    builder.add_item(
        "Simulation",
        handle_simulation,
        description="Generate and explore simulated installations, facilities, and systems",
    )
    builder.add_item(
        "ML Prediction",
        handle_ml_prediction,
        description="Train models, extract features, and predict degradation timing",
    )
    builder.add_separator()
    builder.add_item(
        "Exit",
        handle_exit,
        exit_menu=True,
        description="Exit the MIDAS application",
    )
    return builder.build()
