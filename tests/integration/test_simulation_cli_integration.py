"""Integration tests for simulation CLI helper flows."""

from rich.console import Console

from src.cli.handlers.simulate_handlers import (
    _build_installation_selection_rows,
    _load_or_generate_simulation_result,
    _prompt_for_installation_id,
)
from src.cli.menu.menu_factory import get_main_menu, get_simulation_menu
from src.cli.simulation_shell_panels import build_controls_panel
from src.cli.utils import DisplayHelper, InputHelper, NavigationHelper
from src.config import MidasSettings
from src.simulation import DataGenerator


def test_build_installation_selection_rows_reflects_generated_hierarchy_counts() -> None:
    """Selection rows should summarize installation-level hierarchy counts."""
    result = DataGenerator(seed=42).generate_installations(2)

    rows = _build_installation_selection_rows(
        installations=result.installations,
        facilities=result.facilities,
        systems=result.systems,
        work_orders=result.work_orders,
    )
    rows_by_id = {row["id"]: row for row in rows}

    assert len(rows) == 2
    for installation in result.installations:
        expected_facilities = len([facility for facility in result.facilities if facility.installation_id == installation.id])
        facility_ids = {facility.id for facility in result.facilities if facility.installation_id == installation.id}
        expected_systems = len([system for system in result.systems if system.facility_id in facility_ids])
        expected_work_orders = len([wo for wo in result.work_orders if wo.installation_id == installation.id])

        row = rows_by_id[installation.id]
        assert row["facilities"] == str(expected_facilities)
        assert row["systems"] == str(expected_systems)
        assert row["work_orders"] == str(expected_work_orders)


def test_prompt_for_installation_id_returns_requested_selection(monkeypatch) -> None:
    """Prompt helper should return the installation chosen by the user."""
    settings = MidasSettings()
    result = DataGenerator(seed=42).generate_installations(2)

    monkeypatch.setattr(DisplayHelper, "print_table", staticmethod(lambda table: None))
    monkeypatch.setattr(InputHelper, "ask_number", staticmethod(lambda *args, **kwargs: 2))

    selected_id = _prompt_for_installation_id(result, settings)

    assert selected_id == result.installations[1].id


def test_load_or_generate_simulation_result_defaults_to_generation(monkeypatch) -> None:
    """Default CLI source flow should generate a fresh installation."""
    settings = MidasSettings()

    monkeypatch.setattr(NavigationHelper, "show_help", staticmethod(lambda *args, **kwargs: None))
    monkeypatch.setattr(InputHelper, "ask_choice", staticmethod(lambda *args, **kwargs: "generate"))

    result = _load_or_generate_simulation_result(settings)

    assert result is not None
    assert len(result.installations) == 1
    assert result.facilities
    assert result.systems


def test_build_controls_panel_lists_key_instructions() -> None:
    """Controls panel should clearly show key bindings and usage instructions."""
    console = Console(record=True, width=160)
    console.print(build_controls_panel())
    output = console.export_text()

    assert "space / p" in output
    assert "Pause or resume" in output
    assert "Single-step" in output
    assert "Inspect / focus" in output
    assert "Mission alerts" in output
    assert "category counts" in output
    assert "drill down" in output.lower()
    assert "q / Ctrl-C" in output


def test_run_time_simulation_is_first_main_menu_option() -> None:
    """Main menu should surface runtime simulation as the first selectable option."""
    menu = get_main_menu()
    labels = [item.label for item in menu.config.items if item.visible]

    assert labels[0] == "Run Time Simulation"
    assert "Configuration" in labels


def test_run_time_simulation_is_removed_from_simulation_submenu() -> None:
    """Runtime simulation should live on the main menu rather than the simulation submenu."""
    menu = get_simulation_menu()
    labels = [item.label for item in menu.config.items if item.visible]

    assert "Run Time Simulation" not in labels
