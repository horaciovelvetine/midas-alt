"""Rich renderables and prompt flows for the simulation shell dashboard."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from src.cli.utils import DisplayHelper, InputHelper
from src.config import MidasSettings
from src.enums.entity_type import EntityType
from src.enums.work_order import WO_Status
from src.models import Facility, System, WorkOrder
from src.simulation.runtime import EntityRuntimeState, SimulationSession

INSTALL_MISSION_WO_ALERT_THRESHOLD = 5
SYSTEM_MISSION_WO_ALERT_THRESHOLD = 2

console = Console()

_MISSION_ALERT_OPEN_STATUSES = frozenset(
    {WO_Status.SUBMITTED, WO_Status.APPROVED, WO_Status.IN_PROGRESS}
)


@dataclass(frozen=True)
class MissionAlertItem:
    """One actionable mission alert for summary, drill-down, and work-order samples."""

    kind: str
    summary: str
    detail: str
    severity: str = "warning"
    why_brief: str = ""
    reason_lines: tuple[str, ...] = ()
    entity_type: EntityType | None = None
    entity_id: str | None = None


def build_installation_summary_panel(session: SimulationSession) -> Panel:
    """Create the top-row panel for static installation identity and health summary."""
    installation = session.installation
    installation_state = session.get_installation_state()
    condition_summary = session.condition_summary()

    grid = Table.grid(expand=True)
    grid.add_column(style="cyan")
    grid.add_column(style="green")

    grid.add_row("Title", installation.title or installation.id)
    grid.add_row("Location", installation.location or "N/A")
    grid.add_row("Region", installation.region or "N/A")
    grid.add_row("Facilities", str(len(session.facilities)))
    grid.add_row("Systems", str(len(session.systems)))
    grid.add_row(
        "Condition Index",
        _format_ci_and_status(
            installation_state.condition_index, installation_state.status_label
        ),
    )
    grid.add_row("Degraded entities", str(condition_summary["degraded"]))
    grid.add_row("Inoperable entities", str(condition_summary["inoperable"]))
    grid.add_row("Mission blocked entities", str(condition_summary["mission_blocked"]))

    return Panel(grid, title="Installation Details", border_style="green")


def build_settings_snapshot_panel(session: SimulationSession | None = None) -> Panel:
    """Render a compact snapshot of simulation-relevant settings beside the inspect panel.

    Shows the scalar tunables that most influence ongoing simulation behavior
    (degradation thresholds, random degradation chance and CI drop, generation
    defaults, and age maxima) and tags an "[unsaved]" marker when
    ``MidasSettings`` has edits that have not yet been persisted.
    """
    del session
    settings = MidasSettings()

    grid = Table.grid(expand=True)
    grid.add_column(style="cyan")
    grid.add_column(style="green", justify="right")

    snapshot_keys = (
        ("Degraded Threshold (CI)", "condition_index_degraded_threshold"),
        ("Initial CI Default", "initial_condition_index_default"),
        ("Random System Degrade %/yr", "random_system_degradation_chance"),
        ("Random System Degrade CI Drop", "random_system_degradation_ci_drop"),
        ("Max Facility Age", "maximum_facility_age"),
        ("Max System Age", "maximum_system_age"),
    )
    for label, name in snapshot_keys:
        try:
            value = settings.get_value(name)
        except KeyError:
            continue
        grid.add_row(label, _format_setting_value_for_panel(value))

    title = "Settings Snapshot"
    if settings.is_dirty():
        title += " [unsaved]"
    border_style = "red" if settings.is_dirty() else "blue"
    hint = Text("Press 's' to edit settings.", style="dim")
    return Panel(Group(grid, hint), title=title, border_style=border_style)


def _format_setting_value_for_panel(value: object) -> str:
    """Compact, single-cell-friendly stringifier for the snapshot panel."""
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, tuple) and len(value) == 2:
        return f"{value[0]}-{value[1]}"
    return str(value)


def build_simulation_overview_panel(session: SimulationSession) -> Panel:
    """Create the top-row panel for clock, playback, and pause state."""
    grid = Table.grid(expand=True)
    grid.add_column(style="cyan")
    grid.add_column(style="green")

    grid.add_row("Date", session.current_date.isoformat())
    grid.add_row("Tick Size", session.clock.tick_size.label)
    grid.add_row("Tick Count", str(session.clock.tick_index))
    grid.add_row("Run State", "Paused" if session.paused else "Running")
    grid.add_row("Playback", session.playback_label)
    if session.stop_reason:
        grid.add_row("Pause Reason", session.stop_reason)

    return Panel(grid, title="Simulation Overview", border_style="green")


def build_mission_alert_panel(session: SimulationSession) -> Panel | None:
    """Full-width strip: narrative summary, category counts, thresholds, and drill-down hint (key a)."""
    items = collect_mission_alert_items(session)
    if not items:
        return None
    summary = Text()
    summary.append(_mission_alert_summary_phrase(items), style="red")
    summary.append("\n")
    hint = Text()
    hint.append(
        f"Thresholds: install-wide mission open WOs ≥{INSTALL_MISSION_WO_ALERT_THRESHOLD}; "
        f"system-level mission open WOs ≥{SYSTEM_MISSION_WO_ALERT_THRESHOLD}. ",
        style="dim",
    )
    hint.append("Press ", style="dim")
    hint.append("a", style="bold dim")
    hint.append(
        " for rules, counts, and per-alert drill-down (metrics + why + sample WOs).",
        style="dim",
    )
    return Panel(
        Group(summary, _build_mission_alert_strip_counts_table(items), hint),
        title="Mission alerts",
        border_style="red",
    )


def _format_ci_and_status(condition_index: float | None, status_label: str) -> str:
    """Single-line condition index plus operational status."""
    return f"{_format_ci(condition_index)} — {status_label}"


def _facility_title(session: SimulationSession, facility: Facility) -> str:
    """Human-readable facility label from reference data."""
    facility_type = session.settings.config_data.get_facility_type(
        facility.facility_type_key or 0
    )
    return facility_type.title if facility_type else facility.id


def _system_title(session: SimulationSession, system: System) -> str:
    """Human-readable system label from reference data."""
    system_type = session.settings.config_data.get_system_type(
        system.system_type_key or 0
    )
    return system_type.title if system_type else system.id


def _open_mission_impacting_work_orders(
    session: SimulationSession,
    entity_type: EntityType,
    entity_id: str,
) -> list[WorkOrder]:
    """Open work orders for an entity that count as mission-impacting (matches session rollup logic)."""
    system_ids_under_facility: set[str] | None = None
    if entity_type == EntityType.FACILITY:
        system_ids_under_facility = {
            s.id for s in session.systems_by_facility.get(entity_id, [])
        }
    selected: list[WorkOrder] = []
    for wo in session.work_orders:
        if wo.status not in _MISSION_ALERT_OPEN_STATUSES:
            continue
        if not wo.impacts_mission:
            continue
        if entity_type == EntityType.SYSTEM and wo.system_id == entity_id:
            selected.append(wo)
        elif entity_type == EntityType.FACILITY:
            if wo.facility_id == entity_id or (
                wo.system_id and wo.system_id in system_ids_under_facility
            ):
                selected.append(wo)
        elif entity_type == EntityType.INSTALLATION and wo.installation_id == entity_id:
            selected.append(wo)
    return selected


def _mission_blocked_why_brief(state: EntityRuntimeState) -> str:
    """One-line trigger for the mission-alerts table."""
    if state.entity_type == EntityType.SYSTEM:
        return f"Inoperable (CI≤0) with {state.mission_impacting_open_work_orders} mission open WO(s)"
    if state.entity_type == EntityType.FACILITY:
        return f"Facility rollup blocked; {state.mission_impacting_open_work_orders} mission open WO(s)"
    return f"Installation rollup blocked; {state.mission_impacting_open_work_orders} mission open WO(s)"


def _mission_blocked_reason_lines(
    session: SimulationSession, state: EntityRuntimeState
) -> tuple[str, ...]:
    """Explain mission_blocked from session rules (inoperable + mission WOs, with child rollup)."""
    if state.entity_type == EntityType.SYSTEM:
        return (
            "Condition index is at or below zero, so the system is inoperable in this model.",
            "At least one work order is still open (Submitted, Approved, or In Progress) with impacts_mission=True.",
            "Rule at system level: mission blocked = inoperable AND open mission-impacting work orders.",
        )
    if state.entity_type == EntityType.FACILITY:
        facility = session.facilities_by_id[state.entity_id]
        child_states = [
            session.get_system_state(s.id)
            for s in session.systems_by_facility.get(facility.id, [])
        ]
        n_child_mb = sum(1 for cs in child_states if cs.mission_blocked)
        lines: list[str] = []
        if n_child_mb:
            lines.append(
                f"{n_child_mb} child system(s) are already mission blocked; the facility inherits that condition upward."
            )
        inop_fac = state.condition_index is not None and state.condition_index <= 0
        if inop_fac and state.mission_impacting_open_work_orders:
            lines.append(
                "Facility aggregate CI is inoperable (≤0) while mission-impacting work orders remain open under this facility."
            )
        if not lines:
            lines.append(
                "Facility mission blocked is driven by rollup from systems and/or facility-level inoperability."
            )
        lines.append(
            "Rule: mission blocked if any child system is mission blocked, OR (facility inoperable AND mission open WOs)."
        )
        return tuple(lines)
    facility_states = [session.get_facility_state(f.id) for f in session.facilities]
    n_fac_mb = sum(1 for fs in facility_states if fs.mission_blocked)
    lines2: list[str] = []
    if n_fac_mb:
        lines2.append(
            f"{n_fac_mb} facility rollup(s) show mission blocked; the installation reflects that cumulative posture."
        )
    inop_inst = state.condition_index is not None and state.condition_index <= 0
    if inop_inst and state.mission_impacting_open_work_orders:
        lines2.append(
            "Installation aggregate CI is inoperable (≤0) with open mission-impacting work orders under this installation."
        )
    if not lines2:
        lines2.append(
            "Installation mission blocked aggregates facility and system runtime states."
        )
    lines2.append(
        "Rule: mission blocked if any facility is mission blocked, OR (installation inoperable AND mission open WOs)."
    )
    return tuple(lines2)


def _build_mission_alert_strip_counts_table(items: list[MissionAlertItem]) -> Table:
    """Compact category counts for the live dashboard strip."""
    mb = sum(1 for item in items if item.kind == "mission_blocked")
    inst = sum(1 for item in items if item.kind == "install_high_wo")
    sys_n = sum(1 for item in items if item.kind == "system_high_wo")
    grid = Table(show_header=True, header_style="bold red", box=None, padding=(0, 1))
    grid.add_column("Alert type", style="yellow", min_width=26)
    grid.add_column("Count", justify="right", style="cyan", width=6)
    grid.add_column("", style="dim", width=14)
    grid.add_row("Mission blocked (entities)", str(mb), "critical" if mb else "")
    grid.add_row("Install WO load warning", str(inst), "warning" if inst else "")
    grid.add_row("System WO load warnings", str(sys_n), "warning" if sys_n else "")
    return grid


def _build_mission_alert_rules_panel() -> Panel:
    """Static explanation of alert kinds and thresholds (browser landing view)."""
    body = Text()
    body.append("Critical — Mission blocked\n", style="bold red")
    body.append(
        "Rollup marks an entity mission blocked when it is inoperable (condition index ≤ 0 at that level) and open "
        "work orders with impacts_mission remain in Submitted / Approved / In Progress. Facilities and installations "
        "also show blocked when a child entity is already mission blocked.\n\n",
        style="dim",
    )
    body.append(
        "Warning — High mission-impacting work order load\n", style="bold yellow"
    )
    body.append(
        f"Installation-wide: total open mission-impacting WOs ≥ {INSTALL_MISSION_WO_ALERT_THRESHOLD} while the "
        "installation is not mission blocked (early visibility).\n",
        style="dim",
    )
    body.append(
        f"Per system: open mission-impacting WOs ≥ {SYSTEM_MISSION_WO_ALERT_THRESHOLD} while the system is still "
        "operable (CI > 0); if CI hits zero with those WOs open, this becomes mission blocked instead.\n",
        style="dim",
    )
    return Panel(body, title="How mission alerts work", border_style="blue")


def _build_mission_alert_browser_snapshot_panel(items: list[MissionAlertItem]) -> Panel:
    """Aggregate counts for the current tick inside the browser."""
    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="cyan", justify="right")
    grid.add_column(style="green")
    mb = sum(1 for item in items if item.kind == "mission_blocked")
    inst = sum(1 for item in items if item.kind == "install_high_wo")
    sys_n = sum(1 for item in items if item.kind == "system_high_wo")
    grid.add_row("Mission blocked (rows)", str(mb))
    grid.add_row("Installation WO warning(s)", str(inst))
    grid.add_row("System WO warning(s)", str(sys_n))
    grid.add_row("Total drill-down rows", str(len(items)))
    return Panel(grid, title="This tick — counts", border_style="cyan")


def _build_mission_alert_browser_table(items: list[MissionAlertItem]) -> Table:
    """Selectable list with severity, category, and a short 'why' column."""
    table = Table(title="All alerts", show_header=True, header_style="bold red")
    table.add_column("#", style="cyan", width=3, justify="right")
    table.add_column("Severity", width=8)
    table.add_column("Category", style="yellow", width=14)
    table.add_column("What", style="green", width=32, no_wrap=True, overflow="ellipsis")
    table.add_column(
        "Why flagged", style="dim", width=34, no_wrap=True, overflow="ellipsis"
    )
    kind_labels = {
        "mission_blocked": "Blocked",
        "install_high_wo": "Inst. WO load",
        "system_high_wo": "System WO load",
    }
    for index, item in enumerate(items, start=1):
        if item.severity == "critical":
            sev_cell = Text("critical", style="bold red")
        else:
            sev_cell = Text("warning", style="yellow")
        table.add_row(
            str(index),
            sev_cell,
            kind_labels.get(item.kind, item.kind),
            item.summary,
            item.why_brief or "—",
        )
    return table


def _mission_alert_work_order_sample_table(
    wos: list[WorkOrder], *, max_rows: int
) -> Panel:
    """Table of sample open mission-impacting work orders for drill-down."""
    if not wos:
        return Panel(
            "[dim]No rows matched the session work-order list for this entity (counts above still reflect runtime).[/dim]",
            title="Open mission-impacting work orders",
            border_style="dim",
        )
    tbl = Table(show_header=True, header_style="bold magenta")
    tbl.add_column("WO", style="cyan", max_width=16, overflow="ellipsis")
    tbl.add_column("Status", style="green", max_width=12)
    tbl.add_column("Priority", style="yellow", max_width=12)
    tbl.add_column("Trade", style="dim", max_width=14)
    for wo in wos[:max_rows]:
        short = (wo.id[:10] + "…") if len(wo.id) > 10 else wo.id
        tbl.add_row(
            short,
            wo.status.value if wo.status else "—",
            wo.priority.value if wo.priority else "—",
            wo.trade.value if wo.trade else "—",
        )
    if len(wos) > max_rows:
        note = Text(f"… and {len(wos) - max_rows} more not shown.", style="dim")
        return Panel(
            Group(tbl, note),
            title=f"Open mission-impacting WOs (first {max_rows})",
            border_style="magenta",
        )
    return Panel(
        tbl, title="Open mission-impacting work orders", border_style="magenta"
    )


def _print_mission_alert_drilldown(
    session: SimulationSession,
    item: MissionAlertItem,
    index: int,
    total: int,
) -> None:
    """Print structured detail: metrics, rule bullets, summary line, sample work orders."""
    metrics = Table(show_header=False, box=None, padding=(0, 1))
    metrics.add_column("Field", style="cyan")
    metrics.add_column("Value", style="green")
    filled_metrics = False
    if item.entity_type and item.entity_id:
        st: EntityRuntimeState | None = None
        if item.entity_type == EntityType.SYSTEM:
            st = session.get_system_state(item.entity_id)
        elif item.entity_type == EntityType.FACILITY:
            st = session.get_facility_state(item.entity_id)
        elif item.entity_type == EntityType.INSTALLATION:
            st = session.get_installation_state()
        if st:
            metrics.add_row("Runtime status", st.status_label)
            metrics.add_row("Condition index", _format_ci(st.condition_index))
            metrics.add_row("Open work orders", str(st.open_work_orders))
            metrics.add_row(
                "Mission-impacting (open)", str(st.mission_impacting_open_work_orders)
            )
            filled_metrics = True

    reasons = Text()
    reasons.append("Why this alert\n", style="bold white")
    for line in item.reason_lines:
        reasons.append(f"• {line}\n", style="dim")

    narrative = Panel(
        Text(item.detail, style="red"), title="One-line summary", border_style="red"
    )
    wos = (
        _open_mission_impacting_work_orders(session, item.entity_type, item.entity_id)
        if item.entity_type and item.entity_id
        else []
    )
    wo_panel = _mission_alert_work_order_sample_table(wos, max_rows=12)

    body = Group(
        (
            metrics
            if filled_metrics
            else Text("[dim]No entity metrics for this alert kind.[/dim]", style="dim")
        ),
        reasons,
        narrative,
        wo_panel,
    )
    console.print(
        Panel(
            body,
            title=f"Alert {index} of {total} — {item.summary}",
            border_style="yellow",
        )
    )


def _format_mission_blocked_alert(
    session: SimulationSession, state: EntityRuntimeState
) -> str:
    """One alert line for a mission-blocked entity."""
    if state.entity_type == EntityType.INSTALLATION:
        name = session.installation.title or session.installation.id
        return (
            f"MISSION BLOCKED: {name} (installation) — CI {_format_ci(state.condition_index)} — "
            f"{state.mission_impacting_open_work_orders} open mission-impacting work order(s)."
        )
    if state.entity_type == EntityType.FACILITY:
        facility = session.facilities_by_id[state.entity_id]
        name = _facility_title(session, facility)
        return (
            f"MISSION BLOCKED: {name} (facility) — CI {_format_ci(state.condition_index)} — "
            f"{state.mission_impacting_open_work_orders} open mission-impacting work order(s) under this facility."
        )
    system = session.systems_by_id[state.entity_id]
    name = _system_title(session, system)
    facility = session.facilities_by_id.get(system.facility_id or "")
    fac_name = _facility_title(session, facility) if facility else "Unassigned"
    return (
        f"MISSION BLOCKED: {name} (system) at facility {fac_name} — CI {_format_ci(state.condition_index)} — "
        f"{state.mission_impacting_open_work_orders} open mission-impacting work order(s)."
    )


def _mission_blocked_summary_line(
    session: SimulationSession, state: EntityRuntimeState
) -> str:
    """Short menu label for a mission-blocked entity."""
    if state.entity_type == EntityType.INSTALLATION:
        name = session.installation.title or session.installation.id
        return f"Installation — {name}"
    if state.entity_type == EntityType.FACILITY:
        facility = session.facilities_by_id[state.entity_id]
        return f"Facility — {_facility_title(session, facility)}"
    system = session.systems_by_id[state.entity_id]
    facility = session.facilities_by_id.get(system.facility_id or "")
    fac_name = _facility_title(session, facility) if facility else "Unassigned"
    return f"System — {_system_title(session, system)} ({fac_name})"


def collect_mission_alert_items(session: SimulationSession) -> list[MissionAlertItem]:
    """Build ordered mission alerts with summaries, drill-down fields, and entity linkage for WO samples."""
    items: list[MissionAlertItem] = []
    mission_blocked_keys: set[tuple[EntityType, str]] = set()

    for state in session.iter_runtime_states():
        if not state.mission_blocked:
            continue
        mission_blocked_keys.add((state.entity_type, state.entity_id))
        items.append(
            MissionAlertItem(
                kind="mission_blocked",
                summary=_mission_blocked_summary_line(session, state),
                detail=_format_mission_blocked_alert(session, state),
                severity="critical",
                why_brief=_mission_blocked_why_brief(state),
                reason_lines=_mission_blocked_reason_lines(session, state),
                entity_type=state.entity_type,
                entity_id=state.entity_id,
            )
        )

    inst_state = session.get_installation_state()
    if (
        inst_state.mission_impacting_open_work_orders
        >= INSTALL_MISSION_WO_ALERT_THRESHOLD
        and not inst_state.mission_blocked
    ):
        inst_n = inst_state.mission_impacting_open_work_orders
        items.append(
            MissionAlertItem(
                kind="install_high_wo",
                summary="Installation — high mission-impacting work order load",
                detail=(
                    f"High mission impact: installation has {inst_n} "
                    f"open mission-impacting work orders (alert threshold {INSTALL_MISSION_WO_ALERT_THRESHOLD})."
                ),
                severity="warning",
                why_brief=f"{inst_n} mission open WOs (warn if ≥{INSTALL_MISSION_WO_ALERT_THRESHOLD})",
                reason_lines=(
                    "Early warning — the installation is not mission blocked under current rules.",
                    f"Open mission-impacting work orders ({inst_n}) reached the install-wide dashboard threshold "
                    f"({INSTALL_MISSION_WO_ALERT_THRESHOLD}).",
                    "Mission blocked is stricter: inoperable rollup plus open mission-impacting WOs at that level.",
                ),
                entity_type=EntityType.INSTALLATION,
                entity_id=session.installation.id,
            )
        )

    for system in session.systems:
        sstate = session.get_system_state(system.id)
        if (
            sstate.mission_impacting_open_work_orders
            < SYSTEM_MISSION_WO_ALERT_THRESHOLD
        ):
            continue
        if (EntityType.SYSTEM, system.id) in mission_blocked_keys:
            continue
        facility = session.facilities_by_id.get(system.facility_id or "")
        fac_part = _facility_title(session, facility) if facility else "Unassigned"
        sys_n = sstate.mission_impacting_open_work_orders
        items.append(
            MissionAlertItem(
                kind="system_high_wo",
                summary=f"System — {_system_title(session, system)} ({fac_part})",
                detail=(
                    f"High mission impact: system {_system_title(session, system)} — "
                    f"{sys_n} mission-impacting open work orders "
                    f"(threshold {SYSTEM_MISSION_WO_ALERT_THRESHOLD}); facility: {fac_part}."
                ),
                severity="warning",
                why_brief=f"{sys_n} mission open WOs (warn if ≥{SYSTEM_MISSION_WO_ALERT_THRESHOLD})",
                reason_lines=(
                    "Early warning — system CI is still above zero (operable) but carries several mission-impacting open WOs.",
                    f"Count ({sys_n}) meets the per-system threshold ({SYSTEM_MISSION_WO_ALERT_THRESHOLD}).",
                    "If CI falls to zero while these stay open, this escalates to mission blocked for that system.",
                ),
                entity_type=EntityType.SYSTEM,
                entity_id=system.id,
            )
        )

    return items


def _mission_alert_summary_phrase(items: list[MissionAlertItem]) -> str:
    """Single-sentence counts for the live dashboard strip."""
    mb = sum(1 for item in items if item.kind == "mission_blocked")
    inst = sum(1 for item in items if item.kind == "install_high_wo")
    sys_n = sum(1 for item in items if item.kind == "system_high_wo")
    parts: list[str] = []
    if mb:
        parts.append(f"{mb} mission-blocked entit{'y' if mb == 1 else 'ies'}")
    if inst:
        parts.append("1 installation-wide high mission-impacting work order load")
    if sys_n:
        parts.append(
            f"{sys_n} system{'s' if sys_n != 1 else ''} over the per-system mission WO threshold"
        )
    return "Active mission impact: " + "; ".join(parts) + "."


def prompt_mission_alert_browser(session: SimulationSession) -> None:
    """Rules + snapshot, then a rich table; pick # for metrics, rule text, and sample mission WOs (0 closes)."""
    while True:
        items = collect_mission_alert_items(session)
        if not items:
            DisplayHelper.print_info(
                "There are no active mission alerts.", title="Mission alerts"
            )
            InputHelper.wait_for_continue()
            return

        console.print(_build_mission_alert_rules_panel())
        console.print(_build_mission_alert_browser_snapshot_panel(items))
        DisplayHelper.print_table(_build_mission_alert_browser_table(items))

        choice = InputHelper.ask_number(
            f"Drill into alert 1-{len(items)} (metrics + why + sample WOs), or 0 to close",
            min_value=0,
            max_value=len(items),
            default=0,
        )
        if choice is None or choice == 0:
            return

        _print_mission_alert_drilldown(session, items[choice - 1], choice, len(items))
        InputHelper.wait_for_continue()


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
        return Panel(
            build_system_details(session, system),
            title="Inspecting System",
            border_style="yellow",
        )
    if session.selected_facility_id:
        facility = session.facilities_by_id[session.selected_facility_id]
        return Panel(
            build_facility_details(session, facility),
            title="Inspecting Facility",
            border_style="yellow",
        )
    return Panel(
        build_installation_details(session),
        title="Inspecting Installation",
        border_style="yellow",
    )


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
    detail.add_row(
        "Condition", _format_ci_and_status(state.condition_index, state.status_label)
    )
    detail.add_row("Focused", "None")
    detail.add_row(
        "How To Inspect",
        "Press i for the facility list; b returns to the simulation from inspect prompts",
    )
    return detail


