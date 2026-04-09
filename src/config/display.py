"""Display utilities for configuration visualization.

Provides functions to create Rich tables and panels for displaying
configuration values, facility types, system types, and distributions.
"""

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.models.distributions import (
    BathtubCurveDistribution,
    EventRateDistribution,
    NormalCurveDistribution,
    PiecewiseCurveDistribution,
    WeightedProbabilityDistribution,
)

from .settings import MIDASSettings


def create_facility_types_table(settings: MIDASSettings) -> Table:
    """Rich table of loaded facility types from ``settings`` (or empty-state row)."""
    facility_types = list(settings.facility_types.values())

    table = Table(
        title=f"Loaded Facility Types: {len(facility_types)} total",
        show_header=True,
        header_style="bold cyan",
        border_style="green",
    )

    if not facility_types:
        table.add_column("Status", style="yellow")
        table.add_row("No Facility Types are currently loaded")
        return table

    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="white")
    table.add_column("Life Expectancy", style="magenta", justify="right")
    table.add_column("Mission Criticality", style="yellow", justify="center")

    for facility in sorted(facility_types, key=lambda f: f.key):
        table.add_row(
            str(facility.key),
            str(facility.title),
            str(facility.life_expectancy),
            str(facility.mission_criticality),
        )

    return table


def create_system_types_table(settings: MIDASSettings) -> Table:
    """Rich table of loaded system types from ``settings`` (or empty-state row)."""
    system_types = list(settings.system_types.values())

    table = Table(
        title=f"Loaded System Types: {len(system_types)} total",
        show_header=True,
        header_style="bold cyan",
        border_style="green",
    )

    if not system_types:
        table.add_column("Status", style="yellow")
        table.add_row("No System Types are currently loaded")
        return table

    table.add_column("Key", style="cyan", justify="right")
    table.add_column("Title", style="white")
    table.add_column("Life Expectancy", style="magenta", justify="right")
    table.add_column("Facility Keys", style="blue")

    for system in sorted(system_types, key=lambda s: s.key):
        facility_keys_str = _format_facility_keys(system.facility_keys)
        table.add_row(
            str(system.key),
            str(system.title),
            str(system.life_expectancy),
            facility_keys_str,
        )

    return table


def create_installation_locations_table(settings: MIDASSettings) -> Table:
    """Rich table of installation location reference rows (or empty-state row)."""
    locations = settings.installation_locations

    table = Table(
        title=f"Loaded Installation Locations: {len(locations)} total",
        show_header=True,
        header_style="bold cyan",
        border_style="green",
    )

    if not locations:
        table.add_column("Status", style="yellow")
        table.add_row("No Installation Locations are currently loaded")
        return table

    table.add_column("Title", style="white")
    table.add_column("Location", style="cyan")
    table.add_column("Region", style="magenta")
    table.add_column("Coordinates", style="blue")

    for loc in sorted(locations, key=lambda location: location.title):
        table.add_row(
            str(loc.title),
            str(loc.location),
            str(loc.region),
            str(loc.coordinates),
        )

    return table


def _format_facility_keys(facility_keys: tuple[int, ...]) -> str:
    """Comma-separated keys, truncated with a count suffix when long."""
    if not facility_keys:
        return "[dim]None[/dim]"

    if len(facility_keys) <= 5:
        return ", ".join(str(k) for k in facility_keys)

    # Truncate if too many
    shown = ", ".join(str(k) for k in facility_keys[:5])
    return f"{shown}... (+{len(facility_keys) - 5} more)"


