"""Additional unit tests for shell panels (inspect, work orders, controls, focus prompts)."""

from __future__ import annotations

from datetime import date

import pytest
from rich.console import Console

import src.cli.simulation_shell_panels as shell_panels
from src.cli.simulation_shell_panels import (
    build_controls_panel,
    build_dependency_tree,
    build_facility_details,
    build_inspect_panel,
    build_installation_details,
    build_settings_snapshot_panel,
    build_system_details,
    build_work_order_summary_panel,
    prompt_for_focus_selection,
)
from src.cli.utils.input import InputHelper
from src.config import MidasConfigData, MidasSettings
from src.enums import WO_Priority, WO_Status, WO_TradeSkill
from src.models import (
    DataStore,
    DependencyPosition,
    Facility,
    FacilityType,
    Installation,
    System,
    SystemType,
    WorkOrder,
)
from src.simulation.runtime.clock import SimulationClock, TickSize, TickUnit
from src.simulation.runtime.session import SimulationSession


def _install_reference_data() -> None:
    """Seed two facility/system types so inspect panels show friendly titles."""
    MidasConfigData().replace_reference_data(
        facility_types={1: FacilityType(key=1, title="Hangar", life_expectancy=50)},
        system_types={
            1: SystemType(key=1, title="HVAC", life_expectancy=20, facility_keys=(1,))
        },
    )


def _build_session_with_work_orders(
    *,
    statuses: tuple[WO_Status, ...] = (),
    impacts_mission: tuple[bool, ...] = (),
    condition_index: float = 80.0,
) -> SimulationSession:
    """Build a one-installation session with parametric work orders for testing."""
    _install_reference_data()
    installation = Installation(
        id="i-1",
        title="Base",
        location="Loc",
        region="US",
        facility_ids=["f-1"],
    )
    facility = Facility(
        id="f-1",
        installation_id=installation.id,
        facility_type_key=1,
        facility_type_title="Hangar",
        system_ids=["s-1"],
        dependency_position=DependencyPosition(),
    )
    system = System(
        id="s-1",
        facility_id=facility.id,
        system_type_key=1,
        condition_index=condition_index,
    )
    work_orders: list[WorkOrder] = []
    for index, (status, mission) in enumerate(
        zip(statuses, impacts_mission, strict=False)
    ):
        work_orders.append(
            WorkOrder(
                id=f"wo-{index}",
                installation_id=installation.id,
                facility_id=facility.id,
                system_id=system.id,
                status=status,
                priority=WO_Priority.ROUTINE,
                trade=WO_TradeSkill.HVAC,
                impacts_mission=mission,
            )
        )

    data = DataStore(
        installations=[installation],
        facilities=[facility],
        systems=[system],
        work_orders=work_orders,
    )
    return SimulationSession(
        result=data,
        clock=SimulationClock(
            current_date=date(2026, 1, 1), tick_size=TickSize(1, TickUnit.DAY)
        ),
        modules=[],
        pause_policies=[],
    )


def _print(renderable) -> str:
    console = Console(record=True, width=140)
    console.print(renderable)
    return console.export_text()


# ! ==========================================================================================>
# ! INSPECT PANELS
# ! ==========================================================================================>


def test_build_inspect_panel_defaults_to_installation_view() -> None:
    """Without a selected facility/system, the inspect panel shows the installation."""
    session = _build_session_with_work_orders()
    text = _print(build_inspect_panel(session))
    assert "Inspecting Installation" in text
    assert "Base" in text


def test_build_inspect_panel_renders_facility_when_selected() -> None:
    """Selecting a facility flips the inspect panel to the facility detail variant."""
    session = _build_session_with_work_orders()
    session.set_selected_facility("f-1")
    text = _print(build_inspect_panel(session))
    assert "Inspecting Facility" in text
    assert "Hangar" in text


def test_build_inspect_panel_renders_system_when_selected() -> None:
    """Selecting a system flips the inspect panel to the system detail variant."""
    session = _build_session_with_work_orders(
        statuses=(WO_Status.APPROVED,),
        impacts_mission=(False,),
    )
    session.set_selected_system("s-1")
    text = _print(build_inspect_panel(session))
    assert "Inspecting System" in text
    assert "HVAC" in text
    assert "Work Order Statuses" in text


def test_build_system_details_handles_system_without_work_orders() -> None:
    """The system detail view labels the work-order list ``None`` when empty."""
    session = _build_session_with_work_orders()
    system = session.systems[0]
    text = _print(build_system_details(session, system))
    assert "None" in text


def test_build_facility_details_includes_runtime_aggregates() -> None:
    """The facility detail view shows degraded/inoperable child counts."""
    session = _build_session_with_work_orders(
        statuses=(WO_Status.SUBMITTED,),
        impacts_mission=(True,),
    )
    facility = session.facilities[0]
    text = _print(build_facility_details(session, facility))
    assert "Open Work Orders" in text
    assert "Mission Work Orders" in text
    assert "Degraded Children" in text
    assert "Inoperable Children" in text


