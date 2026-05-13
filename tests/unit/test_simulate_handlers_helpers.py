"""Unit tests for ``simulate_handlers`` formatting and selection helpers."""

from __future__ import annotations

from datetime import datetime

import pytest
from rich.console import Console

import src.cli.handlers.simulate_handlers as simulate_handlers
from src.cli.utils.input import InputHelper
from src.config import MidasConfigData, MidasSettings
from src.enums import UFCGrade, WO_Priority, WO_Status, WO_TradeSkill
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


def _seed_reference_data() -> None:
    """Seed reference data so ``_format_facility`` / ``_format_system`` get titles."""
    MidasConfigData().replace_reference_data(
        facility_types={1: FacilityType(key=1, title="Hangar", life_expectancy=50)},
        system_types={
            1: SystemType(key=1, title="HVAC", life_expectancy=20, facility_keys=(1,))
        },
    )


def _build_facility() -> Facility:
    return Facility(
        id="f-1",
        installation_id="i-1",
        facility_type_key=1,
        facility_type_title="Hangar",
        year_constructed=2000,
        dependency_position=DependencyPosition(),
        resiliency_grade=UFCGrade.G3,
        system_ids=["s-1", "s-2"],
        condition_index=72.5,
    )


def _build_system() -> System:
    return System(
        id="s-1",
        facility_id="f-1",
        system_type_key=1,
        year_constructed=2005,
        condition_index=80.0,
    )


def _build_work_order() -> WorkOrder:
    return WorkOrder(
        id="wo-1",
        installation_id="i-1",
        facility_id="f-1",
        system_id="s-1",
        status=WO_Status.SUBMITTED,
        priority=WO_Priority.ROUTINE,
        trade=WO_TradeSkill.HVAC,
        request_datetime=datetime(2026, 1, 1, 9, 0),
        problem_description="Filter replacement",
        requested_action="Replace filter",
        actions_taken=None,
    )


# ! ==========================================================================================>
# ! _format_* helpers
# ! ==========================================================================================>


def test_format_facility_uses_reference_data_title() -> None:
    """``_format_facility`` resolves the title from the reference cache."""
    _seed_reference_data()
    text = simulate_handlers._format_facility(_build_facility(), MidasSettings())
    assert "Hangar" in text
    assert "Year Constructed: 2000" in text
    assert "Resiliency Grade: 3" in text
    assert "Systems: 2" in text


def test_format_facility_falls_back_to_placeholder_title() -> None:
    """Unknown facility type key produces the ``Facility <key>`` fallback label."""
    MidasConfigData().clear()
    facility = _build_facility()
    facility.facility_type_title = ""
    text = simulate_handlers._format_facility(facility, MidasSettings())
    assert "Facility 1" in text


def test_format_facility_handles_missing_condition_index() -> None:
    """A ``None`` condition index renders as ``N/A``."""
    _seed_reference_data()
    facility = _build_facility()
    facility.condition_index = None
    text = simulate_handlers._format_facility(facility, MidasSettings())
    assert "Condition Index: N/A" in text


def test_format_system_uses_reference_data_title() -> None:
    """``_format_system`` resolves system type title from the reference cache."""
    _seed_reference_data()
    text = simulate_handlers._format_system(_build_system(), MidasSettings())
    assert "HVAC" in text
    assert "Work Orders: 0" in text


def test_format_work_order_handles_optional_fields() -> None:
    """``_format_work_order`` emits ``N/A`` for missing optional fields."""
    wo = _build_work_order()
    wo.completion_datetime = None
    text = simulate_handlers._format_work_order(wo)
    assert "Status: Submitted" in text
    assert "Priority: Routine" in text
    assert "Trade: HVAC" in text
    assert "Completed: N/A" in text
    assert "Actions Taken: N/A" in text


def test_format_installation_includes_facility_count() -> None:
    """``_format_installation`` reports the number of facilities passed in."""
    inst = Installation(
        id="i-1", title="Base", condition_index=88.0, facility_ids=["f-1"]
    )
    text = simulate_handlers._format_installation(inst, [_build_facility()])
    assert "Title: Base" in text
    assert "Facilities: 1" in text
    assert "Condition Index: 88.00" in text


def test_format_installation_handles_missing_condition_index() -> None:
    """A ``None`` installation CI renders as ``N/A``."""
    inst = Installation(id="i-1", title="Base", facility_ids=[])
    text = simulate_handlers._format_installation(inst, [])
    assert "Condition Index: N/A" in text


# ! ==========================================================================================>
# ! _work_orders_for_system
# ! ==========================================================================================>


def test_work_orders_for_system_prefers_embedded_records() -> None:
    """When the system has embedded work orders, the flat list is ignored."""
    system = _build_system()
    embedded = _build_work_order()
    system.work_orders = [embedded]
    flat = [WorkOrder(id="other", system_id=system.id)]
    result = simulate_handlers._work_orders_for_system(system, flat)
    assert result == [embedded]


def test_work_orders_for_system_falls_back_to_flat_list() -> None:
    """When the system has no embedded orders, matching flat rows are returned."""
    system = _build_system()
    matching = WorkOrder(id="match", system_id=system.id)
    other = WorkOrder(id="other", system_id="different")
    result = simulate_handlers._work_orders_for_system(system, [matching, other])
    assert result == [matching]


# ! ==========================================================================================>
# ! _build_installation_selection_rows
# ! ==========================================================================================>


