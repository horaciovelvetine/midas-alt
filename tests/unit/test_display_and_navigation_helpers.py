"""Unit tests for ``DisplayHelper`` and ``NavigationHelper`` rendering output."""

from __future__ import annotations

import pytest
from rich.console import Console

from src.cli.utils import display as display_module
from src.cli.utils import navigation as navigation_module
from src.cli.utils.display import DisplayHelper
from src.cli.utils.navigation import NavigationHelper


@pytest.fixture
def recording_console(monkeypatch: pytest.MonkeyPatch) -> Console:
    """Replace the module-level consoles with a recording Console for assertion."""
    console = Console(record=True, width=120)
    monkeypatch.setattr(display_module, "console", console)
    monkeypatch.setattr(navigation_module, "console", console)
    return console


# ! ==========================================================================================>
# ! DisplayHelper
# ! ==========================================================================================>


def test_print_panel_renders_title_and_content(recording_console: Console) -> None:
    """``print_panel`` outputs the supplied content under the given title."""
    DisplayHelper.print_panel("Hello world", "My Title")

    text = recording_console.export_text()
    assert "Hello world" in text
    assert "My Title" in text


def test_print_table_renders_supplied_table(recording_console: Console) -> None:
    """``print_table`` calls through to render the Rich Table."""
    table = DisplayHelper.create_summary_table(
        title="Summary", data={"alpha": "1", "beta": "2"}
    )
    DisplayHelper.print_table(table)

    text = recording_console.export_text()
    assert "Summary" in text
    assert "alpha" in text
    assert "beta" in text
    assert "1" in text
    assert "2" in text


def test_print_error_renders_error_title(recording_console: Console) -> None:
    """``print_error`` puts the message in a panel titled ``Error`` by default."""
    DisplayHelper.print_error("Bad things")

    text = recording_console.export_text()
    assert "Bad things" in text
    assert "Error" in text


def test_print_success_renders_default_success_title(
    recording_console: Console,
) -> None:
    """``print_success`` renders under the ``Success`` title by default."""
    DisplayHelper.print_success("All good")

    text = recording_console.export_text()
    assert "All good" in text
    assert "Success" in text


def test_print_warning_renders_default_warning_title(
    recording_console: Console,
) -> None:
    """``print_warning`` renders under the ``Warning`` title by default."""
    DisplayHelper.print_warning("Heads up")

    text = recording_console.export_text()
    assert "Heads up" in text
    assert "Warning" in text


def test_print_info_renders_default_information_title(
    recording_console: Console,
) -> None:
    """``print_info`` renders under the ``Information`` title by default."""
    DisplayHelper.print_info("FYI")

    text = recording_console.export_text()
    assert "FYI" in text
    assert "Information" in text


def test_clear_screen_invokes_console_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    """``clear_screen`` delegates to ``console.clear`` exactly once."""
    calls: list[int] = []

    def _fake_clear() -> None:
        calls.append(1)

    monkeypatch.setattr(display_module.console, "clear", _fake_clear)
    DisplayHelper.clear_screen()
    assert calls == [1]


# ! ==========================================================================================>
# ! NavigationHelper
# ! ==========================================================================================>


def test_show_help_renders_option_name_and_description(
    recording_console: Console,
) -> None:
    """``show_help`` renders the option name and description."""
    NavigationHelper.show_help("Output Format", "Choose csv or xlsx.")

    text = recording_console.export_text()
    assert "Output Format" in text
    assert "Choose csv or xlsx." in text


def test_show_help_includes_examples_when_provided(
    recording_console: Console,
) -> None:
    """When examples are passed, they appear under the description."""
    NavigationHelper.show_help("Method", "Pick one.", examples="alpha, beta")

    text = recording_console.export_text()
    assert "alpha, beta" in text


def test_show_step_progress_includes_counter_and_step(
    recording_console: Console,
) -> None:
    """``show_step_progress`` prints ``[current/total]`` and the step name."""
    NavigationHelper.show_step_progress(2, 5, "Pick file name")

    text = recording_console.export_text()
    assert "[2/5]" in text
    assert "Pick file name" in text


@pytest.mark.parametrize("value", ["b", "back", "B", "BACK", "  b  "])
def test_can_go_back_recognizes_back_variants(value: str) -> None:
    """``can_go_back`` is case- and whitespace-insensitive for back tokens."""
    assert NavigationHelper.can_go_back(value) is True


@pytest.mark.parametrize("value", ["q", "next", "", "abc", None])
def test_can_go_back_rejects_other_inputs(value: str | None) -> None:
    """Anything other than the back tokens returns ``False``."""
    assert NavigationHelper.can_go_back(value) is False


def test_should_quit_to_menu_treats_none_as_quit() -> None:
    """``None`` (e.g. Ctrl-C / EOF) maps to a quit request."""
    assert NavigationHelper.should_quit_to_menu(None) is True


@pytest.mark.parametrize("value", ["q", "quit", "Q", "QUIT", "  q  "])
def test_should_quit_to_menu_recognizes_quit_variants(value: str) -> None:
    """``q`` and ``quit`` (any case/whitespace) trigger the quit branch."""
    assert NavigationHelper.should_quit_to_menu(value) is True


@pytest.mark.parametrize("value", ["b", "back", "1", "anything", ""])
def test_should_quit_to_menu_rejects_non_quit_strings(value: str) -> None:
    """Strings that are not quit tokens do not trigger the quit branch."""
    assert NavigationHelper.should_quit_to_menu(value) is False


def test_handle_back_command_returns_b() -> None:
    """``handle_back_command`` returns the canonical ``b`` token."""
    assert NavigationHelper.handle_back_command() == "b"