def create_config_values_panel(settings: MIDASSettings) -> Panel:
    """Panel grouping degradation, simulation, output, and distribution tables."""
    # --- Degradation Settings ---
    deg_table = Table(show_header=False, box=None, padding=(0, 2))
    deg_table.add_column("Setting", style="cyan", width=45)
    deg_table.add_column("Value", style="white")

    deg = settings.degradation
    deg_table.add_row(
        "Condition Index Degraded Threshold",
        str(deg.condition_index_degraded_threshold),
    )
    deg_table.add_row("Resiliency Grade Threshold", str(deg.resiliency_grade_threshold))
    deg_table.add_row("Initial Condition Index", str(deg.initial_condition_index))
    deg_table.add_row(
        "Maximum Time Series Years History", str(deg.max_time_series_years)
    )

    # --- Simulation Settings ---
    sim_table = Table(show_header=False, box=None, padding=(0, 2))
    sim_table.add_column("Setting", style="cyan", width=45)
    sim_table.add_column("Value", style="white")

    sim = settings.simulation
    low, high = sim.facilities_per_installation
    facilities_str = str(low) if low == high else f"{low}-{high}"
    sim_table.add_row("Facilities Per Installation", facilities_str)

    low, high = sim.dependency_chain_group_range
    dep_chain_str = str(low) if low == high else f"{low}-{high}"
    sim_table.add_row("Dependency Chain Group Range", dep_chain_str)
    sim_table.add_row("Maximum Vertical Depth", str(sim.max_vertical_depth))

    sim_table.add_row("Maximum System Age", str(sim.maximum_system_age))
    sim_table.add_row("Maximum Facility Age", str(sim.maximum_facility_age))
    sim_table.add_row(
        "Facility Condition Randomly Degrades Chance",
        f"{sim.facility_condition_randomly_degrades_chance}%",
    )

    # --- Output Settings ---
    out_table = Table(show_header=False, box=None, padding=(0, 2))
    out_table.add_column("Setting", style="cyan", width=45)
    out_table.add_column("Value", style="white")

    out = settings.output
    out_table.add_row("Excel Sheet Main Name", out.excel_sheet_main)
    out_table.add_row(
        "Excel Sheet Facility Time Series Name", out.excel_sheet_facility_ts
    )
    out_table.add_row("Excel Sheet System Time Series Name", out.excel_sheet_system_ts)
    out_table.add_row("Excel Sheet Metadata Name", out.excel_sheet_metadata)
    out_table.add_row("Excel Sheet Work Orders Name", out.excel_sheet_work_orders)
    out_table.add_row("Metadata File Suffix", out.metadata_file_suffix)
    out_table.add_row("CSV Table Separator", f'"{out.csv_table_separator}"')

    # --- Distributions ---
    dist = settings.distributions

    dist_table_ci = _create_distribution_table(dist.condition_index, "Value Range")
    dist_table_age = _create_distribution_table(dist.age, "Value Range")
    dist_table_grade = _create_distribution_table(dist.grade, "Grade", prefix="Grade ")
    dist_table_wo_count = _create_count_distribution_table(dist.work_order_count)
    dist_table_wo_status = _create_distribution_table(dist.work_order_status, "Status")
    dist_table_wo_priority = _create_distribution_table(
        dist.work_order_priority, "Priority"
    )
    dist_table_wo_org = _create_distribution_table(
        dist.work_order_requesting_organization, "Organization"
    )

    content = Group(
        Text("DEGRADATION SETTINGS", style="bold cyan"),
        deg_table,
        Text("\nSIMULATION SETTINGS", style="bold cyan"),
        sim_table,
        Text("\nOUTPUT SETTINGS", style="bold cyan"),
        out_table,
        Text("\nSIMULATION PROBABILITY DISTRIBUTIONS", style="bold cyan"),
        Text("\nSimulated Condition Index Distribution:", style="bold yellow"),
        dist_table_ci,
        Text("\nSimulated Age Distribution:", style="bold yellow"),
        dist_table_age,
        Text("\nSimulated Grade Distribution:", style="bold yellow"),
        dist_table_grade,
        Text("\nSimulated Work Order Count Distribution:", style="bold yellow"),
        dist_table_wo_count,
        Text("\nSimulated Work Order Status Distribution:", style="bold yellow"),
        dist_table_wo_status,
        Text("\nSimulated Work Order Priority Distribution:", style="bold yellow"),
        dist_table_wo_priority,
        Text(
            "\nSimulated Work Order Requesting Organization Distribution:",
            style="bold yellow",
        ),
        dist_table_wo_org,
    )

    return Panel(
        content, title="MIDAS Configuration Values Summary", border_style="green"
    )


