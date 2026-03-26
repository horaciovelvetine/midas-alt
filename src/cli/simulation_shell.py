"""Interactive Rich-based shell for time-stepped simulation sessions."""

from __future__ import annotations

import select
import sys
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from src.cli.utils import DisplayHelper, InputHelper
from src.models import Facility, System
from src.simulation.runtime import EntityRuntimeState, SimulationSession

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - used only on non-POSIX systems
    termios = None
    tty = None

console = Console()


class SimulationShell:
    """Run an interactive dashboard over a single simulation session."""

    def __init__(self, session: SimulationSession, shell_console: Console | None = None) -> None:
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
                        timeout = self.session.playback_delay_seconds if not self.session.paused else 0.1
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

    def render_dashboard(self):
        """Build the full live dashboard renderable."""
        top_row = Table.grid(expand=True)
        top_row.add_column(ratio=2)
        top_row.add_column(ratio=1)
        top_row.add_row(
            build_session_summary_panel(self.session),
            build_work_order_summary_panel(self.session),
        )

        body_row = Table.grid(expand=True)
        body_row.add_column(ratio=2)
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
        )

        renderables = [top_row, body_row]
        if self.show_help:
            renderables.append(build_controls_panel())
        return Group(*renderables)

    def _handle_keypress(self, key: str, live: Live, key_reader: _TerminalKeyReader) -> None:
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

    @contextmanager
    def _suspended_live(self, live: Live, key_reader: _TerminalKeyReader) -> Iterator[None]:
        """Temporarily stop live rendering so prompt-based input can run cleanly."""
        live.stop()
        key_reader.disable()
        try:
            yield
        finally:
            key_reader.enable()
            live.start()


def build_session_summary_panel(session: SimulationSession) -> Panel:
    """Create the top-left session summary panel."""
    installation_state = session.get_installation_state()
    condition_summary = session.condition_summary()

    summary = Table.grid(expand=True)
    summary.add_column(style="cyan", ratio=1)
    summary.add_column(style="green", ratio=1)
    summary.add_column(style="cyan", ratio=1)
    summary.add_column(style="green", ratio=1)

    summary.add_row("Date", session.current_date.isoformat(), "Run State", "Paused" if session.paused else "Running")
    summary.add_row("Tick Size", session.clock.tick_size.label, "Playback", session.playback_label)
    summary.add_row("Tick Count", str(session.clock.tick_index), "Installation CI", _format_ci(installation_state.condition_index))
    summary.add_row(
        "Degraded",
        str(condition_summary["degraded"]),
        "Inoperable",
        str(condition_summary["inoperable"]),
    )
    summary.add_row(
        "Mission Blocked",
        str(condition_summary["mission_blocked"]),
        "Install Status",
        installation_state.status_label,
    )
    if session.stop_reason:
        summary.add_row("Pause Reason", session.stop_reason, "", "")

    title = session.installation.title or session.installation.id
    return Panel(summary, title=f"Simulation Overview: {title}", border_style="green")


def build_work_order_summary_panel(session: SimulationSession) -> Panel:
    """Create the top-right work-order breakdown panel."""
    counts = session.work_order_status_counts()
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Status", style="cyan")
    table.add_column("Count", style="green", justify="right")
    for status_label, count in counts.items():
        if count == 0 and status_label == "Unknown":
            continue
        table.add_row(status_label, str(count))
    return Panel(table, title="Work Orders", border_style="magenta")


def build_inspect_panel(session: SimulationSession) -> Panel:
    """Create the right-hand inspect panel."""
    if session.selected_system_id:
        system = session.systems_by_id[session.selected_system_id]
        return Panel(build_system_details(session, system), title="Inspecting System", border_style="yellow")
    if session.selected_facility_id:
        facility = session.facilities_by_id[session.selected_facility_id]
        return Panel(build_facility_details(session, facility), title="Inspecting Facility", border_style="yellow")
    return Panel(build_installation_details(session), title="Inspecting Installation", border_style="yellow")


