"""Unit tests for the configuration menu handler entry points."""

from __future__ import annotations

import pytest

import src.cli.handlers.config_handlers as config_handlers
from src.cli.utils.input import InputHelper
from src.config import MidasConfigData, MidasSettings
from src.models import WorkOrderText


def _make_work_order_text() -> WorkOrderText:
    """Return a minimally-populated ``WorkOrderText`` for table rendering."""
    return WorkOrderText(
        system_title="HVAC",
        trade="HVAC",
        work_category="Routine",
        priority_code=1,
        problem_description="d",
        requested_action="a",
        action_taken="t",
    )


@pytest.fixture(autouse=True)
def _capture_display_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Replace ``DisplayHelper`` print calls with recorders for assertions."""
    calls: dict[str, list] = {
        "success": [],
        "error": [],
        "warning": [],
        "info": [],
        "panel": [],
        "table": [],
        "clear": [],
    }

    def _record(kind: str, *, two: bool = True):
        def _inner(*args, **kwargs):
            calls[kind].append((args, kwargs))

        return _inner

    monkeypatch.setattr(
        config_handlers.DisplayHelper, "print_success", _record("success")
    )
    monkeypatch.setattr(config_handlers.DisplayHelper, "print_error", _record("error"))
    monkeypatch.setattr(
        config_handlers.DisplayHelper, "print_warning", _record("warning")
    )
    monkeypatch.setattr(config_handlers.DisplayHelper, "print_info", _record("info"))
    monkeypatch.setattr(config_handlers.DisplayHelper, "print_panel", _record("panel"))
    monkeypatch.setattr(config_handlers.DisplayHelper, "print_table", _record("table"))
    monkeypatch.setattr(config_handlers.DisplayHelper, "clear_screen", _record("clear"))
    monkeypatch.setattr(
        InputHelper, "wait_for_continue", staticmethod(lambda message="": None)
    )
    return calls


def test_handle_reload_configuration_skips_when_user_declines(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """A declined confirmation prints a cancellation warning and does not reload."""
    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: False))

    reload_calls: list[None] = []
    monkeypatch.setattr(
        config_handlers.ApplicationState,
        "initialize",
        classmethod(lambda cls: reload_calls.append(None) or None),
    )

    config_handlers.handle_reload_configuration()

    assert reload_calls == []
    assert _capture_display_calls["warning"]


def test_handle_reload_configuration_reports_success(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """A successful reload invokes ``print_success`` with the status message."""

    class _OkState:
        initialized_successfully = True

        def get_status_message(self) -> str:
            return "loaded ok"

    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(
        config_handlers.ApplicationState,
        "initialize",
        classmethod(lambda cls: _OkState()),
    )
    monkeypatch.setattr(config_handlers, "set_app_state", lambda state: None)

    config_handlers.handle_reload_configuration()

    assert _capture_display_calls["success"]
    assert _capture_display_calls["success"][0][0][0] == "loaded ok"


def test_handle_reload_configuration_reports_failure(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """A failed reload invokes ``print_error`` with the status message."""

    class _FailState:
        initialized_successfully = False

        def get_status_message(self) -> str:
            return "bad workbook"

    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(
        config_handlers.ApplicationState,
        "initialize",
        classmethod(lambda cls: _FailState()),
    )
    monkeypatch.setattr(config_handlers, "set_app_state", lambda state: None)

    config_handlers.handle_reload_configuration()

    assert _capture_display_calls["error"]
    assert _capture_display_calls["error"][0][0][0] == "bad workbook"


def test_handle_reload_configuration_catches_initialize_exception(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """An exception during reload is reported via ``print_error``."""

    def _raise(cls):
        raise RuntimeError("boom")

    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(
        config_handlers.ApplicationState, "initialize", classmethod(_raise)
    )

    config_handlers.handle_reload_configuration()

    assert _capture_display_calls["error"]
    assert "boom" in _capture_display_calls["error"][0][0][0]


def test_handle_edit_midas_settings_runs_editor_then_prompts_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``handle_edit_midas_settings`` runs the editor and then offers to persist."""
    invoked: list[str] = []

    monkeypatch.setattr(
        config_handlers,
        "run_settings_editor",
        lambda: invoked.append("editor"),
    )
    monkeypatch.setattr(
        config_handlers,
        "maybe_prompt_save",
        lambda: invoked.append("save"),
    )

    config_handlers.handle_edit_midas_settings()

    assert invoked == ["editor", "save"]


