from collections.abc import Callable

from .menu_config import MenuConfig
from .menu_handler import MenuHandler
from .menu_item import MenuItem


class MenuBuilder:
    """Builder class for creating menus with a fluent interface."""

    def __init__(self, title: str, border_style: str = "blue"):
        """Initialize a menu builder.

        Args:
            title: Menu title.
            border_style: Rich border style for the menu panel.

        """
        self._config = MenuConfig(title=title, border_style=border_style)

    def add_item(
        self,
        label: str,
        action: Callable[[], None],
        exit_menu: bool = False,
        enabled: bool = True,
        separator_before: bool = False,
        shortcut: str | None = None,
        description: str | None = None,
    ) -> "MenuBuilder":
        """Add a menu item.

        Args:
            label: Display text for the menu item.
            action: Callable to execute when item is selected.
            exit_menu: If True, exits the menu after action.
            enabled: If False, item is disabled.
            separator_before: If True, adds a separator before this item.
            shortcut: Optional keyboard shortcut hint.
            description: Optional description text that summarizes what selecting this option entails.

        Returns:
            Self for method chaining.

        """
        item = MenuItem(
            label=label,
            action=action,
            exit_menu=exit_menu,
            enabled=enabled,
            separator_before=separator_before,
            shortcut=shortcut,
            description=description,
        )
        self._config.items.append(item)
        return self

    def add_separator(self) -> "MenuBuilder":
        """Add a separator line to the menu.

        Returns:
            Self for method chaining.

        """
        if self._config.items:
            # Mark the next item to have a separator before it
            # We'll add a placeholder item for the separator
            separator_item = MenuItem(label="", action=lambda: None, visible=False, separator_before=True)
            self._config.items.append(separator_item)
        return self

    def set_border_style(self, style: str) -> "MenuBuilder":
        """Set the border style for the menu.

        Args:
            style: Rich border style.

        Returns:
            Self for method chaining.

        """
        self._config.border_style = style
        return self

    def show_shortcuts(self, show: bool = True) -> "MenuBuilder":
        """Enable or disable shortcut display.

        Args:
            show: Whether to show shortcuts.

        Returns:
            Self for method chaining.

        """
        self._config.show_shortcuts = show
        return self

    def build(self) -> "MenuHandler":
        """Build and return the MenuHandler.

        Returns:
            Configured MenuHandler instance.

        """
        return MenuHandler(self._config)
