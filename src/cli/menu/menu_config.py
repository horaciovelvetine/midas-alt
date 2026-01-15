from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .menu_item import MenuItem


@dataclass
class MenuConfig:
    """Configuration for a menu.

    Attributes:
        title: Menu title.
        items: List of menu items.
        border_style: Rich border style for the menu panel.
        show_shortcuts: Whether to display keyboard shortcuts.
        auto_number: Whether to auto-number items (default: True).

    """

    title: str
    items: list["MenuItem"] = field(default_factory=list)
    border_style: str = "blue"
    show_shortcuts: bool = False
    auto_number: bool = True
