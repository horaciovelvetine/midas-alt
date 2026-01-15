import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .menu_config import MenuConfig
from .menu_item import MenuItem

logger = logging.getLogger(__name__)
console = Console()


class MenuHandler:
    """Generic menu handler for displaying and processing menu selections."""

    def __init__(self, config: MenuConfig):
        """Initialize a menu handler.

        Args:
            config: Menu configuration.

        """
        self.config = config
        self._visible_items: list[MenuItem] = []
        self._update_visible_items()

    def _update_visible_items(self) -> None:
        """Update the list of visible menu items."""
        self._visible_items = [item for item in self.config.items if item.visible]

    def _clear_terminal_history(self) -> None:
        """Clear terminal scrollback history using ANSI escape codes."""
        # Clear scrollback buffer: \033[3J clears scrollback, \033[H moves cursor to top
        # \033[2J clears the screen
        if sys.stdout.isatty():
            sys.stdout.write("\033[3J\033[H\033[2J")
            sys.stdout.flush()

    def display(self) -> None:
        """Display the menu options with bottom justification."""
        # Clear screen and history
        self._clear_terminal_history()

        menu_lines = []
        item_number = 1

        for item in self.config.items:
            if not item.visible:
                continue

            # Add separator if needed
            if item.separator_before and menu_lines:
                menu_lines.append("")

            # Build menu line
            if self.config.auto_number:
                label = f"[{item_number}] {item.label}"
            else:
                label = item.label

            # Add shortcut if configured
            if self.config.show_shortcuts and item.shortcut:
                label += f" ({item.shortcut})"

            # Add description if available (on the same line)
            if item.description:
                if not item.enabled:
                    label += f"  [dim]- {item.description}[/dim]"
                else:
                    label += f"  [bright_black]- {item.description}[/bright_black]"

            # Style disabled items (wrap entire line)
            if not item.enabled:
                label = f"[dim]{label}[/dim]"

            menu_lines.append(label)

            item_number += 1

        menu_text = "\n".join(menu_lines)

        # Calculate padding for bottom justification
        # Get terminal height, accounting for the panel border and prompt
        try:
            terminal_height = console.height or 24  # Default to 24 if height unavailable
            # Estimate menu height: menu lines + panel borders (2) + title (1) + prompt area (2)
            menu_height = len(menu_lines) + 5
            # Add padding to push content to bottom
            padding_lines = max(0, terminal_height - menu_height - 2)
            padding = "\n" * padding_lines
        except Exception:
            # If we can't determine height, just use minimal padding
            padding = "\n"

        console.print(padding)
        console.print(Panel(menu_text, title=self.config.title, border_style=self.config.border_style))

    def get_choices(self) -> list[str]:
        """Get list of valid choice strings."""
        return [str(i) for i in range(1, len(self._visible_items) + 1)]

    def get_default_choice(self) -> str:
        """Get the default choice (last item, typically exit)."""
        return str(len(self._visible_items))

    def get_item_by_index(self, index: int) -> MenuItem | None:
        """Get menu item by its visible index (1-based).

        Args:
            index: 1-based index of the visible item.

        Returns:
            MenuItem if found, None otherwise.

        """
        if 1 <= index <= len(self._visible_items):
            return self._visible_items[index - 1]
        return None

    def update_item_visibility(self, label: str, visible: bool) -> None:
        """Update visibility of a menu item by label.

        Args:
            label: Label of the menu item to update.
            visible: New visibility state.

        """
        for item in self.config.items:
            if item.label == label:
                item.visible = visible
                break
        self._update_visible_items()

    def update_item_enabled(self, label: str, enabled: bool) -> None:
        """Update enabled state of a menu item by label.

        Args:
            label: Label of the menu item to update.
            enabled: New enabled state.

        """
        for item in self.config.items:
            if item.label == label:
                item.enabled = enabled
                break

    def wait_for_continue(self, message: str = "\nPress Enter to continue") -> None:
        """Wait for user to press Enter before continuing."""
        Prompt.ask(message, default="")

    def run(self) -> None:
        """Run the menu loop."""
        while True:
            self._update_visible_items()
            if not self._visible_items:
                console.print("[yellow]No menu items available.[/yellow]\n")
                break

            self.display()
            choice = Prompt.ask("\nSelect an option", choices=self.get_choices(), default=self.get_default_choice())

            try:
                item_index = int(choice)
                selected_item = self.get_item_by_index(item_index)

                if not selected_item:
                    raise IndexError(f"Invalid index: {item_index}")

                if not selected_item.is_selectable():
                    console.print("[yellow]This option is not available.[/yellow]\n")
                    self.wait_for_continue()
                    continue

                # Execute the action
                selected_item.action()

                # Clear terminal history after selection
                self._clear_terminal_history()

                # Exit menu if this is an exit item
                if selected_item.exit_menu:
                    break

            except (ValueError, IndexError) as e:
                logger.error(f"Invalid menu choice: {choice}", exc_info=e)
                console.print("[red]Invalid selection. Please try again.[/red]\n")
                self.wait_for_continue()
