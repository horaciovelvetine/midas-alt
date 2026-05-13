"""Unit tests for ``SimulationShell._handle_keypress`` dispatch logic."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest
from rich.console import Console

# Import the handlers package first so its sibling-import dance completes before
# the deeper ``simulation_shell`` module is pulled in directly.
import src.cli.handlers  # noqa: F401
import src.cli.simulation_shell as shell_module
from src.cli.simulation_shell import SimulationShell, _TerminalKeyReader
from src.models import DataStore, Facility, Installation, System
from src.simulation.runtime.clock import SimulationClock, TickSize, TickUnit
from src.simulation.runtime.session import SimulationSession


@pytest.fixture
def shell() -> SimulationShell:
    """Build a minimal :class:`SimulationShell` whose live loop is never started."""
    installation = Installation(id="i-1", title="Base", facility_ids=["f-1"])
    facility = Facility(id="f-1", installation_id=installation.id, system_ids=["s-1"])
    system = System(id="s-1", facility_id=facility.id, condition_index=80.0)
    data = DataStore(
        installations=[installation],
        facilities=[facility],
        systems=[system],
        work_orders=[],
    )
    session = SimulationSession(
        result=data,
        clock=SimulationClock(
            current_date=date(2026, 1, 1), tick_size=TickSize(1, TickUnit.DAY)
        ),
        modules=[],
        pause_policies=[],
    )
    return SimulationShell(session, shell_console=Console())


class _DummyLive:
    """Stand-in for Rich's ``Live`` object with start/stop noop methods."""

    def __init__(self) -> None:
        self.stop_calls = 0
        self.start_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1

    def start(self) -> None:
        self.start_calls += 1


class _DummyKeyReader:
    """Stand-in for ``_TerminalKeyReader`` with enable/disable noops."""

    def __init__(self) -> None:
        self.enable_calls = 0
        self.disable_calls = 0

    def enable(self) -> None:
        self.enable_calls += 1

    def disable(self) -> None:
        self.disable_calls += 1


def _dispatch(shell: SimulationShell, key: str) -> tuple[_DummyLive, _DummyKeyReader]:
    """Invoke ``_handle_keypress`` with dummy live/reader and return them."""
    live = _DummyLive()
    reader = _DummyKeyReader()
    shell._handle_keypress(key, live=live, key_reader=reader)
    return live, reader


def test_q_sets_should_exit(shell: SimulationShell) -> None:
    """The ``q`` key flips ``_should_exit`` so the loop can terminate."""
    _dispatch(shell, "q")
    assert shell._should_exit is True


def test_ctrl_c_sets_should_exit(shell: SimulationShell) -> None:
    """``\\x03`` (Ctrl-C raw byte) also triggers exit."""
    _dispatch(shell, "\x03")
    assert shell._should_exit is True


def test_space_toggles_paused(shell: SimulationShell) -> None:
    """Space resumes a paused session and pauses a running one."""
    shell.session.paused = True
    _dispatch(shell, " ")
    assert shell.session.paused is False

    _dispatch(shell, " ")
    assert shell.session.paused is True


def test_p_toggles_paused(shell: SimulationShell) -> None:
    """``p`` mirrors the space-key pause toggle."""
    shell.session.paused = False
    _dispatch(shell, "p")
    assert shell.session.paused is True


def test_n_pauses_and_steps_once(shell: SimulationShell) -> None:
    """``n`` pauses the session and immediately steps one tick."""
    shell.session.paused = False
    step_calls: list[None] = []
    shell.session.step = lambda: step_calls.append(None)  # type: ignore[method-assign]

    _dispatch(shell, "n")
    assert shell.session.paused is True
    assert step_calls == [None]


def test_plus_calls_increase_speed(shell: SimulationShell) -> None:
    """``+`` invokes ``session.increase_speed`` once."""
    calls: list[None] = []
    shell.session.increase_speed = lambda: calls.append(None) or 0.0  # type: ignore[method-assign]

    _dispatch(shell, "+")
    assert calls == [None]


def test_minus_calls_decrease_speed(shell: SimulationShell) -> None:
    """``-`` invokes ``session.decrease_speed`` once."""
    calls: list[None] = []
    shell.session.decrease_speed = lambda: calls.append(None) or 0.0  # type: ignore[method-assign]

    _dispatch(shell, "-")
    assert calls == [None]