def test_build_installation_details_shows_focused_placeholder_when_unselected() -> None:
    """The installation inspect view labels ``Focused`` as ``None`` when nothing is selected."""
    session = _build_session_with_work_orders()
    text = _print(build_installation_details(session))
    assert "Focused" in text
    assert "None" in text


# ! ==========================================================================================>
# ! WORK ORDER PANEL
# ! ==========================================================================================>


def test_build_work_order_summary_panel_lists_counts_by_status() -> None:
    """Work-order counts table lists ``Submitted`` and ``Approved`` totals."""
    session = _build_session_with_work_orders(
        statuses=(WO_Status.SUBMITTED, WO_Status.SUBMITTED, WO_Status.APPROVED),
        impacts_mission=(False, False, False),
    )
    text = _print(build_work_order_summary_panel(session))
    assert "Submitted" in text
    assert "Approved" in text


# ! ==========================================================================================>
# ! CONTROLS PANEL
# ! ==========================================================================================>


def test_build_controls_panel_contains_key_rows() -> None:
    """The controls panel lists every documented key shortcut."""
    text = _print(build_controls_panel())
    for key in ("space", "n", "t", "+", "-", "i", "a", "f", "h", "s", "q"):
        assert key in text


# ! ==========================================================================================>
# ! SETTINGS SNAPSHOT
# ! ==========================================================================================>


def test_settings_snapshot_panel_includes_threshold_label() -> None:
    """The snapshot panel includes the degraded threshold row label and value."""
    session = _build_session_with_work_orders()
    text = _print(build_settings_snapshot_panel(session))
    assert "Degraded Threshold (CI)" in text


def test_settings_snapshot_panel_flags_unsaved_settings() -> None:
    """When the settings singleton is dirty, the panel title and border switch."""
    session = _build_session_with_work_orders()
    settings = MidasSettings()
    settings.set_value("condition_index_degraded_threshold", 45.0)
    assert settings.is_dirty()

    panel = build_settings_snapshot_panel(session)
    assert "[unsaved]" in str(panel.title)
    assert panel.border_style == "red"


# ! ==========================================================================================>
# ! DEPENDENCY TREE
# ! ==========================================================================================>


def test_build_dependency_tree_includes_facility_title() -> None:
    """The dependency tree renders the facility type title for each node."""
    session = _build_session_with_work_orders()
    tree = build_dependency_tree(session, show_systems=False)
    text = _print(tree)
    assert "Hangar" in text


def test_build_dependency_tree_shows_systems_when_flag_enabled() -> None:
    """``show_systems=True`` renders system labels under their facility node."""
    session = _build_session_with_work_orders()
    tree = build_dependency_tree(session, show_systems=True)
    text = _print(tree)
    assert "HVAC" in text


# ! ==========================================================================================>
# ! FOCUS SELECTION PROMPT
# ! ==========================================================================================>


def test_prompt_for_focus_selection_warns_when_no_facilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty facility list short-circuits to a warning and returns."""
    session = _build_session_with_work_orders()
    session.result.facilities = []
    session.rebuild_indexes()

    warned: list[str] = []
    monkeypatch.setattr(
        shell_panels.DisplayHelper,
        "print_warning",
        staticmethod(lambda message, *a, **k: warned.append(message)),
    )
    monkeypatch.setattr(
        InputHelper, "wait_for_continue", staticmethod(lambda message="": None)
    )

    prompt_for_focus_selection(session)
    assert warned and "No facilities" in warned[0]


def test_prompt_for_focus_selection_selects_facility_by_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A numeric input selects the corresponding facility in the session."""
    session = _build_session_with_work_orders()

    monkeypatch.setattr(
        shell_panels.DisplayHelper,
        "print_table",
        staticmethod(lambda *_a, **_k: None),
    )
    monkeypatch.setattr(
        InputHelper,
        "get_input_with_backspace",
        staticmethod(lambda *a, **k: "1"),
    )

    prompt_for_focus_selection(session)
    assert session.selected_facility_id == "f-1"


def test_prompt_for_focus_selection_b_returns_without_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An immediate ``b`` exits without altering selection."""
    session = _build_session_with_work_orders()
    session.set_selected_facility("f-1")

    monkeypatch.setattr(
        shell_panels.DisplayHelper,
        "print_table",
        staticmethod(lambda *_a, **_k: None),
    )
    monkeypatch.setattr(
        InputHelper,
        "get_input_with_backspace",
        staticmethod(lambda *a, **k: "b"),
    )

    prompt_for_focus_selection(session)
    assert session.selected_facility_id == "f-1"


def test_prompt_for_focus_selection_c_clears_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``c`` clears the active facility selection."""
    session = _build_session_with_work_orders()
    session.set_selected_facility("f-1")

    monkeypatch.setattr(
        shell_panels.DisplayHelper,
        "print_table",
        staticmethod(lambda *_a, **_k: None),
    )
    monkeypatch.setattr(
        InputHelper,
        "get_input_with_backspace",
        staticmethod(lambda *a, **k: "c"),
    )

    prompt_for_focus_selection(session)
    assert session.selected_facility_id is None
