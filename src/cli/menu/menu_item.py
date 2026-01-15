from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class MenuItem:
    """Represents a menu option with its label and action.

    Attributes:
        label: Display text for the menu item.
        action: Callable to execute when item is selected.
        exit_menu: If True, exits the menu after action.
        enabled: If False, item is disabled (not selectable).
        visible: If False, item is hidden from display.
        separator_before: If True, adds a separator line before this item.
        shortcut: Optional keyboard shortcut hint (e.g., "Ctrl+C").
        description: Optional description text that summarizes what selecting this option entails.

    """

    label: str
    action: Callable[[], None]
    exit_menu: bool = False
    enabled: bool = True
    visible: bool = True
    separator_before: bool = False
    shortcut: str | None = None
    description: str | None = None

    def is_selectable(self) -> bool:
        """Check if this item can be selected."""
        return self.enabled and self.visible
