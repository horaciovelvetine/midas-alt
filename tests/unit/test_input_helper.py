"""Unit tests for :class:`InputHelper` prompt behavior and quit/back flows."""

from __future__ import annotations

import builtins
from collections.abc import Iterable
from typing import Any

import pytest
from rich.prompt import Confirm, Prompt

from src.cli.utils.input import InputHelper


@pytest.fixture
def patched_input(monkeypatch: pytest.MonkeyPatch):
    """Patch ``builtins.input`` to consume a scripted queue of responses."""

    def _install(responses: Iterable[str | type[BaseException]]):
        queue = list(responses)

        def _fake_input(prompt: str = "") -> str:
            value = queue.pop(0)
            if isinstance(value, type) and issubclass(value, BaseException):
                raise value
            return value

        monkeypatch.setattr(builtins, "input", _fake_input)
        return queue

    return _install


@pytest.fixture
def patched_prompt(monkeypatch: pytest.MonkeyPatch):
    """Patch ``rich.prompt.Prompt.ask`` to return scripted values in order."""

    def _install(responses: Iterable[Any | type[BaseException]]):
        queue = list(responses)

        def _fake_ask(*args, **kwargs):
            value = queue.pop(0)
            if isinstance(value, type) and issubclass(value, BaseException):
                raise value
            return value

        monkeypatch.setattr(Prompt, "ask", staticmethod(_fake_ask))
        return queue

    return _install


@pytest.fixture
def patched_confirm(monkeypatch: pytest.MonkeyPatch):
    """Patch ``rich.prompt.Confirm.ask`` to return scripted values in order."""

    def _install(responses: Iterable[Any | type[BaseException]]):
        queue = list(responses)

        def _fake_ask(*args, **kwargs):
            value = queue.pop(0)
            if isinstance(value, type) and issubclass(value, BaseException):
                raise value
            return value

        monkeypatch.setattr(Confirm, "ask", staticmethod(_fake_ask))
        return queue

    return _install


# ! ==========================================================================================>
# ! get_input_with_backspace
# ! ==========================================================================================>


def test_get_input_with_backspace_returns_stripped_value(patched_input) -> None:
    """Whitespace is trimmed and the trimmed value is returned."""
    patched_input(["  hello  "])
    assert InputHelper.get_input_with_backspace("prompt") == "hello"


def test_get_input_with_backspace_returns_default_when_blank(patched_input) -> None:
    """Blank input falls back to the default value when one is set."""
    patched_input([""])
    assert (
        InputHelper.get_input_with_backspace("prompt", default="fallback") == "fallback"
    )


def test_get_input_with_backspace_returns_empty_string_when_no_default(
    patched_input,
) -> None:
    """Blank input returns the empty string when no default is configured."""
    patched_input([""])
    assert InputHelper.get_input_with_backspace("prompt") == ""


def test_get_input_with_backspace_returns_none_when_allow_empty(patched_input) -> None:
    """Blank input + ``allow_empty`` returns ``None`` to signal go-back."""
    patched_input([""])
    assert InputHelper.get_input_with_backspace("prompt", allow_empty=True) is None


def test_get_input_with_backspace_returns_none_on_keyboard_interrupt(
    patched_input,
) -> None:
    """``KeyboardInterrupt`` is caught and surfaced as ``None``."""
    patched_input([KeyboardInterrupt])
    assert InputHelper.get_input_with_backspace("prompt") is None


# ! ==========================================================================================>
# ! ask_yes_no
# ! ==========================================================================================>


def test_ask_yes_no_returns_true_on_yes(patched_prompt) -> None:
    """``yes`` and ``y`` both map to ``True``."""
    patched_prompt(["yes"])
    assert InputHelper.ask_yes_no("ok?") is True


def test_ask_yes_no_returns_false_on_no(patched_prompt) -> None:
    """``no`` maps to ``False``."""
    patched_prompt(["no"])
    assert InputHelper.ask_yes_no("ok?") is False


def test_ask_yes_no_back_returns_none(patched_prompt) -> None:
    """``b`` with ``allow_back=True`` returns ``None``."""
    patched_prompt(["b"])
    assert InputHelper.ask_yes_no("ok?", allow_back=True) is None


def test_ask_yes_no_quit_flow_returns_sentinel(patched_prompt) -> None:
    """``q`` with ``allow_quit_flow=True`` returns the quit sentinel."""
    patched_prompt(["q"])
    assert (
        InputHelper.ask_yes_no("ok?", allow_quit_flow=True) is InputHelper.QUIT_TO_MENU
    )


def test_ask_yes_no_keyboard_interrupt_with_quit_flow_returns_sentinel(
    patched_prompt,
) -> None:
    """Ctrl-C returns the quit sentinel when quit-flow is allowed."""
    patched_prompt([KeyboardInterrupt])
    assert (
        InputHelper.ask_yes_no("ok?", allow_quit_flow=True) is InputHelper.QUIT_TO_MENU
    )