def build_installation_details(session: SimulationSession):
    """Create the default installation inspection view."""
    installation = session.installation
    state = session.get_installation_state()
    detail = Table.grid(padding=(0, 1))
    detail.add_column(style="cyan")
    detail.add_column(style="green")
    detail.add_row("Title", installation.title or installation.id)
    detail.add_row("Location", installation.location or "N/A")
    detail.add_row("Region", installation.region or "N/A")
    detail.add_row("Facilities", str(len(session.facilities)))
    detail.add_row("Systems", str(len(session.systems)))
    detail.add_row("Condition Index", _format_ci(state.condition_index))
    detail.add_row("Status", state.status_label)
    detail.add_row("Focused", "None")
    detail.add_row("How To Inspect", "Press i to choose a facility or system")
    return detail


def build_facility_details(session: SimulationSession, facility: Facility):
    """Create the inspection view for a focused facility."""
    state = session.get_facility_state(facility.id)
    facility_type = session.settings.get_facility_type(facility.facility_type_key or 0)
    systems = session.systems_by_facility.get(facility.id, [])

    detail = Table.grid(padding=(0, 1))
    detail.add_column(style="cyan")
    detail.add_column(style="green")
    detail.add_row("Title", facility_type.title if facility_type else facility.id)
    detail.add_row("Dependency", str(facility.dependency_position))
    detail.add_row("Resiliency", facility.resiliency_grade.value if facility.resiliency_grade else "N/A")
    detail.add_row("Age", f"{facility.age_years} years" if facility.age_years is not None else "N/A")
    detail.add_row("Condition Index", _format_ci(state.condition_index))
    detail.add_row("Status", state.status_label)
    detail.add_row("Systems", str(len(systems)))
    detail.add_row("Open Work Orders", str(state.open_work_orders))
    detail.add_row("Mission Work Orders", str(state.mission_impacting_open_work_orders))
    detail.add_row("Degraded Children", str(state.child_degraded_count))
    detail.add_row("Inoperable Children", str(state.child_inoperable_count))
    detail.add_row("Change Focus", "Press i to inspect another facility or system")
    return detail


def build_system_details(session: SimulationSession, system: System):
    """Create the inspection view for a focused system."""
    state = session.get_system_state(system.id)
    system_type = session.settings.get_system_type(system.system_type_key or 0)

    detail = Table.grid(padding=(0, 1))
    detail.add_column(style="cyan")
    detail.add_column(style="green")
    detail.add_row("Title", system_type.title if system_type else system.id)
    detail.add_row("Age", f"{system.age_years} years" if system.age_years is not None else "N/A")
    detail.add_row("Condition Index", _format_ci(state.condition_index))
    detail.add_row("Status", state.status_label)
    detail.add_row("Open Work Orders", str(state.open_work_orders))
    detail.add_row("Mission Work Orders", str(state.mission_impacting_open_work_orders))

    if system.work_orders:
        detail.add_row("Work Order Statuses", ", ".join(_work_order_status_labels(system)))
    else:
        detail.add_row("Work Order Statuses", "None")
    detail.add_row("Change Focus", "Press i to inspect another facility or system")
    return detail


def build_controls_panel() -> Panel:
    """Render available key controls for the live shell."""
    instructions = Text(
        "Use these keys while the simulation is open. Press h at any time to hide or show this help.",
        style="dim",
    )

    table = Table(expand=True, show_header=True, header_style="bold cyan")
    table.add_column("Keys", style="bold yellow", width=14)
    table.add_column("Action", style="cyan", width=22)
    table.add_column("Instruction", style="green")

    table.add_row("space / p", "Pause or resume", "Toggle the simulation clock on or off.")
    table.add_row("n", "Single-step", "Advance exactly one tick and then pause again.")
    table.add_row("t", "Change tick size", "Cycle through day, week, month, and year ticks.")
    table.add_row("+ or ]", "Speed up", "Reduce the delay between ticks so time passes faster.")
    table.add_row("- or [", "Slow down", "Increase the delay between ticks so you can inspect changes.")
    table.add_row("i", "Inspect / focus", "Open a prompt to focus a facility or system, or clear focus.")
    table.add_row("f", "Toggle systems", "Show or hide systems under facilities in the installation graph.")
    table.add_row("h", "Hide / show help", "Toggle this controls panel.")
    table.add_row("q / Ctrl-C", "Quit simulation", "Exit the live simulation and return to the menu.")

    tips = Text(
        "Tip: focused facilities and systems are highlighted, and focused facilities automatically show their systems.",
        style="dim",
    )
    return Panel(Group(instructions, table, tips), title="Controls", border_style="blue")


