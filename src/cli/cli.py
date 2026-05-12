"""CLI interface for MIDAS application using Rich for menu-based navigation."""

import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.cli.menu.menu_factory import get_main_menu
from src.cli.utils import DisplayHelper, InputHelper
from src.config.app_state import ApplicationState, set_app_state

logger = logging.getLogger(__name__)
console = Console()


# ============================================================================
# Application Initialization
# ============================================================================


def initialize_configuration() -> None:
    """Initialize configuration from Excel file on startup."""
    DisplayHelper.print_info("Loading configuration...", title="MIDAS")

    try:
        # Initialize application state (loads configuration)
        state = ApplicationState.initialize()
        set_app_state(state)

        # Display status message
        status_message = state.get_status_message()

        if state.initialized_successfully:
            DisplayHelper.print_info(status_message, title="MIDAS")
        else:
            DisplayHelper.print_error(status_message, title="MIDAS")
            console.print("[yellow]Continuing with limited functionality...[/yellow]\n")

    except (OSError, RuntimeError, TypeError, ValueError) as e:
        error_msg = f"Configuration initialization error: expected valid startup state (got {e})"
        DisplayHelper.print_error(error_msg, title="MIDAS")
        logger.exception("Error during initial configuration load")

        # Create default state so app can continue
        set_app_state(ApplicationState.with_defaults())
        console.print("[yellow]Continuing with limited functionality...[/yellow]\n")

    # Wait for user to acknowledge initialization output before proceeding
    InputHelper.wait_for_continue("\nPress Enter to continue to the main menu")


def display_welcome() -> None:
    """Display welcome message."""
    welcome_text = Text("Welcome to MIDAS", style="bold cyan")
    console.print(Panel(welcome_text, title="MIDAS", border_style="cyan"))


# ============================================================================
# Main Entry Point
# ============================================================================


def run_cli() -> None:
    """Run the CLI application with menu navigation.

    Persists any unsaved ``MidasSettings`` changes on every exit path so
    interactive edits made via the configuration menu or the simulation shell
    are not lost on quit, Ctrl-C, or unhandled crash.
    """
    from src.cli.handlers.settings_persistence import (
        force_save_on_exit,
        maybe_prompt_save,
    )

    display_welcome()
    initialize_configuration()
    try:
        get_main_menu().run()
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye.[/dim]")
        try:
            maybe_prompt_save()
        finally:
            force_save_on_exit()
        sys.exit(0)
    finally:
        force_save_on_exit()


# ============================================================================
# Demo Entry Point
# ============================================================================


def run_demo() -> None:
    """Run the CLI startup flow without launching the main menu loop."""
    display_welcome()
    initialize_configuration()


if __name__ == "__main__":
    run_cli()
