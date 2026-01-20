"""Display utilities for configuration visualization.

Provides functions to create Rich tables and panels for displaying
configuration values, facility types, system types, and distributions.
"""

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .settings import MIDASSettings


def create_facility_types_table(settings: MIDASSettings) -> Table:
    """Create a Rich Table showing all loaded facility types.
    
    Args:
        settings: The application settings.
        
    Returns:
        Rich Table with facility type information.
    """
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
    """Create a Rich Table showing all loaded system types.
    
    Args:
        settings: The application settings.
        
    Returns:
        Rich Table with system type information.
    """
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


def _format_facility_keys(facility_keys: tuple[int, ...]) -> str:
    """Format facility keys for display.
    
    Args:
        facility_keys: Tuple of facility key integers.
        
    Returns:
        Formatted string representation.
    """
    if not facility_keys:
        return "[dim]None[/dim]"
    
    if len(facility_keys) <= 5:
        return ", ".join(str(k) for k in facility_keys)
    
    # Truncate if too many
    shown = ", ".join(str(k) for k in facility_keys[:5])
    return f"{shown}... (+{len(facility_keys) - 5} more)"


def create_config_values_panel(settings: MIDASSettings) -> Panel:
    """Create a Rich Panel showing all configuration values and distributions.
    
    Args:
        settings: The application settings.
        
    Returns:
        Rich Panel with configuration summary.
    """
    # Build config state values table
    config_table = Table(show_header=False, box=None, padding=(0, 2))
    config_table.add_column("Setting", style="cyan", width=40)
    config_table.add_column("Value", style="white")
    
    # Simulation settings
    sim = settings.simulation
    low, high = sim.facilities_per_installation
    facilities_str = str(low) if low == high else f"{low}-{high}"
    config_table.add_row("Facilities Per Installation", facilities_str)
    
    low, high = sim.dependency_chain_group_range
    dep_chain_str = str(low) if low == high else f"{low}-{high}"
    config_table.add_row("Dependency Chain Group Range", dep_chain_str)
    
    # Degradation settings
    deg = settings.degradation
    config_table.add_row("Condition Index Degraded Threshold", str(deg.condition_index_degraded_threshold))
    config_table.add_row("Resiliency Grade Threshold", str(deg.resiliency_grade_threshold))
    
    # More simulation settings
    config_table.add_row("Maximum System Age", str(sim.maximum_system_age))
    config_table.add_row("Maximum Facility Age", str(sim.maximum_facility_age))
    config_table.add_row(
        "Facility Condition Randomly Degrades Chance",
        f"{sim.facility_condition_randomly_degrades_chance}%"
    )
    
    # Build distributions section
    dist = settings.distributions
    
    # Condition Index Distribution
    dist_table_ci = _create_distribution_table(
        dist.condition_index,
        "Value Range"
    )
    
    # Age Distribution
    dist_table_age = _create_distribution_table(
        dist.age,
        "Value Range"
    )
    
    # Grade Distribution
    dist_table_grade = _create_distribution_table(
        dist.grade,
        "Grade",
        prefix="Grade "
    )
    
    # Build the main content
    content = Group(
        Text("CONFIG STATE VALUES", style="bold cyan"),
        config_table,
        Text("\nSIMULATION PROBABILITY DISTRIBUTIONS", style="bold cyan"),
        Text("\nSimulated Condition Index Distribution:", style="bold yellow"),
        dist_table_ci,
        Text("\nSimulated Age Distribution:", style="bold yellow"),
        dist_table_age,
        Text("\nSimulated Grade Distribution:", style="bold yellow"),
        dist_table_grade,
    )
    
    return Panel(content, title="MIDAS Configuration Values Summary", border_style="green")


def _create_distribution_table(
    distribution,
    value_column_name: str,
    prefix: str = ""
) -> Table:
    """Create a table showing a probability distribution.
    
    Args:
        distribution: ProbabilityDistribution instance.
        value_column_name: Name for the value column.
        prefix: Optional prefix for value display.
        
    Returns:
        Rich Table showing the distribution.
    """
    table = Table(show_header=True, header_style="bold yellow", box=None, padding=(0, 2))
    table.add_column("Percentage", style="magenta", justify="right", width=12)
    table.add_column(value_column_name, style="white")
    
    if distribution is None:
        table.add_row("[dim]Not configured[/dim]", "")
        return table
    
    total_pct = distribution.get_total_percentage()
    for segment in distribution.segments:
        table.add_row(f"{segment._percentage}%", f"{prefix}{segment.value}")
    
    if total_pct != 100:
        table.add_row(f"[yellow](Total: {total_pct}%)[/yellow]", "")
    
    return table


def create_settings_summary_text(settings: MIDASSettings) -> str:
    """Create a simple text summary of settings.
    
    Args:
        settings: The application settings.
        
    Returns:
        String summary of key settings.
    """
    lines = [
        f"Facility Types Loaded: {len(settings.facility_types)}",
        f"System Types Loaded: {len(settings.system_types)}",
        f"Degradation Threshold: {settings.degradation.condition_index_degraded_threshold}",
        f"Facilities per Installation: {settings.simulation.facilities_per_installation}",
    ]
    return "\n".join(lines)
