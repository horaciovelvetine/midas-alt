"""Unit tests for simulation shell dashboard panels (no Live loop)."""

from __future__ import annotations

from datetime import date

from rich.console import Console

import src.cli.simulation_shell_panels as shell_panels
from src.cli.simulation_shell_panels import (
    INSTALL_MISSION_WO_ALERT_THRESHOLD,
    SYSTEM_MISSION_WO_ALERT_THRESHOLD,
    build_installation_summary_panel,
    build_mission_alert_panel,
    build_simulation_overview_panel,
    collect_mission_alert_items,
    prompt_mission_alert_browser,
)
from src.enums.work_order import WO_Status
from src.models import DataStore, Facility, Installation, System, WorkOrder
from src.simulation.runtime.clock import SimulationClock, TickSize, TickUnit
from src.simulation.runtime.session import SimulationSession


def _session(
    *,
    installation: Installation,
    facilities: list[Facility],
    systems: list[System],
    work_orders: list[WorkOrder],
    paused: bool = True,
    stop_reason: str | None = None,
) -> SimulationSession:
    result = DataStore.from_single_installation(installation, facilities, systems, work_orders)
    session = SimulationSession(
        result=result,
        clock=SimulationClock(
            current_date=date(2020, 1, 1),
            tick_size=TickSize(1, TickUnit.DAY),
        ),
        modules=[],
        pause_policies=[],
        paused=paused,
    )
    if stop_reason is not None:
        session.pause(reason=stop_reason)
    return session


def _print_panel(panel) -> str:
    console = Console(record=True, width=120)
    console.print(panel)
    return console.export_text()


def test_top_panels_show_installation_and_simulation_titles_and_condition_index_label() -> None:
    """Installation and simulation summaries are split; CI label is spelled out."""
    inst = Installation(id="in-1", title="Alpha Base", location="Somewhere", region="US")
    fac = Facility(id="f-1", installation_id=inst.id, facility_type_key=1)
    inst.facility_ids = [fac.id]
    sys = System(id="s-1", facility_id=fac.id, system_type_key=1, condition_index=88.0)
    fac.system_ids = [sys.id]
    session = _session(installation=inst, facilities=[fac], systems=[sys], work_orders=[])

    install_text = _print_panel(build_installation_summary_panel(session))
    sim_text = _print_panel(build_simulation_overview_panel(session))

    assert "Installation Details" in install_text
    assert "Simulation Overview" in sim_text
    assert "Condition Index" in install_text
    assert "Alpha Base" in install_text
    assert "2020-01-01" in sim_text
    assert "Installation CI" not in install_text


def test_mission_alert_panel_shows_mission_blocked_system() -> None:
    """Mission-blocked systems produce a compact summary strip; full text lives in alert items."""
    inst = Installation(id="in-1", title="Test Inst")
    fac = Facility(id="f-1", installation_id=inst.id)
    inst.facility_ids = [fac.id]
    sys = System(id="s-1", facility_id=fac.id, condition_index=0.0)
    fac.system_ids = [sys.id]
    wo = WorkOrder(
        system_id=sys.id,
        installation_id=inst.id,
        facility_id=fac.id,
        status=WO_Status.IN_PROGRESS,
        impacts_mission=True,
    )
    session = _session(
        installation=inst,
        facilities=[fac],
        systems=[sys],
        work_orders=[wo],
    )
    panel = build_mission_alert_panel(session)
    assert panel is not None
    text = _print_panel(panel)
    assert "Mission alerts" in text
    assert "Active mission impact" in text
    assert "mission-blocked" in text.lower()
    assert "Press a" in text
    items = collect_mission_alert_items(session)
    assert any("MISSION BLOCKED" in item.detail and "s-1" in item.detail for item in items)
    blocked = next(item for item in items if item.kind == "mission_blocked")
    assert blocked.severity == "critical"
    assert blocked.why_brief
    assert blocked.reason_lines
    assert blocked.entity_type is not None and blocked.entity_id


def test_mission_alert_installation_wide_mission_work_orders_threshold() -> None:
    """Many mission-impacting open WOs trigger installation high-impact when not mission-blocked.

    Spread WOs across systems so no single system hits the per-system threshold (2).
    """
    inst = Installation(id="in-1", title="HQ")
    fac = Facility(id="f-1", installation_id=inst.id)
    inst.facility_ids = [fac.id]
    systems: list[System] = []
    work_orders: list[WorkOrder] = []
    for i in range(INSTALL_MISSION_WO_ALERT_THRESHOLD):
        sid = f"s-{i}"
        systems.append(System(id=sid, facility_id=fac.id, condition_index=80.0))
        work_orders.append(
            WorkOrder(
                system_id=sid,
                installation_id=inst.id,
                facility_id=fac.id,
                status=WO_Status.SUBMITTED,
                impacts_mission=True,
            )
        )
    fac.system_ids = [s.id for s in systems]
    session = _session(
        installation=inst,
        facilities=[fac],
        systems=systems,
        work_orders=work_orders,
    )
    panel = build_mission_alert_panel(session)
    assert panel is not None
    text = _print_panel(panel)
    assert "installation-wide high mission-impacting" in text
    assert "per-system" not in text.lower()
    items = collect_mission_alert_items(session)
    thresh = str(INSTALL_MISSION_WO_ALERT_THRESHOLD)
    assert any(thresh in item.detail and "installation has" in item.detail for item in items)