def test_handle_save_configuration_prints_success_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    _capture_display_calls: dict[str, list],
) -> None:
    """``handle_save_configuration`` prints the path returned by ``save_state``."""
    settings = MidasSettings()
    target = tmp_path / "midas_settings.json"

    monkeypatch.setattr(settings, "save_state", lambda: target)

    config_handlers.handle_save_configuration()

    assert _capture_display_calls["success"]
    assert "Saved current settings to" in _capture_display_calls["success"][0][0][0]


def test_handle_save_configuration_reports_oserror(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """An ``OSError`` during save is surfaced through ``print_error``."""

    def _raise():
        raise OSError("read-only filesystem")

    monkeypatch.setattr(MidasSettings(), "save_state", _raise)

    config_handlers.handle_save_configuration()

    assert _capture_display_calls["error"]
    assert "read-only" in _capture_display_calls["error"][0][0][0]


def test_view_facility_types_summary_renders_table(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """The facility-types viewer asks the config data for a table and prints it."""
    config_handlers._view_facility_types_summary()
    assert _capture_display_calls["table"]


def test_view_system_types_summary_renders_table(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """The system-types viewer asks the config data for a table and prints it."""
    config_handlers._view_system_types_summary()
    assert _capture_display_calls["table"]


def test_view_installation_locations_summary_renders_table(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """The locations viewer asks the config data for a table and prints it."""
    config_handlers._view_installation_locations_summary()
    assert _capture_display_calls["table"]


def test_view_work_order_text_summary_returns_when_no_groups(
    monkeypatch: pytest.MonkeyPatch, _capture_display_calls: dict[str, list]
) -> None:
    """An empty work-order-text cache short-circuits the browser loop."""
    monkeypatch.setattr(config_handlers, "iter_work_order_text_groups", lambda data: [])

    config_handlers._view_work_order_text_summary()
    assert _capture_display_calls["table"]


def test_view_work_order_text_summary_returns_on_empty_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pressing enter at the prompt exits the work-order browser loop."""
    monkeypatch.setattr(
        config_handlers,
        "iter_work_order_text_groups",
        lambda data: [("HVAC", [_make_work_order_text()])],
    )
    monkeypatch.setattr(
        InputHelper, "get_input_with_backspace", staticmethod(lambda *a, **k: "")
    )

    config_handlers._view_work_order_text_summary()


def test_view_work_order_text_summary_drills_into_selected_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid numeric selection drills into the corresponding group view."""
    monkeypatch.setattr(
        config_handlers,
        "iter_work_order_text_groups",
        lambda data: [("HVAC", [_make_work_order_text()])],
    )
    responses = iter(["1", ""])  # select group 1, then exit group view
    monkeypatch.setattr(
        InputHelper,
        "get_input_with_backspace",
        staticmethod(lambda *a, **k: next(responses)),
    )

    called: list[str] = []
    monkeypatch.setattr(
        config_handlers,
        "_view_work_order_text_group",
        lambda title, rows: called.append(title),
    )

    config_handlers._view_work_order_text_summary()
    assert called == ["HVAC"]


def test_view_work_order_text_group_returns_immediately_on_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An immediate blank input exits the per-group browser."""
    monkeypatch.setattr(
        InputHelper, "get_input_with_backspace", staticmethod(lambda *a, **k: "")
    )
    config_handlers._view_work_order_text_group("HVAC", [_make_work_order_text()])


def test_view_work_order_text_group_invalid_index_loops_then_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An out-of-range numeric selection prints an error and continues the loop."""
    responses = iter(["abc", "9", "1", ""])
    monkeypatch.setattr(
        InputHelper,
        "get_input_with_backspace",
        staticmethod(lambda *a, **k: next(responses)),
    )
    monkeypatch.setattr(
        config_handlers,
        "format_work_order_text_detail",
        lambda row: "detail",
    )

    config_handlers._view_work_order_text_group("HVAC", [_make_work_order_text()])
