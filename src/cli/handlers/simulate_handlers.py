"""Simulation-related command handlers."""

import logging
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.cli.simulation_shell import SimulationShell
from src.cli.utils import DisplayHelper, InputHelper, NavigationHelper
from src.config import MIDASSettings
from src.config.app_state import get_app_state
from src.io import DataExporter, SimulationDataLoader
from src.models import Facility, Installation, System, WorkOrder
from src.simulation import DataGenerator, SimulationSession
from src.simulation.modules.system_degradation import SystemDegradationModule

logger = logging.getLogger(__name__)
console = Console()


def _get_settings() -> MIDASSettings:
    """Get settings from the application state."""
    return get_app_state().settings


def _display_selection_summary(selections: dict) -> None:
    """Display summary of current selections in a table."""
    table = Table(
        title="Current Configuration Summary",
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Setting", style="cyan", no_wrap=True, width=30)
    table.add_column("Value", style="green", width=50)

    # File settings
    table.add_row(
        "File Name",
        selections.get("file_name") or "[dim]Not set[/dim]",
        style="default",
    )
    table.add_row(
        "Output Format",
        selections.get("file_output") or "[dim]Not set[/dim]",
        style="default",
    )
    table.add_row(
        "Output Directory",
        str(selections.get("output_directory") or "[dim]Not set[/dim]"),
        style="default",
    )

    table.add_section()

    # Generation settings
    table.add_row(
        "Generation Method",
        selections.get("generation_method") or "[dim]Not set[/dim]",
        style="default",
    )
    target_count = selections.get("target_count")
    if target_count is not None:
        table.add_row("Target Count", str(target_count), style="default")
    else:
        method = selections.get("generation_method", "")
        if method in ["installations", "facilities"]:
            table.add_row(
                "Target Count", "[yellow]Required but not set[/yellow]", style="default"
            )
        else:
            table.add_row(
                "Target Count", "[dim]N/A (using default method)[/dim]", style="default"
            )

    table.add_section()

    # Output settings
    layout = selections.get("layout") or "[dim]Not set[/dim]"
    layout_display = f"{layout} {'(recommended)' if layout == 'normalized' else ''}"
    table.add_row("Output Layout", layout_display, style="default")

    gen_metadata = selections.get("generate_metadata")
    metadata_display = "Yes" if gen_metadata else "No"
    table.add_row("Generate Metadata", metadata_display, style="default")

    description = selections.get("description") or ""
    desc_display = description if description else "[dim]None[/dim]"
    table.add_row(
        "Description",
        desc_display[:47] + "..." if len(desc_display) > 50 else desc_display,
        style="default",
    )

    DisplayHelper.print_table(table)


def _format_facility(facility: Facility, settings: MIDASSettings) -> str:
    """Format a facility for display."""
    facility_type = settings.get_facility_type(facility.facility_type_key or 0)
    title = (
        facility_type.title
        if facility_type
        else f"Facility {facility.facility_type_key}"
    )

    lines = [
        f"ID: {facility.id}",
        f"Type: {title} (Key: {facility.facility_type_key})",
        f"Year Constructed: {facility.year_constructed}",
        f"Age: {facility.age_years} years",
        (
            f"Condition Index: {facility.condition_index:.2f}"
            if facility.condition_index
            else "Condition Index: N/A"
        ),
        f"Dependency Chain: {facility.dependency_position}",
        f"Resiliency Grade: {facility.resiliency_grade.value if facility.resiliency_grade else 'N/A'}",
        f"Systems: {len(facility.system_ids)}",
    ]
    return "\n".join(lines)


def _format_system(system: System, settings: MIDASSettings) -> str:
    """Format a system for display."""
    system_type = settings.get_system_type(system.system_type_key or 0)
    title = system_type.title if system_type else f"System {system.system_type_key}"

    lines = [
        f"ID: {system.id}",
        f"Type: {title} (Key: {system.system_type_key})",
        f"Year Constructed: {system.year_constructed}",
        f"Age: {system.age_years} years",
        (
            f"Condition Index: {system.condition_index:.2f}"
            if system.condition_index
            else "Condition Index: N/A"
        ),
        f"Work Orders: {len(system.work_orders)}",
    ]
    return "\n".join(lines)


def _work_orders_for_system(
    system: System, flat_work_orders: list[WorkOrder]
) -> list[WorkOrder]:
    """Return work orders for a system, preferring embedded records then flat data-store rows."""
    if system.work_orders:
        return list(system.work_orders)
    sid = system.id
    return [wo for wo in flat_work_orders if wo.system_id == sid]


def _format_work_order(work_order: WorkOrder) -> str:
    """Format a work order for detail display."""
    lines = [
        f"ID: {work_order.id}",
        f"Status: {work_order.status.value if work_order.status else 'N/A'}",
        f"Priority: {work_order.priority.value if work_order.priority else 'N/A'}",
        f"Trade: {work_order.trade.value if work_order.trade else 'N/A'}",
        f"Requested: {work_order.request_datetime.isoformat() if work_order.request_datetime else 'N/A'}",
        f"Completed: {work_order.completion_datetime.isoformat() if work_order.completion_datetime else 'N/A'}",
        f"Problem: {work_order.problem_description or 'N/A'}",
        f"Requested Action: {work_order.requested_action or 'N/A'}",
        f"Actions Taken: {work_order.actions_taken or 'N/A'}",
    ]
    return "\n".join(lines)


def _format_installation(installation: Installation, facilities: list[Facility]) -> str:
    """Format an installation for display."""
    lines = [
        f"ID: {installation.id}",
        f"Title: {installation.title}",
        (
            f"Condition Index: {installation.condition_index:.2f}"
            if installation.condition_index
            else "Condition Index: N/A"
        ),
        f"Facilities: {len(facilities)}",
    ]
    return "\n".join(lines)


def _build_installation_selection_rows(
    installations: list[Installation],
    facilities: list[Facility],
    systems: list[System],
    work_orders: list[WorkOrder],
) -> list[dict[str, str]]:
    """Create installation summary rows for selection and testing."""
    facility_counts: dict[str, int] = {}
    system_counts: dict[str, int] = {}
    work_order_counts: dict[str, int] = {}
    facility_to_installation = {
        facility.id: facility.installation_id for facility in facilities
    }
    system_to_installation = {}

    for facility in facilities:
        if facility.installation_id:
            facility_counts[facility.installation_id] = (
                facility_counts.get(facility.installation_id, 0) + 1
            )
    for system in systems:
        installation_id = facility_to_installation.get(system.facility_id)
        if installation_id:
            system_to_installation[system.id] = installation_id
            system_counts[installation_id] = system_counts.get(installation_id, 0) + 1
    for work_order in work_orders:
        installation_id = work_order.installation_id or system_to_installation.get(
            work_order.system_id or ""
        )
        if installation_id:
            work_order_counts[installation_id] = (
                work_order_counts.get(installation_id, 0) + 1
            )

    rows = []
    for installation in installations:
        rows.append(
            {
                "id": installation.id,
                "title": installation.title or installation.id,
                "location": installation.location or "N/A",
                "condition_index": (
                    f"{installation.condition_index:.2f}"
                    if installation.condition_index is not None
                    else "N/A"
                ),
                "facilities": str(facility_counts.get(installation.id, 0)),
                "systems": str(system_counts.get(installation.id, 0)),
                "work_orders": str(work_order_counts.get(installation.id, 0)),
            }
        )
    return rows


def _prompt_for_installation_id(result, settings: MIDASSettings) -> str | None:
    """Prompt the user to select an installation when multiple are available."""
    if not result.installations:
        return None
    if len(result.installations) == 1:
        return result.installations[0].id

    rows = _build_installation_selection_rows(
        installations=result.installations,
        facilities=result.facilities,
        systems=result.systems,
        work_orders=result.work_orders,
    )
    table = Table(
        title="Choose Installation To Simulate",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="cyan", width=4)
    table.add_column("Title", style="green")
    table.add_column("Location", style="yellow")
    table.add_column("CI", style="magenta", justify="right")
    table.add_column("Facilities", style="blue", justify="right")
    table.add_column("Systems", style="blue", justify="right")
    table.add_column("WOs", style="green", justify="right")

    for index, row in enumerate(rows, start=1):
        table.add_row(
            str(index),
            row["title"],
            row["location"],
            row["condition_index"],
            row["facilities"],
            row["systems"],
            row["work_orders"],
        )

    DisplayHelper.print_table(table)
    selection = InputHelper.ask_number(
        f"Select installation 1-{len(result.installations)} (q or Ctrl-C to cancel)",
        min_value=1,
        max_value=len(result.installations),
        default=1,
        allow_quit_flow=True,
    )
    if selection is None or selection is InputHelper.QUIT_TO_MENU:
        return None
    return result.installations[selection - 1].id


def _load_or_generate_simulation_result(settings: MIDASSettings):
    """Prompt the user to load exported data or generate a default installation."""
    NavigationHelper.show_help(
        "Simulation Data Source",
        "Load a normalized CSV/XLSX export from the data export flow, or generate one installation with default settings. "
        "Installations include generated maintenance work orders for the live dashboard.",
        "generate (default), load",
    )
    source = InputHelper.ask_choice(
        "Choose simulation data source [generate/load] (b back, q cancel)",
        choices=["generate", "load"],
        default="generate",
        allow_back=True,
        allow_quit_flow=True,
    )
    if source is None or source is InputHelper.QUIT_TO_MENU:
        return None
    if source == "generate":
        generator = DataGenerator(settings=settings)
        return generator.generate_installation()

    dataset_path = InputHelper.get_input_with_backspace(
        "Enter normalized dataset directory or XLSX workbook path",
        allow_empty=True,
    )
    if dataset_path is None:
        return None
    loader = SimulationDataLoader(settings=settings)
    return loader.load(Path(dataset_path))


def handle_run_time_simulation() -> None:
    """Load or generate one installation and enter the live simulation shell."""
    settings = _get_settings()

    try:
        result = _load_or_generate_simulation_result(settings)
        if result is None:
            return
        if not result.installations:
            DisplayHelper.print_warning(
                "No installations were available for simulation."
            )
            InputHelper.wait_for_continue()
            return

        installation_id = _prompt_for_installation_id(result, settings)
        if installation_id is None:
            return

        session = SimulationSession.from_data_store(
            data=result,
            settings=settings,
            installation_id=installation_id,
            modules=[SystemDegradationModule()],
        )
        SimulationShell(session).run()
        InputHelper.wait_for_continue("\nPress Enter to return to the simulation menu")
    except ValueError as exc:
        DisplayHelper.print_error(str(exc), title="Simulation Load Error")
        logger.exception("Simulation CLI input error")
        InputHelper.wait_for_continue()
    except Exception as exc:  # pragma: no cover - defensive user-facing handler
        DisplayHelper.print_error(
            f"Error running simulation: {exc}", title="Simulation Error"
        )
        logger.exception("Unexpected error running simulation")
        InputHelper.wait_for_continue()


def handle_view_simulated_data_examples() -> None:
    """View simulated data examples with interactive navigation."""
    settings = _get_settings()
    generator = DataGenerator(settings=settings, seed=None)  # Random seed for variety

    # Generate an installation for exploration
    result = generator.generate_installation()
    if not result.installations:
        DisplayHelper.print_warning("No installation generated.")
        return

    installation = result.installations[0]
    facilities = result.facilities
    systems = result.systems
    work_orders = result.work_orders

    # Build lookup maps
    systems_by_facility = {}
    work_orders_by_system: dict[str, list[WorkOrder]] = {}
    for s in systems:
        if s.facility_id not in systems_by_facility:
            systems_by_facility[s.facility_id] = []
        systems_by_facility[s.facility_id].append(s)
    for work_order in work_orders:
        if not work_order.system_id:
            continue
        if work_order.system_id not in work_orders_by_system:
            work_orders_by_system[work_order.system_id] = []
        work_orders_by_system[work_order.system_id].append(work_order)

    # Main navigation loop
    current_level = "installation"
    current_facility: Facility | None = None
    current_system: System | None = None
    current_work_order: WorkOrder | None = None

    while True:
        DisplayHelper.clear_screen()

        if current_level == "installation":
            console.print(
                "\n[bold cyan]Navigation:[/bold cyan] [green]Installation[/green]\n"
            )
            DisplayHelper.print_panel(
                content=_format_installation(installation, facilities),
                title="Installation Overview",
            )

            if not facilities:
                DisplayHelper.print_warning("This installation has no facilities.")
                InputHelper.wait_for_continue("\nPress Enter to return to menu")
                break

            # Show facilities list
            facilities_table = Table(
                title="Available Facilities", show_header=True, header_style="bold cyan"
            )
            facilities_table.add_column("#", style="cyan", width=4)
            facilities_table.add_column("Title", style="green")
            facilities_table.add_column("Key", style="yellow", justify="center")
            facilities_table.add_column("CI", style="magenta", justify="center")
            facilities_table.add_column("Systems", style="blue", justify="center")
            facilities_table.add_column("WOs", style="green", justify="center")

            for idx, facility in enumerate(facilities, start=1):
                facility_type = settings.get_facility_type(
                    facility.facility_type_key or 0
                )
                title = facility_type.title if facility_type else f"Facility {idx}"
                ci = (
                    f"{facility.condition_index:.1f}"
                    if facility.condition_index
                    else "N/A"
                )
                fac_systems = systems_by_facility.get(facility.id, [])
                system_count = len(fac_systems)
                wo_count = sum(
                    len(work_orders_by_system.get(s.id, [])) for s in fac_systems
                )
                facilities_table.add_row(
                    str(idx),
                    title,
                    str(facility.facility_type_key),
                    ci,
                    str(system_count),
                    str(wo_count),
                )

            DisplayHelper.print_table(facilities_table)

            choice = InputHelper.get_input_with_backspace(
                f"Select a facility (1-{len(facilities)}), b / q to return to menu, or Enter to exit",
                allow_empty=True,
            )

            if (
                choice is None
                or NavigationHelper.should_quit_to_menu(choice)
                or choice == ""
            ):
                break
            if NavigationHelper.can_go_back(choice):
                break

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(facilities):
                    current_facility = facilities[idx]
                    current_level = "facility"
                else:
                    DisplayHelper.print_error(
                        f"Invalid selection. Please enter 1-{len(facilities)}."
                    )
                    InputHelper.wait_for_continue()
            except ValueError:
                DisplayHelper.print_error("Invalid input. Please enter a number.")
                InputHelper.wait_for_continue()

        elif current_level == "facility":
            console.print(
                "\n[bold cyan]Navigation:[/bold cyan] [green]Installation[/green] > [yellow]Facility[/yellow]\n"
            )

            facility_type = settings.get_facility_type(
                current_facility.facility_type_key or 0
            )
            title = facility_type.title if facility_type else "Unknown Facility"

            DisplayHelper.print_panel(
                content=_format_facility(current_facility, settings),
                title=f"Facility: {title}",
            )

            facility_systems = systems_by_facility.get(current_facility.id, [])

            if not facility_systems:
                DisplayHelper.print_warning("This facility has no systems.")
                choice = InputHelper.get_input_with_backspace(
                    "Enter to return to facilities, or b / q to return to the menu",
                    allow_empty=True,
                )
                if choice is None or NavigationHelper.should_quit_to_menu(choice):
                    DisplayHelper.print_warning("Cancelled. Returning to menu.")
                    return
                current_level = "installation"
                current_facility = None
                continue

            # Show systems list
            systems_table = Table(
                title="Available Systems", show_header=True, header_style="bold cyan"
            )
            systems_table.add_column("#", style="cyan", width=4)
            systems_table.add_column("Title", style="green")
            systems_table.add_column("Key", style="yellow", justify="center")
            systems_table.add_column("CI", style="magenta", justify="center")
            systems_table.add_column("Age", style="blue", justify="center")
            systems_table.add_column("WOs", style="green", justify="center")

            for idx, system in enumerate(facility_systems, start=1):
                system_type = settings.get_system_type(system.system_type_key or 0)
                title = system_type.title if system_type else f"System {idx}"
                ci = (
                    f"{system.condition_index:.1f}" if system.condition_index else "N/A"
                )
                age = f"{system.age_years}y" if system.age_years else "N/A"
                wo_count = len(work_orders_by_system.get(system.id, []))
                systems_table.add_row(
                    str(idx), title, str(system.system_type_key), ci, age, str(wo_count)
                )

            DisplayHelper.print_table(systems_table)

            choice = InputHelper.get_input_with_backspace(
                f"Select a system (1-{len(facility_systems)}), b to go up, q to menu, or Enter to return",
                allow_empty=True,
            )

            if choice is None or NavigationHelper.should_quit_to_menu(choice):
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return

            if NavigationHelper.can_go_back(choice) or choice == "":
                current_level = "installation"
                current_facility = None
                continue

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(facility_systems):
                    current_system = facility_systems[idx]
                    current_level = "system"
                else:
                    DisplayHelper.print_error(
                        f"Invalid selection. Please enter 1-{len(facility_systems)}."
                    )
                    InputHelper.wait_for_continue()
            except ValueError:
                DisplayHelper.print_error("Invalid input. Please enter a number.")
                InputHelper.wait_for_continue()

        elif current_level == "system":
            console.print(
                "\n[bold cyan]Navigation:[/bold cyan] [green]Installation[/green] > "
                "[yellow]Facility[/yellow] > [magenta]System[/magenta]\n"
            )

            system_type = settings.get_system_type(current_system.system_type_key or 0)
            title = system_type.title if system_type else "Unknown System"

            DisplayHelper.print_panel(
                content=_format_system(current_system, settings),
                title=f"System: {title}",
            )
            related_work_orders = _work_orders_for_system(current_system, work_orders)

            if related_work_orders:
                wo_table = Table(
                    title="Work Orders", show_header=True, header_style="bold cyan"
                )
                wo_table.add_column("#", style="cyan", width=4)
                wo_table.add_column("Status", style="green")
                wo_table.add_column("Priority", style="yellow")
                wo_table.add_column("Trade", style="magenta")
                for idx, work_order in enumerate(related_work_orders, start=1):
                    wo_table.add_row(
                        str(idx),
                        work_order.status.value if work_order.status else "N/A",
                        work_order.priority.value if work_order.priority else "N/A",
                        work_order.trade.value if work_order.trade else "N/A",
                    )
                DisplayHelper.print_table(wo_table)

            console.print("\n")
            choice = InputHelper.get_input_with_backspace(
                "Work order number, Enter for systems, b for facilities, q for menu",
                allow_empty=True,
            )
            if choice is None or NavigationHelper.should_quit_to_menu(choice):
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return

            if NavigationHelper.can_go_back(choice):
                current_level = "facility"
                current_system = None
                continue
            if choice == "":
                current_level = "facility"
                current_system = None
                continue
            try:
                selection = int(choice) - 1
                if 0 <= selection < len(related_work_orders):
                    current_work_order = related_work_orders[selection]
                    current_level = "work_order"
                else:
                    DisplayHelper.print_error("Invalid work order selection.")
                    InputHelper.wait_for_continue()
            except ValueError:
                DisplayHelper.print_error("Invalid input. Please enter a number.")
                InputHelper.wait_for_continue()

        elif current_level == "work_order":
            if current_work_order is None:
                current_level = "system"
                continue
            console.print(
                "\n[bold cyan]Navigation:[/bold cyan] [green]Installation[/green] > "
                "[yellow]Facility[/yellow] > [magenta]System[/magenta] > [blue]Work Order[/blue]\n"
            )
            DisplayHelper.print_panel(
                content=_format_work_order(current_work_order),
                title=f"Work Order: {current_work_order.id}",
            )
            _ = InputHelper.get_input_with_backspace(
                "Enter for system, b for facilities, q for menu",
                allow_empty=True,
            )
            if _ is None or NavigationHelper.should_quit_to_menu(_):
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return

            if NavigationHelper.can_go_back(_):
                current_level = "facility"
                current_system = None
            else:
                current_level = "system"
            current_work_order = None


def handle_generate_data() -> None:
    """Generate simulated data with user prompts and export to file."""
    selections = {
        "file_name": None,
        "file_output": None,
        "output_directory": None,
        "generation_method": None,
        "target_count": None,
        "layout": None,
        "generate_metadata": None,
        "description": None,
    }

    defaults = {
        "file_name": "generated_data",
        "file_output": "csv",
        "output_directory": ".",
        "generation_method": "default",
        "target_count": None,
        "layout": "normalized",
        "generate_metadata": True,
        "description": "",
    }

    step = 0
    total_steps = 8

    while step < total_steps:
        DisplayHelper.clear_screen()
        _display_selection_summary(selections)

        if step == 0:  # File name
            current_value = selections["file_name"] or defaults["file_name"]
            NavigationHelper.show_help(
                "File Name",
                "Base name for the output file (without extension).",
                "generated_data, my_simulation, test_run_2024",
            )
            prompt = f"[{step + 1}/{total_steps}] Enter file name (current: {current_value}, b back / q cancel):"
            value = InputHelper.get_input_with_backspace(
                prompt, default=current_value, allow_empty=False
            )

            if NavigationHelper.should_quit_to_menu(
                value
            ) or NavigationHelper.can_go_back(value):
                return

            selections["file_name"] = value if value else defaults["file_name"]
            step += 1

        elif step == 1:  # File output format
            current_value = selections["file_output"] or defaults["file_output"]
            NavigationHelper.show_help(
                "Output Format",
                "File format for data export.\n• CSV: Comma-separated values\n• XLSX: Excel format with multiple sheets",
                "csv, xlsx",
            )
            prompt = f"[{step + 1}/{total_steps}] Enter format (csv/xlsx) (current: {current_value}, b back / q cancel):"
            value = InputHelper.get_input_with_backspace(
                prompt, default=current_value, allow_empty=False
            )

            if NavigationHelper.should_quit_to_menu(value):
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return
            if NavigationHelper.can_go_back(value):
                step -= 1
                continue

            value = value.lower().strip()
            if value and value not in ["csv", "xlsx"]:
                DisplayHelper.print_error("Invalid format. Must be csv or xlsx.")
                InputHelper.wait_for_continue()
                continue

            selections["file_output"] = value if value else defaults["file_output"]
            step += 1

        elif step == 2:  # Output directory
            current_value = (
                selections["output_directory"] or defaults["output_directory"]
            )
            NavigationHelper.show_help(
                "Output Directory",
                "Directory where output will be saved.",
                ". (current directory), ./output, /path/to/output",
            )
            prompt = f"[{step + 1}/{total_steps}] Enter output directory (current: {current_value}, b back / q cancel):"
            value = InputHelper.get_input_with_backspace(
                prompt, default=current_value, allow_empty=False
            )

            if NavigationHelper.should_quit_to_menu(value):
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return
            if NavigationHelper.can_go_back(value):
                step -= 1
                continue

            if value:
                try:
                    Path(value).mkdir(parents=True, exist_ok=True)
                    selections["output_directory"] = value
                except Exception as e:
                    DisplayHelper.print_error(f"Error with directory: {e}")
                    InputHelper.wait_for_continue()
                    continue
            else:
                selections["output_directory"] = defaults["output_directory"]

            step += 1

        elif step == 3:  # Generation method
            current_value = (
                selections["generation_method"] or defaults["generation_method"]
            )
            NavigationHelper.show_help(
                "Generation Method",
                "Method for generating simulated data.\n"
                "• default: One installation with random facilities\n"
                "• installations: Specific number of installations\n"
                "• facilities: Specific number of facilities\n"
                "Exports always include maintenance work orders (table/sheet or denormalized rows).",
                "default, installations, facilities",
            )
            prompt = f"[{step + 1}/{total_steps}] Method (installations/facilities/default) (current: {current_value}, b back / q cancel):"
            value = InputHelper.get_input_with_backspace(
                prompt, default=current_value, allow_empty=False
            )

            if NavigationHelper.should_quit_to_menu(value):
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return
            if NavigationHelper.can_go_back(value):
                step -= 1
                continue

            value = value.lower().strip()
            if value and value not in ["installations", "facilities", "default"]:
                DisplayHelper.print_error(
                    "Invalid method. Must be installations, facilities, or default."
                )
                InputHelper.wait_for_continue()
                continue

            selections["generation_method"] = (
                value if value else defaults["generation_method"]
            )

            if selections["generation_method"] in ["installations", "facilities"]:
                step += 1
            else:
                selections["target_count"] = None
                step += 2  # Skip count step

        elif step == 4:  # Target count
            if selections["generation_method"] not in ["installations", "facilities"]:
                step += 1
                continue

            current_value = (
                str(selections["target_count"]) if selections["target_count"] else "10"
            )
            method_name = selections["generation_method"]
            NavigationHelper.show_help(
                f"Target Count ({method_name.title()})",
                f"Number of {method_name} to generate.",
                "10, 25, 100",
            )
            prompt = f"[{step + 1}/{total_steps}] Enter number of {method_name} (current: {current_value}, b back / q cancel):"
            value = InputHelper.ask_number(
                prompt,
                min_value=1,
                default=(
                    10 if not selections["target_count"] else selections["target_count"]
                ),
                allow_back=True,
                allow_quit_flow=True,
            )

            if value is InputHelper.QUIT_TO_MENU:
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return
            if value is None:
                step -= 1
                continue

            selections["target_count"] = value
            step += 1

        elif step == 5:  # Output layout
            current_value = selections["layout"] or defaults["layout"]
            NavigationHelper.show_help(
                "Output Layout",
                "Structure of the exported data.\n"
                "• normalized: Separate tables including work orders (recommended)\n"
                "• denormalized: Single flattened table (one row per work order)",
                "normalized (recommended), denormalized",
            )
            prompt = f"[{step + 1}/{total_steps}] Layout (normalized/denormalized) (current: {current_value}, b back / q cancel):"
            value = InputHelper.ask_choice(
                prompt,
                choices=["normalized", "denormalized"],
                default=current_value,
                allow_back=True,
                allow_quit_flow=True,
            )

            if value is InputHelper.QUIT_TO_MENU:
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return
            if value is None:
                step -= 1
                continue

            selections["layout"] = value if value else defaults["layout"]
            step += 1

        elif step == 6:  # Generate metadata
            current_value = (
                "yes"
                if (selections["generate_metadata"] or defaults["generate_metadata"])
                else "no"
            )
            NavigationHelper.show_help(
                "Generate Metadata",
                "Whether to generate metadata output (JSON sidecar for CSV, metadata sheet for Excel).",
                "yes (recommended), no",
            )
            prompt = f"[{step + 1}/{total_steps}] Generate metadata? (yes/no) (current: {current_value}, b back / q cancel):"
            value = InputHelper.ask_yes_no(
                prompt, default=True, allow_back=True, allow_quit_flow=True
            )

            if value is InputHelper.QUIT_TO_MENU:
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return
            if value is None:
                step -= 1
                continue

            selections["generate_metadata"] = value
            step += 1

        elif step == 7:  # Description
            current_value = selections["description"] or defaults["description"]
            NavigationHelper.show_help(
                "Dataset Description",
                "Optional description for this dataset.",
                "Test dataset, Production run, Research data",
            )
            prompt = f"[{step + 1}/{total_steps}] Description (optional, current: '{current_value}', b back / q cancel):"
            value = InputHelper.get_input_with_backspace(
                prompt, default=current_value, allow_empty=False
            )

            if NavigationHelper.should_quit_to_menu(value):
                DisplayHelper.print_warning("Cancelled. Returning to menu.")
                return
            if NavigationHelper.can_go_back(value):
                step -= 1
                continue

            selections["description"] = value if value else defaults["description"]
            step += 1

    # Final confirmation
    DisplayHelper.clear_screen()
    _display_selection_summary(selections)

    if not InputHelper.confirm("\nProceed with data generation?", default=True):
        DisplayHelper.print_warning("Generation cancelled.")
        return

    # Generate and export data
    try:
        DisplayHelper.print_info("Generating data...", title="MIDAS")

        settings = _get_settings()

        exporter = DataExporter(
            file_name=selections["file_name"],
            output_format=selections["file_output"],
            output_directory=selections["output_directory"],
            layout=selections["layout"],
            generate_metadata=selections["generate_metadata"],
            description=selections["description"],
            settings=settings,
        )

        file_path = exporter.generate_and_export(
            method=selections["generation_method"],
            target_count=selections["target_count"],
        )

        DisplayHelper.print_success(f"Data successfully exported to: {file_path}")
        DisplayHelper.print_success(
            f"All output files in: {exporter.config.output_directory}"
        )
        if selections["generate_metadata"]:
            if selections["file_output"] == "csv":
                DisplayHelper.print_success(f"Metadata file: {exporter.metadata_path}")
            else:
                DisplayHelper.print_success(
                    f"Metadata sheet: {settings.output.excel_sheet_metadata} (in {file_path.name})"
                )
        InputHelper.wait_for_continue()

    except ValueError as e:
        DisplayHelper.print_error(f"Invalid configuration: {e}", title="Error")
        logger.exception("Error during data generation")
        InputHelper.wait_for_continue()
    except Exception as e:
        DisplayHelper.print_error(f"Error generating data: {e}", title="Error")
        logger.exception("Error during data generation")
        InputHelper.wait_for_continue()


def handle_view_facility_and_system() -> None:
    """Generate a facility and allow user to select a system to view."""
    settings = _get_settings()
    generator = DataGenerator(settings=settings)

    result = generator.generate_installation()
    facilities = result.facilities
    systems = result.systems
    flat_work_orders = result.work_orders

    if not facilities:
        DisplayHelper.print_warning("No facilities generated.")
        return

    facility = facilities[0]
    facility_systems = [s for s in systems if s.facility_id == facility.id]

    DisplayHelper.print_panel(
        content=_format_facility(facility, settings), title="Simulated Facility Data"
    )

    if not facility_systems:
        DisplayHelper.print_warning("This facility has no systems to display.")
        return

    systems_table = Table(
        title="Available Systems", show_header=True, header_style="bold cyan"
    )
    systems_table.add_column("#", style="cyan", width=4)
    systems_table.add_column("Title", style="green")
    systems_table.add_column("Key", style="yellow", justify="center")
    systems_table.add_column("WOs", style="green", justify="center")

    for idx, system in enumerate(facility_systems, start=1):
        system_type = settings.get_system_type(system.system_type_key or 0)
        title = system_type.title if system_type else f"System {idx}"
        wo_count = len(_work_orders_for_system(system, flat_work_orders))
        systems_table.add_row(
            str(idx), title, str(system.system_type_key), str(wo_count)
        )

    DisplayHelper.print_table(systems_table)

    choice = InputHelper.ask_choice(
        f"Select a system (1-{len(facility_systems)}), b / q to return to menu",
        choices=[str(i) for i in range(1, len(facility_systems) + 1)],
        default="1",
        allow_back=True,
        allow_quit_flow=True,
    )
    if choice is None or choice is InputHelper.QUIT_TO_MENU:
        DisplayHelper.print_warning("Cancelled. Returning to menu.")
        return

    try:
        selected_system = facility_systems[int(choice) - 1]
    except (ValueError, IndexError) as e:
        DisplayHelper.print_error(f"Invalid selection: {e}")
        InputHelper.wait_for_continue()
        return

    DisplayHelper.print_panel(
        content=_format_system(selected_system, settings), title="System Details"
    )

    related = _work_orders_for_system(selected_system, flat_work_orders)
    if not related:
        DisplayHelper.print_info("No work orders for this system.", title="Work Orders")
        InputHelper.wait_for_continue()
        return

    while True:
        wo_table = Table(
            title="Work Orders", show_header=True, header_style="bold cyan"
        )
        wo_table.add_column("#", style="cyan", width=4)
        wo_table.add_column("Status", style="green")
        wo_table.add_column("Priority", style="yellow")
        wo_table.add_column("Trade", style="magenta")
        for idx, work_order in enumerate(related, start=1):
            wo_table.add_row(
                str(idx),
                work_order.status.value if work_order.status else "N/A",
                work_order.priority.value if work_order.priority else "N/A",
                work_order.trade.value if work_order.trade else "N/A",
            )
        DisplayHelper.print_table(wo_table)

        wo_choice = InputHelper.get_input_with_backspace(
            f"Work order number (1-{len(related)}) for detail, Enter to leave, b / q to menu",
            allow_empty=True,
        )
        if (
            wo_choice is None
            or NavigationHelper.should_quit_to_menu(wo_choice)
            or NavigationHelper.can_go_back(wo_choice)
            or wo_choice == ""
        ):
            break
        try:
            sel = int(wo_choice) - 1
            if 0 <= sel < len(related):
                DisplayHelper.print_panel(
                    content=_format_work_order(related[sel]),
                    title=f"Work Order: {related[sel].id}",
                )
                InputHelper.wait_for_continue()
            else:
                DisplayHelper.print_error(
                    f"Invalid selection. Please enter 1-{len(related)}."
                )
                InputHelper.wait_for_continue()
        except ValueError:
            DisplayHelper.print_error("Invalid input. Please enter a number.")
            InputHelper.wait_for_continue()


def handle_view_installation_interactive() -> None:
    """Generate an installation and allow interactive navigation."""
    # This is now handled by handle_view_simulated_data_examples
    handle_view_simulated_data_examples()


def handle_quick_generate() -> None:
    """Quick generate data and display summary statistics."""
    DisplayHelper.clear_screen()

    console.print("\n[bold cyan]Quick Generate - Summary Statistics[/bold cyan]\n")
    console.print("Generating sample data with default settings...\n")

    settings = _get_settings()
    generator = DataGenerator(settings=settings)

    # Generate data
    result = generator.generate_installation()
    installation = result.installations[0]
    facilities = result.facilities
    systems = result.systems
    work_orders = result.work_orders

    # Calculate statistics
    facility_cis = [
        f.condition_index for f in facilities if f.condition_index is not None
    ]
    facility_ages = [f.age_years for f in facilities if f.age_years is not None]
    system_cis = [s.condition_index for s in systems if s.condition_index is not None]
    system_ages = [s.age_years for s in systems if s.age_years is not None]

    # Create summary table
    summary_table = Table(
        title="Generation Summary",
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
    )
    summary_table.add_column("Metric", style="cyan", width=30)
    summary_table.add_column("Value", style="green", justify="right", width=20)

    summary_table.add_row("Installation ID", installation.id[:20] + "...")
    summary_table.add_row("Installation Title", installation.title or "N/A")
    summary_table.add_section()
    summary_table.add_row("Total Facilities", str(len(facilities)))
    summary_table.add_row("Total Systems", str(len(systems)))
    summary_table.add_row("Total Work Orders", str(len(work_orders)))
    summary_table.add_row(
        "Avg Systems per Facility", f"{len(systems) / max(1, len(facilities)):.1f}"
    )
    summary_table.add_row(
        "Avg Work Orders per System", f"{len(work_orders) / max(1, len(systems)):.1f}"
    )

    DisplayHelper.print_table(summary_table)

    # Condition Index Distribution
    if facility_cis:
        ci_table = Table(
            title="Condition Index Distribution",
            show_header=True,
            header_style="bold cyan",
        )
        ci_table.add_column("Entity", style="cyan", width=15)
        ci_table.add_column("Min", justify="right", width=10)
        ci_table.add_column("Max", justify="right", width=10)
        ci_table.add_column("Mean", justify="right", width=10)
        ci_table.add_column("Count", justify="right", width=10)

        ci_table.add_row(
            "Facilities",
            f"{min(facility_cis):.1f}",
            f"{max(facility_cis):.1f}",
            f"{sum(facility_cis) / len(facility_cis):.1f}",
            str(len(facility_cis)),
        )

        if system_cis:
            ci_table.add_row(
                "Systems",
                f"{min(system_cis):.1f}",
                f"{max(system_cis):.1f}",
                f"{sum(system_cis) / len(system_cis):.1f}",
                str(len(system_cis)),
            )

        DisplayHelper.print_table(ci_table)

    # Age Distribution
    if facility_ages:
        age_table = Table(
            title="Age Distribution (Years)",
            show_header=True,
            header_style="bold cyan",
        )
        age_table.add_column("Entity", style="cyan", width=15)
        age_table.add_column("Min", justify="right", width=10)
        age_table.add_column("Max", justify="right", width=10)
        age_table.add_column("Mean", justify="right", width=10)

        age_table.add_row(
            "Facilities",
            str(min(facility_ages)),
            str(max(facility_ages)),
            f"{sum(facility_ages) / len(facility_ages):.1f}",
        )

        if system_ages:
            age_table.add_row(
                "Systems",
                str(min(system_ages)),
                str(max(system_ages)),
                f"{sum(system_ages) / len(system_ages):.1f}",
            )

        DisplayHelper.print_table(age_table)

    if work_orders:
        status_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}
        for work_order in work_orders:
            status_key = work_order.status.value if work_order.status else "Unknown"
            priority_key = (
                work_order.priority.value if work_order.priority else "Unknown"
            )
            status_counts[status_key] = status_counts.get(status_key, 0) + 1
            priority_counts[priority_key] = priority_counts.get(priority_key, 0) + 1

        wo_table = Table(
            title="Work Order Breakdown",
            show_header=True,
            header_style="bold cyan",
        )
        wo_table.add_column("Type", style="cyan", width=12)
        wo_table.add_column("Value", style="green", width=18)
        wo_table.add_column("Count", justify="right", width=10)
        wo_table.add_column("Percent", justify="right", width=10)

        total_wo = len(work_orders)
        for value, count in sorted(status_counts.items(), key=lambda item: item[0]):
            wo_table.add_row(
                "Status", value, str(count), f"{(count / total_wo) * 100:.1f}%"
            )
        for value, count in sorted(priority_counts.items(), key=lambda item: item[0]):
            wo_table.add_row(
                "Priority", value, str(count), f"{(count / total_wo) * 100:.1f}%"
            )

        DisplayHelper.print_table(wo_table)

    # Condition breakdown
    console.print("[bold]Condition Breakdown (Facilities):[/bold]")

    if facility_cis:
        good = sum(1 for ci in facility_cis if ci >= 70)
        fair = sum(1 for ci in facility_cis if 50 <= ci < 70)
        poor = sum(1 for ci in facility_cis if 25 <= ci < 50)
        critical = sum(1 for ci in facility_cis if ci < 25)
        total = len(facility_cis)

        console.print(
            f"  [green]Good (CI >= 70):[/green]     {good:3} ({good / total * 100:5.1f}%)"
        )
        console.print(
            f"  [yellow]Fair (50-69):[/yellow]        {fair:3} ({fair / total * 100:5.1f}%)"
        )
        console.print(
            f"  [orange3]Poor (25-49):[/orange3]        {poor:3} ({poor / total * 100:5.1f}%)"
        )
        console.print(
            f"  [red]Critical (< 25):[/red]     {critical:3} ({critical / total * 100:5.1f}%)"
        )

    console.print("\n[dim]Enter to generate again · b or q to return to menu[/dim]")

    choice = InputHelper.get_input_with_backspace("", allow_empty=True)
    if (
        choice is None
        or NavigationHelper.should_quit_to_menu(choice)
        or NavigationHelper.can_go_back(choice)
    ):
        return
    else:
        # Generate again
        handle_quick_generate()