def build_dependency_tree(session: SimulationSession, show_systems: bool) -> Tree:
    """Create a tree-like dependency view for facilities and optional systems."""
    installation_state = session.get_installation_state()
    title = session.installation.title or session.installation.id
    root_label = (
        f"[bold cyan]{title}[/bold cyan] "
        f"(CI { _format_ci(installation_state.condition_index) }, {installation_state.status_label})"
    )
    root = Tree(root_label)
    parent_map = build_dependency_parent_map(session.facilities)
    children_by_parent: dict[str | None, list[Facility]] = defaultdict(list)
    for facility in session.facilities:
        children_by_parent[parent_map.get(facility.id)].append(facility)

    def add_children(parent_node: Tree, parent_id: str | None) -> None:
        for facility in sorted(children_by_parent.get(parent_id, []), key=_facility_sort_key):
            facility_state = session.get_facility_state(facility.id)
            facility_node = parent_node.add(
                _format_facility_label(
                    session=session,
                    facility=facility,
                    runtime_state=facility_state,
                    selected=session.selected_facility_id == facility.id,
                )
            )
            should_show_systems = show_systems or session.selected_facility_id == facility.id
            if should_show_systems:
                for system in session.systems_by_facility.get(facility.id, []):
                    facility_node.add(
                        _format_system_label(
                            session=session,
                            system=system,
                            runtime_state=session.get_system_state(system.id),
                            selected=session.selected_system_id == system.id,
                        )
                    )
            add_children(facility_node, facility.id)

    add_children(root, None)
    return root


def build_dependency_parent_map(facilities: list[Facility]) -> dict[str, str | None]:
    """Choose one display parent for each facility based on dependency rules."""
    parent_map: dict[str, str | None] = {}
    sorted_facilities = sorted(facilities, key=_facility_sort_key)

    for facility in sorted_facilities:
        parent_id: str | None = None
        best_score: tuple[int, int, str] | None = None
        for candidate in sorted_facilities:
            if candidate.id == facility.id:
                continue
            if not candidate.dependency_position.is_above(facility.dependency_position):
                continue
            if not candidate.dependency_position.has_shared_group(facility.dependency_position):
                continue

            shared_groups = len(set(candidate.dependency_position.group_ids) & set(facility.dependency_position.group_ids))
            candidate_score = (candidate.dependency_position.depth, shared_groups, candidate.id)
            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                parent_id = candidate.id
        parent_map[facility.id] = parent_id

    return parent_map


def prompt_for_focus_selection(session: SimulationSession) -> None:
    """Prompt the user to focus a facility, system, or clear the current selection."""
    mode = InputHelper.ask_choice(
        "Inspect [facility/system/clear/cancel]",
        choices=["facility", "system", "clear", "cancel"],
        default="cancel",
    )
    if mode in {None, "cancel"}:
        return
    if mode == "clear":
        session.clear_selection()
        return
    if mode == "facility":
        _prompt_for_facility_selection(session)
        return
    _prompt_for_system_selection(session)


def _prompt_for_facility_selection(session: SimulationSession) -> None:
    """Prompt the user to select a facility by number."""
    if not session.facilities:
        DisplayHelper.print_warning("No facilities are available to inspect.")
        InputHelper.wait_for_continue()
        return

    table = Table(title="Facilities", show_header=True, header_style="bold cyan")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Facility", style="green")
    table.add_column("Dependency", style="yellow")
    table.add_column("CI", style="magenta", justify="right")
    for index, facility in enumerate(sorted(session.facilities, key=_facility_sort_key), start=1):
        facility_type = session.settings.get_facility_type(facility.facility_type_key or 0)
        table.add_row(
            str(index),
            facility_type.title if facility_type else facility.id,
            str(facility.dependency_position),
            _format_ci(facility.condition_index),
        )
    DisplayHelper.print_table(table)

    selection = InputHelper.ask_number(
        f"Select facility 1-{len(session.facilities)}",
        min_value=1,
        max_value=len(session.facilities),
    )
    if selection is None:
        return
    selected_facility = sorted(session.facilities, key=_facility_sort_key)[selection - 1]
    session.set_selected_facility(selected_facility.id)


