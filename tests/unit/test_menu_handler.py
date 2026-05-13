"""Unit tests for :class:`MenuHandler` rendering, choices, and dispatch loop."""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from rich.console import Console

import src.cli.menu.menu_handler as menu_handler_module
from src.cli.menu.menu_builder import MenuBuilder
from src.cli.menu.menu_config import MenuConfig
from src.cli.menu.menu_handler import MenuHandler
from src.cli.menu.menu_item import MenuItem
from src.cli.utils.input import InputHelper


@pytest.fixture
def recording_console(monkeypatch: pytest.MonkeyPatch) -> Console:
    """Replace the menu module console with one that records output."""
    console = Console(record=True, width=120)
    monkeypatch.setattr(menu_handler_module, "console", console)
    return console


def _scripted_prompt(
    monkeypatch: pytest.MonkeyPatch, answers: Iterable[str | None]
) -> list:
    """Patch ``InputHelper.safe_prompt_ask`` with a scripted queue and return remaining list."""
    queue = list(answers)

    def _fake_ask(*args, **kwargs):
        return queue.pop(0)

    monkeypatch.setattr(InputHelper, "safe_prompt_ask", staticmethod(_fake_ask))
    return queue


def _silence_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``InputHelper.wait_for_continue`` a no-op so tests don't block."""
    monkeypatch.setattr(
        InputHelper, "wait_for_continue", staticmethod(lambda message="": None)
    )


def test_get_choices_lists_numbers_and_navigation_tokens_for_sub_menu() -> None:
    """A non-root menu offers numeric options plus ``b``, ``q``, and ``quit``."""
    config = MenuConfig(title="Sub")
    config.items.append(MenuItem(label="One", action=lambda: None))
    config.items.append(MenuItem(label="Two", action=lambda: None))

    handler = MenuHandler(config)
    assert handler.get_choices() == ["1", "2", "b", "q", "quit"]
    assert handler.get_default_choice() == "1"


def test_get_choices_omits_back_for_root_menu() -> None:
    """A root menu does not expose ``b`` because there is nowhere to go back to."""
    config = MenuConfig(title="Root", is_root_menu=True)
    config.items.append(MenuItem(label="Only", action=lambda: None))

    handler = MenuHandler(config)
    assert handler.get_choices() == ["1", "q", "quit"]


def test_get_item_by_index_returns_item_in_range() -> None:
    """Visible items can be looked up by their 1-based index."""
    item_a = MenuItem(label="A", action=lambda: None)
    item_b = MenuItem(label="B", action=lambda: None)
    handler = MenuHandler(MenuConfig(title="X", items=[item_a, item_b]))

    assert handler.get_item_by_index(1) is item_a
    assert handler.get_item_by_index(2) is item_b
    assert handler.get_item_by_index(3) is None
    assert handler.get_item_by_index(0) is None


def test_update_item_visibility_filters_visible_list() -> None:
    """Toggling visibility updates ``_visible_items`` immediately."""
    item_a = MenuItem(label="A", action=lambda: None)
    item_b = MenuItem(label="B", action=lambda: None)
    handler = MenuHandler(MenuConfig(title="X", items=[item_a, item_b]))

    handler.update_item_visibility("A", False)
    assert handler._visible_items == [item_b]

    handler.update_item_visibility("A", True)
    assert handler._visible_items == [item_a, item_b]


def test_update_item_enabled_does_not_change_visibility() -> None:
    """``update_item_enabled`` toggles the ``enabled`` flag without filtering."""
    item = MenuItem(label="A", action=lambda: None)
    handler = MenuHandler(MenuConfig(title="X", items=[item]))

    handler.update_item_enabled("A", False)
    assert handler.config.items[0].enabled is False
    assert item.visible is True


def test_display_renders_title_items_and_descriptions(
    recording_console: Console,
) -> None:
    """The Rich panel includes the menu title and item label/description text."""
    item = MenuItem(
        label="Run Stuff", action=lambda: None, description="Kick off the thing"
    )
    handler = MenuHandler(MenuConfig(title="My Menu", items=[item]))

    handler.display()

    text = recording_console.export_text()
    assert "My Menu" in text
    assert "Run Stuff" in text
    assert "Kick off the thing" in text


def test_display_includes_back_hint_for_sub_menu(recording_console: Console) -> None:
    """Sub-menus show the ``b back`` hint line below the panel."""
    handler = MenuHandler(
        MenuConfig(
            title="Sub",
            items=[MenuItem(label="One", action=lambda: None)],
        )
    )
    handler.display()
    assert "back" in recording_console.export_text()