def build_facility_details(session: SimulationSession, facility: Facility):
    """Create the inspection view for a focused facility."""
    state = session.get_facility_state(facility.id)
    facility_type = session.settings.config_data.get_facility_type(
        facility.facility_type_key or 0
    )
    systems = session.systems_by_facility.get(facility.id, [])

    detail = Table.grid(padding=(0, 1))
    detail.add_column(style="cyan")
    detail.add_column(style="green")
    detail.add_row("Title", facility_type.title if facility_type else facility.id)
    detail.add_row("Dependency", str(facility.dependency_position))
    detail.add_row(
        "Resiliency",
        facility.resiliency_grade.value if facility.resiliency_grade else "N/A",
    )
    detail.add_row(
        "Age",
        f"{facility.age_years} years" if facility.age_years is not None else "N/A",
    )
    detail.add_row(
        "Condition", _format_ci_and_status(state.condition_index, state.status_label)
    )
    detail.add_row("Systems", str(len(systems)))
    detail.add_row("Open Work Orders", str(state.open_work_orders))
    detail.add_row("Mission Work Orders", str(state.mission_impacting_open_work_orders))
    detail.add_row("Degraded Children", str(state.child_degraded_count))
    detail.add_row("Inoperable Children", str(state.child_inoperable_count))
    detail.add_row(
        "Change Focus",
        "Press i for the facility list; b returns to the simulation from inspect prompts",
    )
    return detail


