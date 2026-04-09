"""Dataclass holding title, items, and display options for a CLI menu."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .menu_item import MenuItem


@dataclass
class MenuConfig:
    """Title, item list, and Rich panel options for one menu."""

    title: str
    items: list["MenuItem"] = field(default_factory=list)
    border_style: str = "blue"
    show_shortcuts: bool = False
    auto_number: bool = True
    is_root_menu: bool = False