def test_build_installation_selection_rows_counts_descendants() -> None:
    """Each installation row reports facility/system/work-order totals."""
    inst = Installation(
        id="i-1", title="Base", facility_ids=["f-1"], condition_index=72.5
    )
    facility = _build_facility()
    facility.installation_id = inst.id
    system = _build_system()
    system.facility_id = facility.id
    work_order = _build_work_order()
    work_order.installation_id = inst.id
    work_order.facility_id = facility.id
    work_order.system_id = system.id

    rows = simulate_handlers._build_installation_selection_rows(
        installations=[inst],
        facilities=[facility],
        systems=[system],
        work_orders=[work_order],
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Base"
    assert row["facilities"] == "1"
    assert row["systems"] == "1"
    assert row["work_orders"] == "1"
    assert row["condition_index"] == "72.50"


def test_build_installation_selection_rows_handles_missing_fields() -> None:
    """Missing title/location/CI fall back to ``N/A``."""
    inst = Installation(id="i-1", title="", location="", condition_index=None)
    rows = simulate_handlers._build_installation_selection_rows(
        installations=[inst], facilities=[], systems=[], work_orders=[]
    )
    assert rows[0]["title"] == "i-1"
    assert rows[0]["location"] == "N/A"
    assert rows[0]["condition_index"] == "N/A"


# ! ==========================================================================================>
# ! _prompt_for_installation_id
# ! ==========================================================================================>


def test_prompt_for_installation_id_returns_only_id_for_single_installation() -> None:
    """A single-installation result skips the prompt and returns the only id."""
    result = DataStore(
        installations=[Installation(id="solo", title="One")],
        facilities=[],
        systems=[],
        work_orders=[],
    )
    assert (
        simulate_handlers._prompt_for_installation_id(result, MidasSettings()) == "solo"
    )


def test_prompt_for_installation_id_returns_none_when_no_installations() -> None:
    """An empty installation list yields ``None``."""
    result = DataStore(installations=[], facilities=[], systems=[], work_orders=[])
    assert (
        simulate_handlers._prompt_for_installation_id(result, MidasSettings()) is None
    )


def test_prompt_for_installation_id_prompts_for_choice_when_multiple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple installations trigger ``InputHelper.ask_number`` and return the picked id."""
    result = DataStore(
        installations=[
            Installation(id="a", title="A"),
            Installation(id="b", title="B"),
        ],
        facilities=[],
        systems=[],
        work_orders=[],
    )
    monkeypatch.setattr(
        simulate_handlers.DisplayHelper,
        "print_table",
        staticmethod(lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(InputHelper, "ask_number", staticmethod(lambda *a, **k: 2))

    chosen = simulate_handlers._prompt_for_installation_id(result, MidasSettings())
    assert chosen == "b"


def test_prompt_for_installation_id_returns_none_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Quit-to-menu sentinel during prompt returns ``None``."""
    result = DataStore(
        installations=[
            Installation(id="a", title="A"),
            Installation(id="b", title="B"),
        ],
        facilities=[],
        systems=[],
        work_orders=[],
    )
    monkeypatch.setattr(
        simulate_handlers.DisplayHelper,
        "print_table",
        staticmethod(lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(
        InputHelper,
        "ask_number",
        staticmethod(lambda *a, **k: InputHelper.QUIT_TO_MENU),
    )

    assert (
        simulate_handlers._prompt_for_installation_id(result, MidasSettings()) is None
    )


# ! ==========================================================================================>
# ! _display_selection_summary
# ! ==========================================================================================>


def test_display_selection_summary_uses_print_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_display_selection_summary`` calls ``DisplayHelper.print_table`` once."""
    calls: list[None] = []
    monkeypatch.setattr(
        simulate_handlers.DisplayHelper,
        "print_table",
        staticmethod(lambda *args, **kwargs: calls.append(None)),
    )

    simulate_handlers._display_selection_summary({"file_name": "x"})
    assert calls == [None]


# ! ==========================================================================================>
# ! _load_or_generate_simulation_result
# ! ==========================================================================================>


def test_load_or_generate_returns_none_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelling the choice prompt returns ``None``."""
    monkeypatch.setattr(
        simulate_handlers.NavigationHelper,
        "show_help",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        InputHelper,
        "ask_choice",
        staticmethod(lambda *a, **k: InputHelper.QUIT_TO_MENU),
    )
    assert (
        simulate_handlers._load_or_generate_simulation_result(MidasSettings()) is None
    )


def test_load_or_generate_falls_back_to_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Choosing ``generate`` invokes the data generator and returns its result."""

    class _StubGenerator:
        def generate_installation(self):
            return "stub-result"

    monkeypatch.setattr(
        simulate_handlers.NavigationHelper,
        "show_help",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        InputHelper, "ask_choice", staticmethod(lambda *a, **k: "generate")
    )
    monkeypatch.setattr(simulate_handlers, "DataGenerator", _StubGenerator)

    assert (
        simulate_handlers._load_or_generate_simulation_result(MidasSettings())
        == "stub-result"
    )


def test_load_or_generate_load_returns_none_when_path_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Blank/canceled path entry on ``load`` returns ``None``."""
    monkeypatch.setattr(
        simulate_handlers.NavigationHelper,
        "show_help",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(InputHelper, "ask_choice", staticmethod(lambda *a, **k: "load"))
    monkeypatch.setattr(
        InputHelper, "get_input_with_backspace", staticmethod(lambda *a, **k: None)
    )
    assert (
        simulate_handlers._load_or_generate_simulation_result(MidasSettings()) is None
    )