def build_system_details(session: SimulationSession, system: System):
    """Create the inspection view for a focused system."""
    state = session.get_system_state(system.id)
    system_type = session.settings.config_data.get_system_type(
        system.system_type_key or 0
    )

    detail = Table.grid(padding=(0, 1))
    detail.add_column(style="cyan")
    detail.add_column(style="green")
    detail.add_row("Title", system_type.title if system_type else system.id)
    detail.add_row(
        "Age", f"{system.age_years} years" if system.age_years is not None else "N/A"
    )
    detail.add_row(
        "Condition", _format_ci_and_status(state.condition_index, state.status_label)
    )
    detail.add_row("Open Work Orders", str(state.open_work_orders))
    detail.add_row("Mission Work Orders", str(state.mission_impacting_open_work_orders))

    if system.work_orders:
        detail.add_row(
            "Work Order Statuses", ", ".join(_work_order_status_labels(system))
        )
    else:
        detail.add_row("Work Order Statuses", "None")
    detail.add_row(
        "Change Focus",
        "Press i for the facility list; b returns to the simulation from inspect prompts",
    )
    return detail


def build_controls_panel() -> Panel:
    """Render available key controls for the live shell."""
    overview = Text(style="dim")
    overview.append("Use these keys while the simulation is open. Press ")
    overview.append("h", style="bold dim")
    overview.append(" at any time to hide or show this help.\n")
    overview.append(
        "Mission alerts: the red strip shows a sentence plus category counts and thresholds. Press "
    )
    overview.append("a", style="bold dim")
    overview.append(
        " to pause and open the mission-impact view: how alerts work, a snapshot, a table with "
        "short 'why' text, then pick a number for metrics, rule bullets, and sample work orders; "
    )
    overview.append("0", style="bold dim")
    overview.append(" (or default) closes and returns to the dashboard.\n")

    table = Table(expand=True, show_header=True, header_style="bold cyan")
    table.add_column("Keys", style="bold yellow", width=14)
    table.add_column("Action", style="cyan", width=22)
    table.add_column("Instruction", style="green")

    table.add_row(
        "space / p", "Pause or resume", "Toggle the simulation clock on or off."
    )
    table.add_row("n", "Single-step", "Advance exactly one tick and then pause again.")
    table.add_row(
        "t", "Change tick size", "Cycle through day, week, month, and year ticks."
    )
    table.add_row(
        "+ or ]", "Speed up", "Reduce the delay between ticks so time passes faster."
    )
    table.add_row(
        "- or [",
        "Slow down",
        "Increase the delay between ticks so you can inspect changes.",
    )
    table.add_row(
        "i",
        "Inspect / focus",
        "Facility list first (number, s=system, c=clear, b=simulation); system flow uses b to exit.",
    )
    table.add_row(
        "a",
        "Mission alerts",
        "When the red strip is visible: rules + snapshot + table; pick # to drill down (0 to close).",
    )
    table.add_row(
        "f",
        "Toggle systems",
        "Show or hide systems under facilities in the installation graph.",
    )
    table.add_row(
        "s",
        "Edit settings",
        "Pause and open the MIDAS settings editor (saved to JSON on return / exit).",
    )
    table.add_row("h", "Hide / show help", "Toggle this controls panel.")
    table.add_row(
        "q / Ctrl-C",
        "Quit simulation",
        "Exit the live simulation and return to the menu.",
    )

    tips = Text(
        "Tip: focused facilities and systems are highlighted, and focused facilities automatically show their systems.",
        style="dim",
    )
    return Panel(Group(overview, table, tips), title="Controls", border_style="blue")


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
        for facility in sorted(
            children_by_parent.get(parent_id, []), key=_facility_sort_key
        ):
            facility_state = session.get_facility_state(facility.id)
            facility_node = parent_node.add(
                _format_facility_label(
                    session=session,
                    facility=facility,
                    runtime_state=facility_state,
                    selected=session.selected_facility_id == facility.id,
                )
            )
            should_show_systems = (
                show_systems or session.selected_facility_id == facility.id
            )
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
            if not candidate.dependency_position.has_shared_group(
                facility.dependency_position
            ):
                continue

            shared_groups = len(
                set(candidate.dependency_position.group_ids)
                & set(facility.dependency_position.group_ids)
            )
            candidate_score = (
                candidate.dependency_position.depth,
                shared_groups,
                candidate.id,
            )
            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                parent_id = candidate.id
        parent_map[facility.id] = parent_id

    return parent_map


