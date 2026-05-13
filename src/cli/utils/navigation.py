"""Navigation utilities for CLI flow management."""

from rich.console import Console
from rich.panel import Panel

console = Console()


class NavigationHelper:
    """Helper class for navigation and flow control."""

    @staticmethod
    def show_help(option_name: str, description: str, examples: str = "") -> None:
        """Display help information for an option.

        Args:
            option_name: Name of the option.
            description: Description of what the option does.
            examples: Optional examples of valid values.

        """
        help_text = f"[cyan]{option_name}[/cyan]\n{description}"
        if examples:
            help_text += f"\n\n[dim]Examples: {examples}[/dim]"
        console.print(Panel(help_text, title="Option Information", border_style="blue"))
        console.print("\n")

    @staticmethod
    def show_step_progress(current: int, total: int, step_name: str) -> None:
        """Display progress indicator for multi-step processes.

        Args:
            current: Current step number (1-based).
            total: Total number of steps.
            step_name: Name of the current step.

        """
        console.print(f"[dim][{current}/{total}][/dim] [cyan]{step_name}[/cyan]\n")

    @staticmethod
    def can_go_back(value: str | None) -> bool:
        """Check if user input indicates going back one level (b / back)."""
        if value is None:
            return False
        return value.lower().strip() in ["b", "back"]

    @staticmethod
    def should_quit_to_menu(value: str | None) -> bool:
        """Return ``True`` for Ctrl-C / EOF (None) or explicit ``q`` / ``quit`` input."""
        if value is None:
            return True
        return value.lower().strip() in ["q", "quit"]

    @staticmethod
    def handle_back_command() -> str:
        """Get the standard back command string.

        Returns:
            String indicating back command.

        """
        return "b"