def _prompt_for_system_selection(session: SimulationSession) -> None:
    """Prompt the user to select a system by number."""
    if not session.systems:
        DisplayHelper.print_warning("No systems are available to inspect.")
        InputHelper.wait_for_continue()
        return

    table = Table(title="Systems", show_header=True, header_style="bold cyan")
    table.add_column("#", style="cyan", width=4)
    table.add_column("System", style="green")
    table.add_column("Facility", style="yellow")
    table.add_column("CI", style="magenta", justify="right")
    sorted_systems = sorted(session.systems, key=lambda system: (_facility_sort_group(session, system), system.id))
    for index, system in enumerate(sorted_systems, start=1):
        system_type = session.settings.get_system_type(system.system_type_key or 0)
        facility = session.facilities_by_id.get(system.facility_id or "")
        facility_type = session.settings.get_facility_type(facility.facility_type_key or 0) if facility else None
        table.add_row(
            str(index),
            system_type.title if system_type else system.id,
            facility_type.title if facility_type else (facility.id if facility else "N/A"),
            _format_ci(system.condition_index),
        )
    DisplayHelper.print_table(table)

    selection = InputHelper.ask_number(
        f"Select system 1-{len(sorted_systems)}",
        min_value=1,
        max_value=len(sorted_systems),
    )
    if selection is None:
        return
    session.set_selected_system(sorted_systems[selection - 1].id)


def _format_facility_label(
    session: SimulationSession,
    facility: Facility,
    runtime_state: EntityRuntimeState,
    selected: bool,
) -> str:
    """Format a facility label for the dependency tree."""
    facility_type = session.settings.get_facility_type(facility.facility_type_key or 0)
    title = facility_type.title if facility_type else facility.id
    label = (
        f"{title} [{facility.dependency_position}] "
        f"(CI {_format_ci(runtime_state.condition_index)}, {runtime_state.status_label})"
    )
    if selected:
        return f"[bold yellow]{label}[/bold yellow]"
    return label


def _format_system_label(
    session: SimulationSession,
    system: System,
    runtime_state: EntityRuntimeState,
    selected: bool,
) -> str:
    """Format a system label for the dependency tree."""
    system_type = session.settings.get_system_type(system.system_type_key or 0)
    title = system_type.title if system_type else system.id
    label = f"{title} (CI {_format_ci(runtime_state.condition_index)}, {runtime_state.status_label})"
    if selected:
        return f"[bold yellow]{label}[/bold yellow]"
    return label


def _facility_sort_key(facility: Facility) -> tuple[int, str, list[int], str]:
    """Return a stable ordering for facility display."""
    return (
        facility.dependency_position.depth,
        facility.dependency_position.vertical_position,
        facility.dependency_position.group_ids,
        facility.id,
    )


def _facility_sort_group(session: SimulationSession, system: System) -> tuple[int, str, str]:
    """Return a stable ordering for system display grouped by facility."""
    facility = session.facilities_by_id.get(system.facility_id or "")
    if facility is None:
        return (999, "Z", system.id)
    return (
        facility.dependency_position.depth,
        facility.dependency_position.vertical_position,
        system.id,
    )


def _format_ci(value: float | None) -> str:
    """Format a condition-index value for display."""
    return f"{value:.2f}" if value is not None else "N/A"


def _work_order_status_labels(system: System) -> list[str]:
    """Return work-order statuses for a system as simple labels."""
    return [work_order.status.value if work_order.status else "Unknown" for work_order in system.work_orders]


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
        if not self._enabled or self._fd is None or self._original_settings is None or termios is None:
            return
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_settings)
        self._enabled = False

    def poll(self, timeout: float) -> str | None:
        """Poll for a single key press within the provided timeout."""
        if not self._enabled or self._fd is None:
            time.sleep(timeout)
            return None

        ready, _, _ = select.select([sys.stdin], [], [], timeout)
        if not ready:
            return None
        key = sys.stdin.read(1)
        if key == "\x1b":
            return None
        return key
