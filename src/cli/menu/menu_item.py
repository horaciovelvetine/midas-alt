"""Single selectable row in a CLI menu (label, action, visibility flags)."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class MenuItem:
    """One menu row: label, callback, and display/selection flags."""

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