def test_ask_yes_no_keyboard_interrupt_returns_none_without_quit_flow(
    patched_prompt,
) -> None:
    """Without quit-flow, Ctrl-C is downgraded to ``None``."""
    patched_prompt([KeyboardInterrupt])
    assert InputHelper.ask_yes_no("ok?") is None


# ! ==========================================================================================>
# ! ask_choice
# ! ==========================================================================================>


def test_ask_choice_returns_selected_value(patched_prompt) -> None:
    """The selected choice string is returned verbatim."""
    patched_prompt(["beta"])
    assert InputHelper.ask_choice("pick", ["alpha", "beta", "gamma"]) == "beta"


def test_ask_choice_back_returns_none(patched_prompt) -> None:
    """``b`` with ``allow_back=True`` returns ``None``."""
    patched_prompt(["b"])
    assert InputHelper.ask_choice("pick", ["x"], allow_back=True) is None


def test_ask_choice_quit_returns_sentinel(patched_prompt) -> None:
    """``q`` with ``allow_quit_flow=True`` returns the quit sentinel."""
    patched_prompt(["quit"])
    assert (
        InputHelper.ask_choice("pick", ["x"], allow_quit_flow=True)
        is InputHelper.QUIT_TO_MENU
    )


# ! ==========================================================================================>
# ! ask_number
# ! ==========================================================================================>


def test_ask_number_returns_parsed_value(patched_input) -> None:
    """A valid integer string is returned as ``int``."""
    patched_input(["42"])
    assert InputHelper.ask_number("count") == 42


def test_ask_number_back_returns_none_when_allowed(patched_input) -> None:
    """Blank input + ``allow_back`` returns ``None`` immediately."""
    patched_input([""])
    assert InputHelper.ask_number("count", allow_back=True) is None


def test_ask_number_quit_sentinel(patched_input) -> None:
    """``q`` with ``allow_quit_flow=True`` returns the quit sentinel."""
    patched_input(["q"])
    assert (
        InputHelper.ask_number("count", allow_quit_flow=True)
        is InputHelper.QUIT_TO_MENU
    )


def test_ask_number_re_prompts_on_below_minimum(patched_input) -> None:
    """Sub-minimum input loops until a valid value is supplied."""
    patched_input(["0", "5"])
    assert InputHelper.ask_number("count", min_value=1) == 5


def test_ask_number_re_prompts_on_above_maximum(patched_input) -> None:
    """Above-maximum input loops until a valid value is supplied."""
    patched_input(["99", "5"])
    assert InputHelper.ask_number("count", max_value=10) == 5


def test_ask_number_re_prompts_on_invalid_input(patched_input) -> None:
    """Non-numeric input triggers a re-prompt without raising."""
    patched_input(["abc", "12"])
    assert InputHelper.ask_number("count") == 12


def test_ask_number_keyboard_interrupt_no_quit_returns_none(patched_input) -> None:
    """Without quit-flow, a Ctrl-C from the underlying input call returns ``None``."""
    patched_input([KeyboardInterrupt])
    assert InputHelper.ask_number("count") is None


# ! ==========================================================================================>
# ! safe_prompt_ask
# ! ==========================================================================================>


def test_safe_prompt_ask_returns_value(patched_prompt) -> None:
    """A successful Rich prompt returns the chosen value."""
    patched_prompt(["a"])
    assert InputHelper.safe_prompt_ask("pick", choices=["a", "b"], default="a") == "a"


def test_safe_prompt_ask_returns_none_on_keyboard_interrupt(patched_prompt) -> None:
    """``Prompt.ask`` raising Ctrl-C is downgraded to ``None``."""
    patched_prompt([KeyboardInterrupt])
    assert InputHelper.safe_prompt_ask("pick", choices=["a"], default="a") is None


# ! ==========================================================================================>
# ! wait_for_continue
# ! ==========================================================================================>


def test_wait_for_continue_returns_none_after_prompt(patched_prompt) -> None:
    """``wait_for_continue`` returns ``None`` after a successful prompt."""
    patched_prompt([""])
    assert InputHelper.wait_for_continue() is None


def test_wait_for_continue_swallows_keyboard_interrupt(patched_prompt) -> None:
    """Ctrl-C during ``wait_for_continue`` is swallowed and returns ``None``."""
    patched_prompt([KeyboardInterrupt])
    assert InputHelper.wait_for_continue() is None


# ! ==========================================================================================>
# ! confirm
# ! ==========================================================================================>


def test_confirm_returns_true(patched_confirm) -> None:
    """``Confirm.ask`` returning ``True`` propagates."""
    patched_confirm([True])
    assert InputHelper.confirm("ok?") is True


def test_confirm_returns_false(patched_confirm) -> None:
    """``Confirm.ask`` returning ``False`` propagates."""
    patched_confirm([False])
    assert InputHelper.confirm("ok?") is False


def test_confirm_returns_false_on_keyboard_interrupt(patched_confirm) -> None:
    """Ctrl-C during confirm is downgraded to ``False``."""
    patched_confirm([KeyboardInterrupt])
    assert InputHelper.confirm("ok?") is False