def _build_facility_inspect_table(session: SimulationSession) -> Table:
    """Table of facilities with runtime CI and status for the inspect flow."""
    table = Table(title="Facilities", show_header=True, header_style="bold cyan")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Facility", style="green")
    table.add_column("Dependency", style="yellow")
    table.add_column("CI", style="magenta", justify="right")
    table.add_column("Status", style="white")
    for index, facility in enumerate(
        sorted(session.facilities, key=_facility_sort_key), start=1
    ):
        facility_type = session.settings.config_data.get_facility_type(
            facility.facility_type_key or 0
        )
        runtime = session.get_facility_state(facility.id)
        table.add_row(
            str(index),
            facility_type.title if facility_type else facility.id,
            str(facility.dependency_position),
            _format_ci(runtime.condition_index),
            runtime.status_label,
        )
    return table


def prompt_for_focus_selection(session: SimulationSession) -> None:
    """Facility-first inspect: pick by number, or s/c/b; b returns to the live simulation."""
    if not session.facilities:
        DisplayHelper.print_warning("No facilities are available to inspect.")
        InputHelper.wait_for_continue()
        return

    sorted_facilities = sorted(session.facilities, key=_facility_sort_key)
    n_fac = len(sorted_facilities)

    while True:
        DisplayHelper.print_table(_build_facility_inspect_table(session))
        console.print(
            "[dim]Enter a facility number (1-"
            f"{n_fac}), "
            "[bold dim]s[/bold dim] = pick a system, "
            "[bold dim]c[/bold dim] = clear focus, "
            "[bold dim]b[/bold dim] = back to simulation[/dim]"
        )
        raw = InputHelper.get_input_with_backspace(
            "Inspect", default="", allow_empty=False
        )
        if raw is None:
            return
        key = raw.strip().lower()
        if key in {"b", "back"}:
            return
        if key in {"c", "clear"}:
            session.clear_selection()
            return
        if key in {"s", "system"}:
            _prompt_for_system_selection(session)
            return
        try:
            choice = int(key)
        except ValueError:
            console.print(f"[red]Invalid choice. Use 1-{n_fac}, s, c, or b.[/red]\n")
            continue
        if choice < 1 or choice > n_fac:
            console.print(
                f"[red]Facility number must be between 1 and {n_fac}.[/red]\n"
            )
            continue
        session.set_selected_facility(sorted_facilities[choice - 1].id)
        return


