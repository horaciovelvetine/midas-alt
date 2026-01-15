"""CLI interface for MIDAS application using Rich for menu-based navigation."""

import logging

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.cli.menu import get_main_menu
from src.cli.utils import DisplayHelper, InputHelper
from src.config.app_state import get_app_state, set_app_state, ApplicationState

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
            
    except Exception as e:
        error_msg = f"Error loading configuration: {e}"
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
    """Run the CLI application with menu navigation."""
    display_welcome()
    initialize_configuration()
    get_main_menu().run()


if __name__ == "__main__":
    run_cli()
