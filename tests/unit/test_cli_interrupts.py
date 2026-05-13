"""Tests for CLI KeyboardInterrupt / EOF handling and wizard abort behavior."""

import pytest

from src.cli.handlers.simulate_handlers import handle_generate_data
from src.cli.menu.menu_config import MenuConfig
from src.cli.menu.menu_handler import MenuHandler
from src.cli.menu.menu_item import MenuItem
from src.cli.utils import InputHelper
from src.cli.utils import input as input_utils


def test_wait_for_continue_swallows_keyboard_interrupt(monkeypatch) -> None:
    """Pressing Ctrl-C during wait_for_continue should not propagate."""

    class FakePrompt:
        @staticmethod
        def ask(*_args, **_kwargs):
            raise KeyboardInterrupt

    monkeypatch.setattr(input_utils, "Prompt", FakePrompt)
    InputHelper.wait_for_continue()


def test_menu_run_exits_on_ctrl_c_prompt(monkeypatch) -> None:
    """Ctrl-C / EOF on the menu prompt (None) should quit the process."""
    monkeypatch.setattr(
        InputHelper,
        "safe_prompt_ask",
        staticmethod(lambda _prompt, *, choices, default: None),
    )
    monkeypatch.setattr(MenuHandler, "display", lambda self: None)
    monkeypatch.setattr(MenuHandler, "_clear_terminal_history", lambda self: None)

    ran: list[bool] = []

    config = MenuConfig(
        title="Test",
        is_root_menu=True,
        items=[MenuItem(label="Do", action=lambda: ran.append(True))],
    )
    handler = MenuHandler(config)

    with pytest.raises(SystemExit):
        handler.run()

    assert ran == []


def test_submenu_run_returns_on_b_without_running_action(monkeypatch) -> None:
    """Submenu: typing b should pop the menu without executing a numbered item."""
    monkeypatch.setattr(
        InputHelper,
        "safe_prompt_ask",
        staticmethod(lambda _prompt, *, choices, default: "b"),
    )
    monkeypatch.setattr(MenuHandler, "display", lambda self: None)
    monkeypatch.setattr(MenuHandler, "_clear_terminal_history", lambda self: None)

    ran: list[bool] = []

    config = MenuConfig(
        title="Sub",
        is_root_menu=False,
        items=[MenuItem(label="Do", action=lambda: ran.append(True))],
    )
    handler = MenuHandler(config)
    handler.run()

    assert ran == []


def test_handle_generate_data_returns_on_interrupt_after_step_one(monkeypatch) -> None:
    """Ctrl-C (None) on format step should exit wizard, not loop forever."""
    calls: list[str] = []

    def fake_get(_prompt: str, default: str = "", allow_empty: bool = False) -> str | None:
        if not calls:
            calls.append("first")
            return "my_dataset"
        return None

    monkeypatch.setattr(InputHelper, "get_input_with_backspace", staticmethod(fake_get))
    monkeypatch.setattr(InputHelper, "ask_number", staticmethod(lambda *a, **k: 1))
    monkeypatch.setattr(InputHelper, "ask_choice", staticmethod(lambda *a, **k: "normalized"))
    monkeypatch.setattr(InputHelper, "ask_yes_no", staticmethod(lambda *a, **k: False))
    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: False))

    from src.cli.handlers import simulate_handlers as sh

    monkeypatch.setattr(sh.DisplayHelper, "clear_screen", staticmethod(lambda: None))
    monkeypatch.setattr(sh.DisplayHelper, "print_table", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(sh.NavigationHelper, "show_help", staticmethod(lambda *a, **k: None))

    handle_generate_data()

    assert len(calls) == 1