def _prompt_for_system_selection(session: SimulationSession) -> None:
    """Prompt the user to pick a facility (or Unassigned), then a system under it."""
    if not session.systems:
        DisplayHelper.print_warning("No systems are available to inspect.")
        InputHelper.wait_for_continue()
        return

    sorted_facilities = sorted(session.facilities, key=_facility_sort_key)
    orphan_systems = [
        system
        for system in session.systems
        if not system.facility_id or system.facility_id not in session.facilities_by_id
    ]
    groups: list[tuple[Facility | None, list[System]]] = [
        (facility, session.systems_by_facility.get(facility.id, []))
        for facility in sorted_facilities
    ]
    if orphan_systems:
        groups.append((None, orphan_systems))

    fac_table = Table(
        title="Facilities (choose one to list its systems)",
        show_header=True,
        header_style="bold cyan",
    )
    fac_table.add_column("#", style="cyan", width=4)
    fac_table.add_column("Facility", style="green")
    fac_table.add_column("Dependency", style="yellow")
    fac_table.add_column("CI", style="magenta", justify="right")
    fac_table.add_column("Status", style="white")
    for index, (facility, systems) in enumerate(groups, start=1):
        if facility is None:
            fac_table.add_row(
                str(index), "Unassigned", "—", "—", f"{len(systems)} system(s)"
            )
        else:
            runtime = session.get_facility_state(facility.id)
            fac_table.add_row(
                str(index),
                _facility_title(session, facility),
                str(facility.dependency_position),
                _format_ci(runtime.condition_index),
                runtime.status_label,
            )
    DisplayHelper.print_table(fac_table)
    console.print(
        "[dim]Enter [bold dim]b[/bold dim] to return to the simulation without selecting.[/dim]"
    )

    fac_pick = InputHelper.ask_number(
        f"Select facility group 1-{len(groups)} (or b)",
        min_value=1,
        max_value=len(groups),
        allow_back=True,
    )
    if fac_pick is None:
        return
    _facility, group_systems = groups[fac_pick - 1]
    if not group_systems:
        DisplayHelper.print_warning("This facility has no systems to inspect.")
        InputHelper.wait_for_continue()
        return

    sys_table = Table(title="Systems", show_header=True, header_style="bold cyan")
    sys_table.add_column("#", style="cyan", width=4)
    sys_table.add_column("System", style="green")
    sys_table.add_column("CI", style="magenta", justify="right")
    sys_table.add_column("Status", style="white")
    sys_table.add_column("Mission WOs", style="yellow", justify="right")
    for index, system in enumerate(sorted(group_systems, key=lambda s: s.id), start=1):
        s_runtime = session.get_system_state(system.id)
        sys_table.add_row(
            str(index),
            _system_title(session, system),
            _format_ci(s_runtime.condition_index),
            s_runtime.status_label,
            str(s_runtime.mission_impacting_open_work_orders),
        )
    DisplayHelper.print_table(sys_table)
    console.print(
        "[dim]Enter [bold dim]b[/bold dim] to return to the simulation without selecting.[/dim]"
    )

    sys_pick = InputHelper.ask_number(
        f"Select system 1-{len(group_systems)} (or b)",
        min_value=1,
        max_value=len(group_systems),
        allow_back=True,
    )
    if sys_pick is None:
        return
    session.set_selected_system(
        sorted(group_systems, key=lambda s: s.id)[sys_pick - 1].id
    )


def _format_facility_label(
    session: SimulationSession,
    facility: Facility,
    runtime_state: EntityRuntimeState,
    selected: bool,
) -> str:
    """Format a facility label for the dependency tree."""
    facility_type = session.settings.config_data.get_facility_type(
        facility.facility_type_key or 0
    )
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
    system_type = session.settings.config_data.get_system_type(
        system.system_type_key or 0
    )
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


def _format_ci(value: float | None) -> str:
    """Format a condition-index value for display."""
    return f"{value:.2f}" if value is not None else "N/A"


def _work_order_status_labels(system: System) -> list[str]:
    """Return work-order statuses for a system as simple labels."""
    return [
        work_order.status.value if work_order.status else "Unknown"
        for work_order in system.work_orders
    ]
