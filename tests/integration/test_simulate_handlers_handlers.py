"""Scripted integration tests for :mod:`simulate_handlers` handler entry points."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.cli.handlers.simulate_handlers as simulate_handlers
from src.cli.utils.input import InputHelper


@pytest.fixture
def silenced_display(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Stub the display helpers and the inner shell so the tests don't render."""
    calls: dict[str, list] = {
        "success": [],
        "error": [],
        "warning": [],
        "info": [],
        "panel": [],
        "table": [],
    }

    def _record(kind):
        def _inner(*args, **kwargs):
            calls[kind].append((args, kwargs))

        return _inner

    monkeypatch.setattr(
        simulate_handlers.DisplayHelper, "print_success", _record("success")
    )
    monkeypatch.setattr(
        simulate_handlers.DisplayHelper, "print_error", _record("error")
    )
    monkeypatch.setattr(
        simulate_handlers.DisplayHelper, "print_warning", _record("warning")
    )
    monkeypatch.setattr(simulate_handlers.DisplayHelper, "print_info", _record("info"))
    monkeypatch.setattr(
        simulate_handlers.DisplayHelper, "print_panel", _record("panel")
    )
    monkeypatch.setattr(
        simulate_handlers.DisplayHelper, "print_table", _record("table")
    )
    monkeypatch.setattr(
        simulate_handlers.DisplayHelper, "clear_screen", staticmethod(lambda: None)
    )
    monkeypatch.setattr(
        InputHelper, "wait_for_continue", staticmethod(lambda message="": None)
    )
    return calls


def test_handle_quick_generate_exits_on_back(
    monkeypatch: pytest.MonkeyPatch, silenced_display: dict[str, list]
) -> None:
    """``handle_quick_generate`` returns when the user enters ``b`` at the prompt."""
    monkeypatch.setattr(
        InputHelper, "get_input_with_backspace", staticmethod(lambda *a, **k: "b")
    )

    simulate_handlers.handle_quick_generate()

    assert silenced_display["table"], "expected one or more summary tables rendered"


def test_handle_quick_generate_exits_on_quit_token(
    monkeypatch: pytest.MonkeyPatch, silenced_display: dict[str, list]
) -> None:
    """A ``q`` response exits the recursive prompt at the end."""
    monkeypatch.setattr(
        InputHelper, "get_input_with_backspace", staticmethod(lambda *a, **k: "q")
    )

    simulate_handlers.handle_quick_generate()


def test_handle_view_facility_and_system_warns_when_no_facilities(
    monkeypatch: pytest.MonkeyPatch, silenced_display: dict[str, list]
) -> None:
    """``handle_view_facility_and_system`` short-circuits to a warning when empty."""

    class _StubResult:
        installations = []
        facilities = []
        systems = []
        work_orders = []

    class _StubGenerator:
        def generate_installation(self):
            return _StubResult()

    monkeypatch.setattr(simulate_handlers, "DataGenerator", _StubGenerator)

    simulate_handlers.handle_view_facility_and_system()

    assert silenced_display["warning"]


def test_handle_generate_data_aborts_when_user_quits_first_step(
    monkeypatch: pytest.MonkeyPatch,
    silenced_display: dict[str, list],
) -> None:
    """Entering ``q`` at the first step exits ``handle_generate_data`` cleanly."""
    monkeypatch.setattr(
        simulate_handlers.NavigationHelper,
        "show_help",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        InputHelper, "get_input_with_backspace", staticmethod(lambda *a, **k: "q")
    )

    simulate_handlers.handle_generate_data()


def test_handle_generate_data_aborts_when_user_declines_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    silenced_display: dict[str, list],
) -> None:
    """Declining the final confirmation skips export and prints a cancel warning."""
    responses = iter(
        [
            "dataset",  # file_name
            "csv",  # file_output
            str(tmp_path),  # output_directory
            "default",  # generation_method
            "",  # description (description step prompt, skipping target_count)
        ]
    )

    def _get_input(*args, **kwargs):
        return next(responses)

    monkeypatch.setattr(
        simulate_handlers.NavigationHelper,
        "show_help",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        InputHelper, "get_input_with_backspace", staticmethod(_get_input)
    )
    monkeypatch.setattr(
        InputHelper, "ask_choice", staticmethod(lambda *a, **k: "normalized")
    )
    monkeypatch.setattr(InputHelper, "ask_yes_no", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: False))

    simulate_handlers.handle_generate_data()
    assert silenced_display["warning"]
