"""Display utilities for CLI output formatting."""

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


class DisplayHelper:
    """Helper class for consistent display formatting across the CLI."""

    @staticmethod
    def print_panel(content: str, title: str, border_style: str = "green") -> None:
        """Print content to a panel with title.

        Args:
            content: Content to display in the panel.
            title: Panel title.
            border_style: Rich border style (default: "green").

        """
        console.print("\n")
        console.print(Panel(content, title=title, border_style=border_style))
        console.print("\n")

    @staticmethod
    def print_config_view(content: str | list[str], title: str, config_summary) -> None:
        """Print config view with combined content and config summary.

        Args:
            content: Content to display (string or list of strings).
            title: Panel title.
            config_summary: Config summary panel from create_config_values_panel().

        """
        # Convert list to string if needed
        if isinstance(content, list):
            content = "\n".join(content)

        # Extract the renderable content from the config panel
        config_content = getattr(config_summary, "_renderable", None) or getattr(
            config_summary, "renderable", config_summary
        )

        # Create a Group with the text content and config content
        combined_content = Group(
            Text(content),
            Text(""),  # Empty line separator
            config_content,
        )

        console.print("\n")
        console.print(Panel(combined_content, title=title, border_style="green"))
        console.print("\n")

    @staticmethod
    def create_summary_table(title: str, data: dict[str, str]) -> Table:
        """Create a summary table with key-value pairs.

        Args:
            title: Table title.
            data: Dictionary of key-value pairs to display.

        Returns:
            Rich Table object.

        """
        table = Table(
            title=title,
            show_header=True,
            header_style="bold cyan",
            show_lines=True,
        )
        table.add_column("Setting", style="cyan", no_wrap=True, width=30)
        table.add_column("Value", style="green", width=50)

        for key, value in data.items():
            table.add_row(key, value, style="default")

        return table

    @staticmethod
    def print_table(table: Table) -> None:
        """Print a table with consistent spacing.

        Args:
            table: Rich Table object to display.

        """
        console.print("\n")
        console.print(table)
        console.print("\n")

    @staticmethod
    def print_error(message: str, title: str = "Error") -> None:
        """Print an error message in a panel.

        Args:
            message: Error message to display.
            title: Panel title (default: "Error").

        """
        console.print("\n")
        console.print(Panel(message, title=title, border_style="red"))
        console.print("\n")

    @staticmethod
    def print_success(message: str, title: str = "Success") -> None:
        """Print a success message in a panel.

        Args:
            message: Success message to display.
            title: Panel title (default: "Success").

        """
        console.print("\n")
        console.print(Panel(message, title=title, border_style="green"))
        console.print("\n")

    @staticmethod
    def print_warning(message: str, title: str = "Warning") -> None:
        """Print a warning message in a panel.

        Args:
            message: Warning message to display.
            title: Panel title (default: "Warning").

        """
        console.print("\n")
        console.print(Panel(message, title=title, border_style="yellow"))
        console.print("\n")

    @staticmethod
    def print_info(message: str, title: str = "Information") -> None:
        """Print an info message in a panel.

        Args:
            message: Info message to display.
            title: Panel title (default: "Information").

        """
        console.print("\n")
        console.print(Panel(message, title=title, border_style="cyan"))
        console.print("\n")

    @staticmethod
    def clear_screen() -> None:
        """Clear the console screen."""
        console.clear()