def test_mission_alert_per_system_mission_work_orders_not_duplicated_for_mission_blocked() -> None:
    """Per-system high mission WO line is omitted when that system is already mission-blocked."""
    inst = Installation(id="in-1", title="HQ")
    fac = Facility(id="f-1", installation_id=inst.id)
    inst.facility_ids = [fac.id]
    sys = System(id="s-1", facility_id=fac.id, condition_index=0.0)
    fac.system_ids = [sys.id]
    work_orders = [
        WorkOrder(
            system_id=sys.id,
            installation_id=inst.id,
            facility_id=fac.id,
            status=WO_Status.IN_PROGRESS,
            impacts_mission=True,
        )
        for _ in range(max(SYSTEM_MISSION_WO_ALERT_THRESHOLD, 2))
    ]
    session = _session(
        installation=inst,
        facilities=[fac],
        systems=[sys],
        work_orders=work_orders,
    )
    text = _print_panel(build_mission_alert_panel(session))
    assert "mission-blocked" in text.lower()
    assert "per-system" not in text.lower()
    items = collect_mission_alert_items(session)
    assert not any(item.kind == "system_high_wo" for item in items)


def test_mission_alert_per_system_threshold_without_mission_blocked() -> None:
    """Operational system with enough mission WOs triggers high-impact line."""
    inst = Installation(id="in-1", title="HQ")
    fac = Facility(id="f-1", installation_id=inst.id)
    inst.facility_ids = [fac.id]
    sys = System(id="s-1", facility_id=fac.id, condition_index=70.0)
    fac.system_ids = [sys.id]
    work_orders = [
        WorkOrder(
            system_id=sys.id,
            installation_id=inst.id,
            facility_id=fac.id,
            status=WO_Status.APPROVED,
            impacts_mission=True,
        )
        for _ in range(SYSTEM_MISSION_WO_ALERT_THRESHOLD)
    ]
    session = _session(
        installation=inst,
        facilities=[fac],
        systems=[sys],
        work_orders=work_orders,
    )
    panel = build_mission_alert_panel(session)
    assert panel is not None
    text = _print_panel(panel)
    assert "per-system mission WO threshold" in text
    items = collect_mission_alert_items(session)
    assert any(item.kind == "system_high_wo" and str(SYSTEM_MISSION_WO_ALERT_THRESHOLD) in item.detail for item in items)


def test_mission_alert_panel_none_when_no_issues() -> None:
    """Healthy installation produces no alert panel."""
    inst = Installation(id="in-1", title="OK")
    fac = Facility(id="f-1", installation_id=inst.id)
    inst.facility_ids = [fac.id]
    sys = System(id="s-1", facility_id=fac.id, condition_index=90.0)
    fac.system_ids = [sys.id]
    session = _session(installation=inst, facilities=[fac], systems=[sys], work_orders=[])
    assert build_mission_alert_panel(session) is None


def test_simulation_overview_shows_pause_reason() -> None:
    """Pause reason appears only on the simulation overview panel."""
    inst = Installation(id="in-1", title="T")
    session = _session(
        installation=inst,
        facilities=[],
        systems=[],
        work_orders=[],
        stop_reason="Paused for inspection.",
    )
    text = _print_panel(build_simulation_overview_panel(session))
    assert "Pause Reason" in text
    assert "Paused for inspection." in text


def test_prompt_mission_alert_browser_can_open_and_close(monkeypatch) -> None:
    """Mission alert browser renders prompt content before exiting on 0."""
    inst = Installation(id="in-1", title="Test Inst")
    fac = Facility(id="f-1", installation_id=inst.id)
    inst.facility_ids = [fac.id]
    sys = System(id="s-1", facility_id=fac.id, condition_index=0.0)
    fac.system_ids = [sys.id]
    wo = WorkOrder(
        system_id=sys.id,
        installation_id=inst.id,
        facility_id=fac.id,
        status=WO_Status.IN_PROGRESS,
        impacts_mission=True,
    )
    session = _session(
        installation=inst,
        facilities=[fac],
        systems=[sys],
        work_orders=[wo],
    )

    recorded_console = Console(record=True, width=120)
    monkeypatch.setattr(shell_panels, "console", recorded_console)
    monkeypatch.setattr(shell_panels.DisplayHelper, "print_table", staticmethod(lambda *_a, **_k: None))
    monkeypatch.setattr(shell_panels.InputHelper, "ask_number", staticmethod(lambda *_a, **_k: 0))

    prompt_mission_alert_browser(session)

    output = recorded_console.export_text()
    assert "How mission alerts work" in output
    assert "This tick" in output