def test_display_includes_root_quit_hint(recording_console: Console) -> None:
    """Root menus show the quit-only hint instead of the back hint."""
    handler = MenuHandler(
        MenuConfig(
            title="Root",
            is_root_menu=True,
            items=[MenuItem(label="One", action=lambda: None)],
        )
    )
    handler.display()
    text = recording_console.export_text()
    assert "quit" in text


def test_run_calls_action_on_selection_then_back_to_caller(
    monkeypatch: pytest.MonkeyPatch, recording_console: Console
) -> None:
    """Selecting a numeric option invokes the underlying action, then ``b`` exits."""
    calls: list[str] = []

    def _action() -> None:
        calls.append("action")

    config = MenuConfig(title="Sub", items=[MenuItem(label="Run", action=_action)])
    handler = MenuHandler(config)
    _silence_wait(monkeypatch)
    _scripted_prompt(monkeypatch, ["1", "b"])

    handler.run()
    assert calls == ["action"]


def test_run_quit_invokes_quit_helper(
    monkeypatch: pytest.MonkeyPatch, recording_console: Console
) -> None:
    """Entering ``q`` triggers ``_quit_midas`` which raises ``SystemExit``."""
    handler = MenuHandler(
        MenuConfig(title="Sub", items=[MenuItem(label="X", action=lambda: None)])
    )
    _scripted_prompt(monkeypatch, ["q"])
    _silence_wait(monkeypatch)
    monkeypatch.setattr(
        menu_handler_module, "maybe_prompt_save", lambda: False, raising=False
    )
    monkeypatch.setattr(
        menu_handler_module, "force_save_on_exit", lambda: False, raising=False
    )
    monkeypatch.setattr(
        "src.cli.handlers.settings_persistence.maybe_prompt_save", lambda: False
    )
    monkeypatch.setattr(
        "src.cli.handlers.settings_persistence.force_save_on_exit", lambda: False
    )

    with pytest.raises(SystemExit):
        handler.run()


def test_run_warns_when_back_used_at_root(
    monkeypatch: pytest.MonkeyPatch, recording_console: Console
) -> None:
    """At the root menu, ``b`` prints a notice and the loop continues until ``q``."""
    handler = MenuHandler(
        MenuConfig(
            title="Root",
            is_root_menu=True,
            items=[MenuItem(label="X", action=lambda: None)],
        )
    )
    monkeypatch.setattr(
        "src.cli.handlers.settings_persistence.maybe_prompt_save", lambda: False
    )
    monkeypatch.setattr(
        "src.cli.handlers.settings_persistence.force_save_on_exit", lambda: False
    )
    _scripted_prompt(monkeypatch, ["b", "q"])
    _silence_wait(monkeypatch)

    with pytest.raises(SystemExit):
        handler.run()
    assert "main menu" in recording_console.export_text()


def test_run_skips_unselectable_item(
    monkeypatch: pytest.MonkeyPatch, recording_console: Console
) -> None:
    """A disabled visible item logs ``not available`` and keeps looping."""
    calls: list[str] = []
    item = MenuItem(label="Disabled", action=lambda: calls.append("ran"), enabled=False)
    config = MenuConfig(title="Sub", items=[item])
    handler = MenuHandler(config)
    _scripted_prompt(monkeypatch, ["1", "b"])
    _silence_wait(monkeypatch)

    handler.run()
    assert calls == []
    assert "not available" in recording_console.export_text()


def test_run_invalid_choice_warns_and_continues(
    monkeypatch: pytest.MonkeyPatch, recording_console: Console
) -> None:
    """Out-of-range selections print an invalid notice and loop again."""
    config = MenuConfig(title="Sub", items=[MenuItem(label="One", action=lambda: None)])
    handler = MenuHandler(config)
    _scripted_prompt(monkeypatch, ["1", "b"])
    _silence_wait(monkeypatch)

    handler.run()


def test_builder_returns_menu_handler() -> None:
    """``MenuBuilder.build`` returns a configured ``MenuHandler``."""
    handler = (
        MenuBuilder("Test")
        .add_item("Item", lambda: None, description="d")
        .add_separator()
        .add_item("Other", lambda: None)
        .show_shortcuts(True)
        .set_border_style("magenta")
        .set_root_menu(False)
        .build()
    )
    assert isinstance(handler, MenuHandler)
    assert handler.config.title == "Test"
    assert handler.config.show_shortcuts is True
    assert handler.config.border_style == "magenta"
    visible_labels = [item.label for item in handler.config.items if item.visible]
    assert visible_labels == ["Item", "Other"]
