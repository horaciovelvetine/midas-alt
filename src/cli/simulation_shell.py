"""Interactive Rich-based shell for time-stepped simulation sessions."""

from __future__ import annotations

import select
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from src.cli.handlers.settings_editor import run_settings_editor
from src.cli.handlers.settings_persistence import (
    force_save_on_exit,
    maybe_prompt_save,
)
from src.cli.simulation_shell_panels import (
    build_controls_panel,
    build_dependency_tree,
    build_inspect_panel,
    build_installation_summary_panel,
    build_mission_alert_panel,
    build_settings_snapshot_panel,
    build_simulation_overview_panel,
    build_work_order_summary_panel,
    collect_mission_alert_items,
    prompt_for_focus_selection,
    prompt_mission_alert_browser,
)
from src.cli.utils import DisplayHelper
from src.simulation.runtime import SimulationSession

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - used only on non-POSIX systems
    termios = None
    tty = None

console = Console()


class SimulationShell:
    """Run an interactive dashboard over a single simulation session."""

    def __init__(
        self, session: SimulationSession, shell_console: Console | None = None
    ) -> None:
        """Store shell state for an active simulation session."""
        self.session = session
        self.console = shell_console or console
        self.show_help = True
        self.show_systems = False
        self._should_exit = False

    def run(self) -> None:
        """Run the live simulation shell until the user exits."""
        interrupted = False
        with Live(
            self.render_dashboard(),
            console=self.console,
            auto_refresh=False,
            screen=True,
            transient=False,
        ) as live:
            with _TerminalKeyReader() as key_reader:
                try:
                    while not self._should_exit:
                        timeout = (
                            self.session.playback_delay_seconds
                            if not self.session.paused
                            else 0.1
                        )
                        key = key_reader.poll(timeout=timeout)
                        if key is not None:
                            self._handle_keypress(key, live=live, key_reader=key_reader)
                        elif not self.session.paused:
                            self.session.step()
                        live.update(self.render_dashboard(), refresh=True)
                except KeyboardInterrupt:
                    interrupted = True
                    self._should_exit = True

        if interrupted:
            DisplayHelper.print_info(
                "Interrupted (Ctrl-C); exited simulation shell.",
                title="Simulation",
            )
        else:
            DisplayHelper.print_info("Exited simulation shell.", title="Simulation")
        try:
            maybe_prompt_save()
        finally:
            force_save_on_exit()

    def render_dashboard(self):
        """Build the full live dashboard renderable."""
        top_row = Table.grid(expand=True)
        top_row.add_column(ratio=11)
        top_row.add_column(ratio=9)
        top_row.add_column(ratio=10)
        top_row.add_row(
            build_installation_summary_panel(self.session),
            build_simulation_overview_panel(self.session),
            build_work_order_summary_panel(self.session),
        )

        body_row = Table.grid(expand=True)
        body_row.add_column(ratio=2)
        body_row.add_column(ratio=1)
        body_row.add_column(ratio=1)
        body_row.add_row(
            Panel(
                build_dependency_tree(
                    session=self.session,
                    show_systems=self.show_systems,
                ),
                title="Installation Graph",
                border_style="cyan",
            ),
            build_inspect_panel(self.session),
            build_settings_snapshot_panel(self.session),
        )

        renderables: list[object] = [top_row]
        alert_panel = build_mission_alert_panel(self.session)
        if alert_panel is not None:
            renderables.append(alert_panel)
        renderables.append(body_row)
        if self.show_help:
            renderables.append(build_controls_panel())
        return Group(*renderables)

    def _handle_keypress(
        self, key: str, live: Live, key_reader: _TerminalKeyReader
    ) -> None:
        """Interpret a single-key shell command."""
        if key in {"\x03", "q", "Q"}:
            self._should_exit = True
            return
        if key in {" ", "p", "P"}:
            if self.session.paused:
                self.session.resume()
            else:
                self.session.pause(reason="Paused by user.")
            return
        if key in {"n", "N"}:
            self.session.pause(reason="Advanced one tick.")
            self.session.step()
            return
        if key in {"+", "]"}:
            self.session.increase_speed()
            return
        if key in {"-", "["}:
            self.session.decrease_speed()
            return
        if key in {"t", "T"}:
            self.session.cycle_tick_size()
            return
        if key in {"f", "F"}:
            self.show_systems = not self.show_systems
            return
        if key in {"h", "H"}:
            self.show_help = not self.show_help
            return
        if key in {"i", "I"}:
            self.session.pause(reason="Paused for inspection.")
            with self._suspended_live(live=live, key_reader=key_reader):
                prompt_for_focus_selection(self.session)
            return
        if key in {"a", "A"}:
            if not collect_mission_alert_items(self.session):
                return
            self.session.pause(reason="Paused for mission alerts.")
            with self._suspended_live(live=live, key_reader=key_reader):
                prompt_mission_alert_browser(self.session)
            return
        if key in {"s", "S"}:
            self.session.pause(reason="Paused for settings.")
            with self._suspended_live(live=live, key_reader=key_reader):
                run_settings_editor()
                maybe_prompt_save()
            return

    @contextmanager
    def _suspended_live(
        self, live: Live, key_reader: _TerminalKeyReader
    ) -> Iterator[None]:
        """Temporarily stop live rendering so prompt-based input can run cleanly."""
        live.stop()
        key_reader.disable()
        try:
            yield
        finally:
            key_reader.enable()
            live.start()


class _TerminalKeyReader:
    """Read single-key input without blocking the simulation loop."""

    def __init__(self) -> None:
        """Initialize raw terminal bookkeeping."""
        self._enabled = False
        self._original_settings = None
        self._fd: int | None = None

    def __enter__(self) -> _TerminalKeyReader:
        """Enable raw key reads if the terminal supports it."""
        self.enable()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Restore terminal settings on exit."""
        self.disable()

    def enable(self) -> None:
        """Switch stdin into cbreak mode when possible."""
        if self._enabled or termios is None or tty is None or not sys.stdin.isatty():
            return
        self._fd = sys.stdin.fileno()
        self._original_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._enabled = True

    def disable(self) -> None:
        """Restore stdin settings after raw reads."""
        if (
            not self._enabled
            or self._fd is None
            or self._original_settings is None
            or termios is None
        ):
            return
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_settings)
        self._enabled = False

    def poll(self, timeout: float) -> str | None:
        """Poll for a single key press within the provided timeout."""
        if not self._enabled or self._fd is None:
            time.sleep(timeout)
            return None

        try:
            ready, _, _ = select.select([sys.stdin], [], [], timeout)
        except KeyboardInterrupt:
            return "\x03"
        if not ready:
            return None
        key = sys.stdin.read(1)
        if key == "\x1b":
            return None
        return key
