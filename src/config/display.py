"""Display helpers for rendering MidasSettings and MidasConfigData summaries."""

from __future__ import annotations

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

from .midas_config_data import MidasConfigData
from .midas_settings import MidasSettings
from .setting_state import (
    DistributionSettingState,
    FloatSettingState,
    IntegerSettingState,
    RangeSettingState,
    StringSettingState,
)


def create_facility_types_table(config_data: MidasConfigData | None = None) -> Table:
    """Rich table of loaded facility types (or empty-state row)."""
    data = config_data or MidasConfigData()
    facility_types = list(data.facility_types.values())

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


def create_system_types_table(config_data: MidasConfigData | None = None) -> Table:
    """Rich table of loaded system types (or empty-state row)."""
    data = config_data or MidasConfigData()
    system_types = list(data.system_types.values())

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


def create_installation_locations_table(
    config_data: MidasConfigData | None = None,
) -> Table:
    """Rich table of installation location reference rows (or empty-state row)."""
    data = config_data or MidasConfigData()
    locations = data.installation_locations

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

    shown = ", ".join(str(k) for k in facility_keys[:5])
    return f"{shown}... (+{len(facility_keys) - 5} more)"


def create_config_values_panel(settings: MidasSettings | None = None) -> Panel:
    """Panel grouping all configurable setting values from MidasSettings."""
    cfg = settings or MidasSettings()

    scalar_table = Table(show_header=False, box=None, padding=(0, 2))
    scalar_table.add_column("Setting", style="cyan", width=55)
    scalar_table.add_column("Value", style="white")

    distribution_blocks: list[tuple[str, Table]] = []

    for name, state in cfg.iter_states():
        if isinstance(state, DistributionSettingState):
            distribution_blocks.append(
                (state.label or name, _create_count_distribution_table(state.value))
            )
            continue

        if isinstance(state, RangeSettingState):
            low, high = state.value
            value_str = str(low) if low == high else f"{low}-{high}"
        elif isinstance(state, FloatSettingState):
            value_str = f"{state.value:g}"
        elif isinstance(state, IntegerSettingState):
            value_str = str(state.value)
        elif isinstance(state, StringSettingState):
            value_str = f'"{state.value}"'
        else:
            value_str = str(getattr(state, "value", ""))

        scalar_table.add_row(state.label or name, value_str)

    content_items: list = [
        Text("MIDAS SETTINGS", style="bold cyan"),
        scalar_table,
    ]
    if distribution_blocks:
        content_items.append(Text("\nDATA GENERATION DISTRIBUTIONS", style="bold cyan"))
        for label, table in distribution_blocks:
            content_items.append(Text(f"\n{label}:", style="bold yellow"))
            content_items.append(table)

    return Panel(
        Group(*content_items),
        title="MIDAS Configuration Values Summary",
        border_style="green",
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
    """Create a table showing a generic distribution's parameters or segments."""
    if distribution is None:
        return _create_parameter_table([("Status", "Not configured")])

    if isinstance(distribution, WeightedProbabilityDistribution):
        return _create_distribution_table(distribution, "Sampled Value")

    rows: list[tuple[str, str]] = [("Type", type(distribution).__name__)]
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


def create_settings_summary_text(
    settings: MidasSettings | None = None,
    config_data: MidasConfigData | None = None,
) -> str:
    """Short newline-separated counts and key simulation/degradation scalars."""
    cfg = settings or MidasSettings()
    data = config_data or MidasConfigData()

    facilities_range = cfg.get_value("facilities_per_installation")
    lines = [
        f"Facility Types Loaded: {len(data.facility_types)}",
        f"System Types Loaded: {len(data.system_types)}",
        f"Degradation Threshold: {cfg.get_value('condition_index_degraded_threshold')}",
        f"Facilities per Installation: {facilities_range[0]}-{facilities_range[1]}",
        f"Max Vertical Depth: {cfg.get_value('maximum_vertical_dependency_depth')}",
    ]
    return "\n".join(lines)