def _create_parameter_table(rows: list[tuple[str, str]]) -> Table:
    """Create a two-column parameter table used for non-segment distributions."""
    table = Table(
        show_header=True, header_style="bold yellow", box=None, padding=(0, 2)
    )
    table.add_column("Parameter", style="cyan", width=25)
    table.add_column("Value", style="white", justify="right")

    for name, value in rows:
        table.add_row(name, value)
    return table


def _create_count_distribution_table(distribution) -> Table:
    """Create a table showing the configured work-order count distribution."""
    if distribution is None:
        return _create_parameter_table([("Status", "Not configured")])

    if isinstance(distribution, WeightedProbabilityDistribution):
        return _create_distribution_table(distribution, "Sampled Value")

    rows = [("Type", type(distribution).__name__)]
    if isinstance(distribution, BathtubCurveDistribution):
        rows.extend(
            [
                ("Early Peak Rate", str(distribution.early_peak_rate)),
                ("Useful Life Rate", str(distribution.useful_life_rate)),
                ("Wearout Peak Rate", str(distribution.wearout_peak_rate)),
                ("Early End Ratio", str(distribution.early_end_ratio)),
                ("Wearout Start Ratio", str(distribution.wearout_start_ratio)),
                ("Max Ratio", str(distribution.max_ratio)),
            ]
        )
        return _create_parameter_table(rows)

    if isinstance(distribution, NormalCurveDistribution):
        rows.extend(
            [
                ("Baseline Rate", str(distribution.baseline_rate)),
                ("Amplitude", str(distribution.amplitude)),
                ("Mean", str(distribution.mean)),
                ("Stddev", str(distribution.stddev)),
            ]
        )
        return _create_parameter_table(rows)

    if isinstance(distribution, PiecewiseCurveDistribution):
        rows.extend(
            (
                f"Point {index}",
                f"age_ratio={age_ratio}, rate={rate}",
            )
            for index, (age_ratio, rate) in enumerate(distribution.points, start=1)
        )
        return _create_parameter_table(rows)

    if isinstance(distribution, EventRateDistribution):
        rows.extend(
            (
                attribute_name.replace("_", " ").title(),
                str(attribute_value),
            )
            for attribute_name, attribute_value in vars(distribution).items()
        )
        return _create_parameter_table(rows)

    rows.append(("Value", str(distribution)))
    return _create_parameter_table(rows)


def _create_distribution_table(
    distribution: WeightedProbabilityDistribution | None,
    value_column_name: str,
    prefix: str = "",
) -> Table:
    """Two-column percent/value table; shows *Not configured* when ``distribution`` is None."""
    table = Table(
        show_header=True, header_style="bold yellow", box=None, padding=(0, 2)
    )
    table.add_column("Percentage", style="magenta", justify="right", width=12)
    table.add_column(value_column_name, style="white")

    if distribution is None:
        table.add_row("[dim]Not configured[/dim]", "")
        return table

    total_pct = distribution.get_total_percentage()
    for segment in distribution.segments:
        table.add_row(f"{segment.weight_percent}%", f"{prefix}{segment.value}")

    if total_pct != 100:
        table.add_row(f"[yellow](Total: {total_pct}%)[/yellow]", "")

    return table


def create_settings_summary_text(settings: MIDASSettings) -> str:
    """Short newline-separated counts and key simulation/degradation scalars."""
    lines = [
        f"Facility Types Loaded: {len(settings.facility_types)}",
        f"System Types Loaded: {len(settings.system_types)}",
        f"Degradation Threshold: {settings.degradation.condition_index_degraded_threshold}",
        f"Facilities per Installation: {settings.simulation.facilities_per_installation}",
        f"Max Vertical Depth: {settings.simulation.max_vertical_depth}",
    ]
    return "\n".join(lines)