def test_t_calls_cycle_tick_size(shell: SimulationShell) -> None:
    """``t`` calls ``session.cycle_tick_size`` exactly once."""
    calls: list[None] = []
    shell.session.cycle_tick_size = lambda: calls.append(None) or TickSize()  # type: ignore[method-assign]

    _dispatch(shell, "t")
    assert calls == [None]


def test_f_toggles_show_systems(shell: SimulationShell) -> None:
    """``f`` toggles ``show_systems`` between ``False`` and ``True``."""
    shell.show_systems = False
    _dispatch(shell, "f")
    assert shell.show_systems is True
    _dispatch(shell, "f")
    assert shell.show_systems is False


def test_h_toggles_show_help(shell: SimulationShell) -> None:
    """``h`` toggles the controls help overlay."""
    shell.show_help = True
    _dispatch(shell, "h")
    assert shell.show_help is False
    _dispatch(shell, "h")
    assert shell.show_help is True


def test_i_invokes_focus_prompt_inside_suspended_live(
    shell: SimulationShell, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``i`` pauses, suspends the live render, and calls the focus prompt."""
    called: list[None] = []
    monkeypatch.setattr(
        shell_module, "prompt_for_focus_selection", lambda session: called.append(None)
    )

    live, reader = _dispatch(shell, "i")

    assert shell.session.paused is True
    assert called == [None]
    assert live.stop_calls == 1 and live.start_calls == 1
    assert reader.disable_calls == 1 and reader.enable_calls == 1


def test_a_skips_when_no_alerts(
    shell: SimulationShell, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``a`` does nothing visible when there are no mission alerts."""
    monkeypatch.setattr(shell_module, "collect_mission_alert_items", lambda s: [])

    called: list[None] = []
    monkeypatch.setattr(
        shell_module,
        "prompt_mission_alert_browser",
        lambda session: called.append(None),
    )

    shell.session.paused = False
    _dispatch(shell, "a")

    assert called == []
    assert shell.session.paused is False


def test_a_opens_browser_when_alerts_exist(
    shell: SimulationShell, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``a`` pauses and opens the mission alert browser when alerts exist."""
    monkeypatch.setattr(shell_module, "collect_mission_alert_items", lambda s: ["fake"])

    called: list[None] = []
    monkeypatch.setattr(
        shell_module,
        "prompt_mission_alert_browser",
        lambda session: called.append(None),
    )

    _dispatch(shell, "a")
    assert shell.session.paused is True
    assert called == [None]


def test_s_opens_settings_editor_inside_suspended_live(
    shell: SimulationShell, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``s`` opens the settings editor and prompts to save on return."""
    invoked: list[str] = []
    monkeypatch.setattr(
        shell_module, "run_settings_editor", lambda: invoked.append("editor")
    )
    monkeypatch.setattr(
        shell_module, "maybe_prompt_save", lambda: invoked.append("save")
    )

    live, _reader = _dispatch(shell, "s")

    assert invoked == ["editor", "save"]
    assert shell.session.paused is True
    assert live.stop_calls == 1 and live.start_calls == 1


def test_unrecognized_keys_are_ignored(shell: SimulationShell) -> None:
    """Unknown keys leave session state untouched."""
    previous = shell.session.paused
    _dispatch(shell, "z")
    assert shell.session.paused is previous


# ! ==========================================================================================>
# ! _TerminalKeyReader behavior in non-TTY mode
# ! ==========================================================================================>


def test_terminal_key_reader_poll_returns_none_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When stdin is not a TTY, ``enable`` is a no-op and ``poll`` sleeps then returns ``None``."""

    class _FakeStdin:
        @staticmethod
        def isatty() -> bool:
            return False

    monkeypatch.setattr(shell_module.sys, "stdin", _FakeStdin())

    sleep_calls: list[float] = []
    monkeypatch.setattr(
        shell_module.time, "sleep", lambda timeout: sleep_calls.append(timeout)
    )

    reader = _TerminalKeyReader()
    reader.enable()
    assert reader._enabled is False
    assert reader.poll(0.01) is None
    assert sleep_calls == [0.01]
