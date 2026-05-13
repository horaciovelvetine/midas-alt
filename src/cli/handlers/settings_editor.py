"""Interactive editors for ``MidasSettings`` values backed by ``SettingState``.

Provides one reusable entry point (:func:`run_settings_editor`) plus per-type
editor helpers used both by the configuration menu and the simulation shell.
All input flows through :class:`InputHelper` so callers can suspend other
terminal modes (e.g. the live shell) before invoking the editor.
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.cli.utils import DisplayHelper, InputHelper
from src.config import MidasSettings
from src.config.display import _create_count_distribution_table
from src.config.setting_state import (
    BooleanMappingSettingState,
    DistributionSettingState,
    FloatSettingState,
    IntegerSettingState,
    MappingSettingState,
    RangeSettingState,
    SettingState,
    StringSettingState,
)
from src.models.distributions import (
    BathtubCurveDistribution,
    DistributionBase,
    EventRateDistribution,
    NormalCurveDistribution,
    PiecewiseCurveDistribution,
    WeightedProbabilityDistribution,
    WeightedProbabilitySegment,
)

logger = logging.getLogger(__name__)
console = Console()


# Section label per setting key. Anything not listed falls under "Other".
_SECTION_BY_NAME: dict[str, str] = {
    "condition_index_degraded_threshold": "Degradation",
    "resiliency_grade_rating_threshold": "Degradation",
    "initial_condition_index_default": "Degradation",
    "system_degradation_state_rate_multipliers": "Degradation",
    "random_system_degradation_chance": "Degradation",
    "random_system_degradation_ci_drop": "Degradation",
    "system_degradation_age_ratio_rate_curve": "Degradation",
    "facilities_per_installation": "Data Generation",
    "dependency_chain_group_range": "Data Generation",
    "maximum_vertical_dependency_depth": "Data Generation",
    "maximum_system_age": "Data Generation",
    "maximum_facility_age": "Data Generation",
    "generated_condition_index_distribution": "Data Generation Distributions",
    "generated_age_distribution": "Data Generation Distributions",
    "generated_resiliency_grade_distribution": "Data Generation Distributions",
    "generated_work_order_count_distribution": "Data Generation Distributions",
    "generated_work_order_status_distribution": "Data Generation Distributions",
    "generated_work_order_priority_distribution": "Data Generation Distributions",
    "generated_work_order_requesting_organization_distribution": "Data Generation Distributions",
    "enabled_simulation_modules": "Simulation",
    "excel_sheet_main": "Output",
    "excel_sheet_metadata": "Output",
    "excel_sheet_work_orders": "Output",
    "metadata_file_suffix": "Output",
    "csv_table_separator": "Output",
}

_SECTION_ORDER = (
    "Degradation",
    "Data Generation",
    "Data Generation Distributions",
    "Simulation",
    "Output",
    "Other",
)


# ! ==========================================================================================>
# ! TOP-LEVEL ENTRY POINT
# ! ==========================================================================================>


def run_settings_editor() -> bool:
    """Run the interactive picker loop until the user exits.

    Returns:
        ``True`` if any setting value was modified during the session.
    """
    settings = MidasSettings()
    any_changed = False

    while True:
        ordered_names = _list_settings_in_section_order(settings)
        if not ordered_names:
            DisplayHelper.print_warning("No settings are registered.", title="Settings")
            return any_changed

        _print_settings_index(settings, ordered_names)

        choices = [str(i) for i in range(1, len(ordered_names) + 1)] + [
            "b",
            "back",
            "q",
            "quit",
        ]
        raw = InputHelper.safe_prompt_ask(
            "Select a setting to edit (b to go back)",
            choices=choices,
            default="b",
        )
        if raw is None:
            return any_changed
        lowered = raw.strip().lower()
        if lowered in {"b", "back", "q", "quit"}:
            return any_changed

        try:
            index = int(lowered)
        except ValueError:
            continue
        if not (1 <= index <= len(ordered_names)):
            continue

        name = ordered_names[index - 1]
        state = settings.get_state(name)
        try:
            changed = edit_setting(name, state)
        except (ValueError, TypeError) as exc:
            DisplayHelper.print_error(
                f"Could not update {name!r}: {exc}", title="Settings"
            )
            logger.exception("Failed to edit setting %s", name)
            InputHelper.wait_for_continue()
            continue
        if changed:
            any_changed = True
            DisplayHelper.print_success(
                f"Updated '{state.label or name}'.", title="Settings"
            )


def edit_setting(name: str, state: SettingState) -> bool:
    """Dispatch to the per-type editor for ``state``.

    Returns:
        ``True`` if the underlying value was changed.
    """
    if isinstance(state, FloatSettingState):
        return _edit_float(name, state)
    if isinstance(state, IntegerSettingState):
        return _edit_integer(name, state)
    if isinstance(state, RangeSettingState):
        return _edit_range(name, state)
    if isinstance(state, StringSettingState):
        return _edit_string(name, state)
    if isinstance(state, BooleanMappingSettingState):
        return _edit_boolean_mapping(name, state)
    if isinstance(state, MappingSettingState):
        return _edit_mapping(name, state)
    if isinstance(state, DistributionSettingState):
        return _edit_distribution(name, state)
    DisplayHelper.print_warning(
        f"Setting type {type(state).__name__} is not editable from the CLI.",
        title="Settings",
    )
    InputHelper.wait_for_continue()
    return False


# ! ==========================================================================================>
# ! INDEX RENDERING
# ! ==========================================================================================>


def _list_settings_in_section_order(settings: MidasSettings) -> list[str]:
    """Return setting names ordered by ``_SECTION_ORDER`` then registration order."""
    by_section: dict[str, list[str]] = {section: [] for section in _SECTION_ORDER}
    for name, _state in settings.iter_states():
        section = _SECTION_BY_NAME.get(name, "Other")
        by_section.setdefault(section, []).append(name)
    ordered: list[str] = []
    for section in _SECTION_ORDER:
        ordered.extend(by_section.get(section, []))
    return ordered


def _print_settings_index(settings: MidasSettings, ordered_names: list[str]) -> None:
    """Print a numbered table of settings, sectioned by category, with current values."""
    table = Table(
        title="MIDAS Settings",
        show_header=True,
        header_style="bold cyan",
        border_style="green",
        show_lines=True,
    )
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta", no_wrap=True)
    table.add_column("Current Value", style="white", overflow="fold")
    table.add_column("Description", style="dim white", overflow="fold", ratio=2)

    last_section: str | None = None
    for index, name in enumerate(ordered_names, start=1):
        section = _SECTION_BY_NAME.get(name, "Other")
        if section != last_section:
            table.add_section()
            table.add_row("", f"[bold]{section}[/bold]", "", "", "")
            last_section = section
        state = settings.get_state(name)
        table.add_row(
            str(index),
            state.label or name,
            _setting_kind_label(state),
            _format_setting_value(state),
            _format_setting_description(state),
        )

    dirty_marker = (
        Text(" [unsaved changes]", style="bold red")
        if settings.is_dirty()
        else Text("")
    )
    header = Text("Pick a number to edit a setting; 'b' returns to the previous menu.")
    console.print("\n")
    console.print(Panel(Text.assemble(header, dirty_marker), border_style="cyan"))
    console.print(table)
    console.print()


def _setting_kind_label(state: SettingState) -> str:
    if isinstance(state, FloatSettingState):
        return "float"
    if isinstance(state, IntegerSettingState):
        return "integer"
    if isinstance(state, RangeSettingState):
        return "range"
    if isinstance(state, StringSettingState):
        return "choice" if state.choices else "string"
    if isinstance(state, BooleanMappingSettingState):
        return "toggle map"
    if isinstance(state, MappingSettingState):
        return "mapping"
    if isinstance(state, DistributionSettingState):
        dist = state.value
        return (
            f"distribution ({type(dist).__name__})"
            if dist is not None
            else "distribution"
        )
    return type(state).__name__


def _format_setting_description(state: SettingState) -> str:
    """Return a single-paragraph description suitable for the picker table."""
    description = (state.description or "").strip()
    if not description:
        return "[italic dim]No description.[/italic dim]"
    return " ".join(description.split())


def _format_setting_value(state: SettingState) -> RenderableType:
    """Render a setting's current value for the picker table.

    Distributions and mappings render as nested Rich tables so callers can see
    the full configuration without opening the editor.
    """
    if isinstance(state, RangeSettingState):
        low, high = state.value
        return f"{low}-{high}"
    if isinstance(state, FloatSettingState):
        return f"{state.value:g}"
    if isinstance(state, IntegerSettingState):
        return str(state.value)
    if isinstance(state, StringSettingState):
        return f'"{state.value}"'
    if isinstance(state, BooleanMappingSettingState):
        if not state.value:
            return "(empty)"
        return _create_boolean_mapping_value_table(state)
    if isinstance(state, MappingSettingState):
        if not state.value:
            return "(empty)"
        return _create_mapping_value_table(state)
    if isinstance(state, DistributionSettingState):
        if state.value is None:
            return "(unset)"
        return _create_count_distribution_table(state.value)
    return str(getattr(state, "value", ""))


def _create_mapping_value_table(state: MappingSettingState) -> Table:
    """Compact two-column table for a mapping setting's current entries."""
    table = Table(
        show_header=True,
        header_style="bold yellow",
        box=None,
        padding=(0, 1),
    )
    table.add_column(state.key_label or "Key", style="cyan")
    table.add_column(state.value_label or "Value", style="white", justify="right")
    for key, value in state.value.items():
        table.add_row(str(key), f"{value:g}")
    return table


def _create_boolean_mapping_value_table(state: BooleanMappingSettingState) -> Table:
    """Compact two-column table summarizing a boolean-mapping setting."""
    table = Table(
        show_header=True,
        header_style="bold yellow",
        box=None,
        padding=(0, 1),
    )
    table.add_column(state.key_label or "Key", style="cyan")
    table.add_column(state.value_label or "Enabled", style="white", justify="right")
    ordered_keys = (
        list(state.keys) if state.keys is not None else list(state.value.keys())
    )
    for key in ordered_keys:
        enabled = bool(state.value.get(key, False))
        label = state.display_label_for(key)
        status_style = "green" if enabled else "dim red"
        status_text = "on" if enabled else "off"
        table.add_row(label, f"[{status_style}]{status_text}[/{status_style}]")
    return table


# ! ==========================================================================================>
# ! SCALAR EDITORS
# ! ==========================================================================================>


def _bounds_hint(minimum: Any, maximum: Any) -> str:
    if minimum is None and maximum is None:
        return ""
    return f" [min={minimum if minimum is not None else '-inf'}, max={maximum if maximum is not None else '+inf'}]"


def _edit_float(name: str, state: FloatSettingState) -> bool:
    """Prompt for a new float value; bounds enforced via ``MidasSettings.set_value``."""
    DisplayHelper.print_info(
        f"{state.label or name}\n{state.description}\nCurrent: {state.value:g}{_bounds_hint(state.min, state.max)}",
        title="Edit Float",
    )
    new_value = _prompt_float(
        f"New value (blank to cancel)",
        default=state.value,
        minimum=state.min,
        maximum=state.max,
    )
    if new_value is None:
        DisplayHelper.print_warning("Edit cancelled.")
        return False
    if new_value == state.value:
        return False
    MidasSettings().set_value(name, new_value)
    return True


def _edit_integer(name: str, state: IntegerSettingState) -> bool:
    """Prompt for a new integer value with optional bounds."""
    DisplayHelper.print_info(
        f"{state.label or name}\n{state.description}\nCurrent: {state.value}{_bounds_hint(state.min, state.max)}",
        title="Edit Integer",
    )
    new_value = InputHelper.ask_number(
        "New value (b to cancel)",
        min_value=state.min,
        max_value=state.max,
        default=state.value,
        allow_back=True,
    )
    if new_value is None or new_value is InputHelper.QUIT_TO_MENU:
        DisplayHelper.print_warning("Edit cancelled.")
        return False
    if new_value == state.value:
        return False
    MidasSettings().set_value(name, new_value)
    return True


def _edit_range(name: str, state: RangeSettingState) -> bool:
    """Prompt for ``low`` then ``high``; values are swapped if reversed."""
    low_current, high_current = state.value
    DisplayHelper.print_info(
        f"{state.label or name}\n{state.description}\n"
        f"Current: {low_current}-{high_current}{_bounds_hint(state.min, state.max)}",
        title="Edit Range",
    )
    new_low = InputHelper.ask_number(
        "New low (b to cancel)",
        min_value=state.min,
        max_value=state.max,
        default=low_current,
        allow_back=True,
    )
    if new_low is None or new_low is InputHelper.QUIT_TO_MENU:
        DisplayHelper.print_warning("Edit cancelled.")
        return False
    new_high = InputHelper.ask_number(
        "New high (b to cancel)",
        min_value=state.min,
        max_value=state.max,
        default=high_current,
        allow_back=True,
    )
    if new_high is None or new_high is InputHelper.QUIT_TO_MENU:
        DisplayHelper.print_warning("Edit cancelled.")
        return False
    low, high = (new_low, new_high) if new_low <= new_high else (new_high, new_low)
    if (low, high) == (low_current, high_current):
        return False
    MidasSettings().set_value(name, (low, high))
    return True


def _edit_string(name: str, state: StringSettingState) -> bool:
    """Prompt for a new string; uses ``ask_choice`` when ``state.choices`` is set."""
    DisplayHelper.print_info(
        f'{state.label or name}\n{state.description}\nCurrent: "{state.value}"',
        title="Edit String",
    )
    if state.choices:
        new_value = InputHelper.ask_choice(
            "Pick a value (b to cancel)",
            choices=list(state.choices),
            default=state.value if state.value in state.choices else None,
            allow_back=True,
        )
        if new_value is None or new_value is InputHelper.QUIT_TO_MENU:
            DisplayHelper.print_warning("Edit cancelled.")
            return False
    else:
        raw = InputHelper.get_input_with_backspace(
            "New value (blank to cancel)",
            default=state.value,
            allow_empty=True,
        )
        if raw is None or raw == "":
            DisplayHelper.print_warning("Edit cancelled.")
            return False
        new_value = raw
    if new_value == state.value:
        return False
    MidasSettings().set_value(name, new_value)
    return True


# ! ==========================================================================================>
# ! MAPPING EDITOR
# ! ==========================================================================================>


def _edit_mapping(name: str, state: MappingSettingState) -> bool:
    """Iterate the mapping's keys and prompt for a new float per key.

    Blank input keeps the current value. The mapping is only persisted when at
    least one entry actually changes.
    """
    DisplayHelper.print_info(
        f"{state.label or name}\n{state.description}\n"
        f"{_bounds_hint(state.min, state.max).strip() or 'No per-value bounds.'}",
        title="Edit Mapping",
    )
    _print_mapping_entries(state)

    ordered_keys = (
        list(state.keys) if state.keys is not None else list(state.value.keys())
    )
    if not ordered_keys:
        DisplayHelper.print_warning(
            "This mapping has no editable entries.", title="Edit Mapping"
        )
        InputHelper.wait_for_continue()
        return False

    new_values: dict[str, float] = {}
    for key in ordered_keys:
        current = float(state.value.get(key, 0.0))
        new_value = _prompt_float(
            f"{state.value_label} for {key} [current {current:g}] (blank to keep)",
            default=current,
            minimum=state.min,
            maximum=state.max,
        )
        new_values[key] = current if new_value is None else new_value

    if all(new_values[key] == state.value.get(key) for key in ordered_keys):
        return False

    try:
        MidasSettings().set_value(name, new_values)
    except (TypeError, ValueError) as exc:
        DisplayHelper.print_error(f"Invalid mapping: {exc}", title="Edit Mapping")
        return False
    return True


def _edit_boolean_mapping(name: str, state: BooleanMappingSettingState) -> bool:
    """Toggle individual entries in a boolean-mapping setting.

    The editor lists each entry with its current ``on``/``off`` status and
    offers a sub-loop: enter a number to toggle that entry, ``a`` to enable
    all, ``n`` to disable all, ``d`` to finish. The mapping is only persisted
    when at least one entry actually changes.
    """
    DisplayHelper.print_info(
        f"{state.label or name}\n{state.description}",
        title="Edit Toggle Map",
    )

    ordered_keys = (
        list(state.keys) if state.keys is not None else list(state.value.keys())
    )
    if not ordered_keys:
        DisplayHelper.print_warning(
            "This toggle map has no editable entries.",
            title="Edit Toggle Map",
        )
        InputHelper.wait_for_continue()
        return False

    working: dict[str, bool] = {
        key: bool(state.value.get(key, False)) for key in ordered_keys
    }
    initial = dict(working)

    while True:
        _print_boolean_mapping_entries(state, working, ordered_keys)
        numeric_choices = [str(index) for index in range(1, len(ordered_keys) + 1)]
        choices = numeric_choices + ["a", "n", "d"]
        action = InputHelper.ask_choice(
            "Toggle # / (a)ll on / (n)one / (d)one",
            choices=choices,
            default="d",
            allow_back=True,
        )
        if action is None or action is InputHelper.QUIT_TO_MENU or action == "d":
            break
        if action == "a":
            working = {key: True for key in ordered_keys}
            continue
        if action == "n":
            working = {key: False for key in ordered_keys}
            continue
        try:
            index = int(action)
        except ValueError:
            continue
        if not (1 <= index <= len(ordered_keys)):
            continue
        target_key = ordered_keys[index - 1]
        working[target_key] = not working[target_key]

    if working == initial:
        return False

    try:
        MidasSettings().set_value(name, working)
    except (TypeError, ValueError) as exc:
        DisplayHelper.print_error(f"Invalid toggle map: {exc}", title="Edit Toggle Map")
        return False
    return True


def _print_boolean_mapping_entries(
    state: BooleanMappingSettingState,
    working: dict[str, bool],
    ordered_keys: list[str],
) -> None:
    """Render the current toggle state as a numbered table."""
    table = Table(
        show_header=True,
        header_style="bold cyan",
        title="Current Entries",
    )
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column(state.key_label or "Key", style="cyan")
    table.add_column(state.value_label or "Enabled", style="white", justify="right")
    for index, key in enumerate(ordered_keys, start=1):
        enabled = bool(working.get(key, False))
        status_style = "green" if enabled else "dim red"
        status_text = "on" if enabled else "off"
        table.add_row(
            str(index),
            state.display_label_for(key),
            f"[{status_style}]{status_text}[/{status_style}]",
        )
    console.print(table)
    console.print()


def _print_mapping_entries(state: MappingSettingState) -> None:
    """Render the mapping's current ``(key, value)`` pairs in a Rich table."""
    table = Table(
        show_header=True,
        header_style="bold cyan",
        title="Current Entries",
    )
    table.add_column(state.key_label or "Key", style="cyan")
    table.add_column(state.value_label or "Value", style="white", justify="right")
    if not state.value:
        table.add_row("-", "[dim]No entries configured[/dim]")
    else:
        for key, value in state.value.items():
            table.add_row(str(key), f"{value:g}")
    console.print(table)
    console.print()


# ! ==========================================================================================>
# ! DISTRIBUTION EDITOR
# ! ==========================================================================================>


def _edit_distribution(name: str, state: DistributionSettingState) -> bool:
    """Dispatch to the editor matching the concrete distribution subclass."""
    distribution = state.value
    if distribution is None:
        DisplayHelper.print_warning(
            "This distribution is not configured; cannot edit from CLI.",
            title="Edit Distribution",
        )
        InputHelper.wait_for_continue()
        return False

    DisplayHelper.print_info(
        f"{state.label or name}\n{state.description}\n"
        f"Type: {type(distribution).__name__}",
        title="Edit Distribution",
    )
    console.print(_create_count_distribution_table(distribution))
    console.print()

    if isinstance(distribution, WeightedProbabilityDistribution):
        return _edit_weighted_distribution(name, distribution)
    if isinstance(distribution, BathtubCurveDistribution):
        return _edit_bathtub_distribution(name, distribution)
    if isinstance(distribution, NormalCurveDistribution):
        return _edit_normal_distribution(name, distribution)
    if isinstance(distribution, PiecewiseCurveDistribution):
        return _edit_piecewise_distribution(name, distribution)
    if isinstance(distribution, EventRateDistribution):
        return _edit_event_rate_distribution(name, distribution)
    DisplayHelper.print_warning(
        f"Distribution type {type(distribution).__name__} is not editable from the CLI.",
        title="Edit Distribution",
    )
    InputHelper.wait_for_continue()
    return False


def _edit_weighted_distribution(
    name: str, distribution: WeightedProbabilityDistribution
) -> bool:
    """Sub-loop for adding / editing / removing weighted segments."""
    working = [
        WeightedProbabilitySegment(seg.weight_percent, seg.value)
        for seg in distribution.segments
    ]
    changed = False
    while True:
        _print_weighted_segments(working)
        action = InputHelper.ask_choice(
            "Action: (a)dd, (e)dit, (r)emove, (d)one",
            choices=["a", "e", "r", "d"],
            default="d",
            allow_back=True,
        )
        if action is None or action is InputHelper.QUIT_TO_MENU or action == "d":
            break
        if action == "a":
            if _prompt_add_segment(working):
                changed = True
            continue
        if action == "e":
            if _prompt_edit_segment(working):
                changed = True
            continue
        if action == "r":
            if _prompt_remove_segment(working):
                changed = True
            continue

    if not changed:
        return False
    if not working:
        DisplayHelper.print_error(
            "A weighted distribution requires at least one segment; reverting.",
            title="Edit Distribution",
        )
        return False
    MidasSettings().set_value(name, WeightedProbabilityDistribution(working))
    return True


def _print_weighted_segments(segments: list[WeightedProbabilitySegment]) -> None:
    table = Table(show_header=True, header_style="bold cyan", title="Current Segments")
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column("Percentage", style="magenta", justify="right")
    table.add_column("Value", style="white")
    if not segments:
        table.add_row("-", "-", "[dim]No segments configured[/dim]")
    else:
        for index, seg in enumerate(segments, start=1):
            table.add_row(str(index), f"{seg.weight_percent}%", seg.value)
    total = sum(seg.weight_percent for seg in segments)
    console.print(table)
    style = "yellow" if total != 100 else "green"
    console.print(f"[{style}]Total weight: {total}%[/{style}]\n")


def _prompt_add_segment(segments: list[WeightedProbabilitySegment]) -> bool:
    weight = InputHelper.ask_number(
        "New segment percentage (1-100, b to cancel)",
        min_value=1,
        max_value=100,
        default=10,
        allow_back=True,
    )
    if weight is None or weight is InputHelper.QUIT_TO_MENU:
        return False
    raw_value = InputHelper.get_input_with_backspace(
        "New segment value (blank to cancel)", allow_empty=True
    )
    if raw_value is None or raw_value == "":
        return False
    try:
        segments.append(WeightedProbabilitySegment(int(weight), raw_value))
    except ValueError as exc:
        DisplayHelper.print_error(f"Invalid segment: {exc}", title="Edit Distribution")
        return False
    return True


def _prompt_edit_segment(segments: list[WeightedProbabilitySegment]) -> bool:
    if not segments:
        DisplayHelper.print_warning("No segments to edit.")
        return False
    index = InputHelper.ask_number(
        f"Segment number to edit (1-{len(segments)}, b to cancel)",
        min_value=1,
        max_value=len(segments),
        allow_back=True,
    )
    if index is None or index is InputHelper.QUIT_TO_MENU:
        return False
    target = segments[index - 1]
    weight = InputHelper.ask_number(
        f"Percentage [current {target.weight_percent}] (b to cancel)",
        min_value=1,
        max_value=100,
        default=target.weight_percent,
        allow_back=True,
    )
    if weight is None or weight is InputHelper.QUIT_TO_MENU:
        return False
    raw_value = InputHelper.get_input_with_backspace(
        f'Value [current "{target.value}"] (blank to cancel)',
        default=target.value,
        allow_empty=True,
    )
    if raw_value is None or raw_value == "":
        return False
    try:
        segments[index - 1] = WeightedProbabilitySegment(int(weight), raw_value)
    except ValueError as exc:
        DisplayHelper.print_error(f"Invalid segment: {exc}", title="Edit Distribution")
        return False
    return True


def _prompt_remove_segment(segments: list[WeightedProbabilitySegment]) -> bool:
    if not segments:
        DisplayHelper.print_warning("No segments to remove.")
        return False
    index = InputHelper.ask_number(
        f"Segment number to remove (1-{len(segments)}, b to cancel)",
        min_value=1,
        max_value=len(segments),
        allow_back=True,
    )
    if index is None or index is InputHelper.QUIT_TO_MENU:
        return False
    segments.pop(index - 1)
    return True


def _edit_bathtub_distribution(
    name: str, distribution: BathtubCurveDistribution
) -> bool:
    """Edit each named float field on a bathtub curve."""
    fields = (
        ("early_peak_rate", "Early peak rate"),
        ("useful_life_rate", "Useful life rate"),
        ("wearout_peak_rate", "Wearout peak rate"),
        ("early_end_ratio", "Early end ratio"),
        ("wearout_start_ratio", "Wearout start ratio"),
        ("max_ratio", "Max ratio"),
    )
    return _edit_named_float_fields(
        name, distribution, fields, BathtubCurveDistribution
    )


def _edit_normal_distribution(name: str, distribution: NormalCurveDistribution) -> bool:
    """Edit each named field on a normal-curve distribution."""
    fields = (
        ("baseline_rate", "Baseline rate"),
        ("amplitude", "Amplitude"),
        ("mean", "Mean"),
        ("stddev", "Stddev (must be > 0)"),
    )
    return _edit_named_float_fields(name, distribution, fields, NormalCurveDistribution)


def _edit_event_rate_distribution(
    name: str, distribution: EventRateDistribution
) -> bool:
    """Generic editor for any other ``EventRateDistribution`` subclass."""
    fields = tuple(
        (attr, attr.replace("_", " ").title())
        for attr in vars(distribution)
        if not attr.startswith("_")
        and isinstance(getattr(distribution, attr), (int, float))
    )
    if not fields:
        DisplayHelper.print_warning(
            f"No editable scalar fields on {type(distribution).__name__}.",
            title="Edit Distribution",
        )
        InputHelper.wait_for_continue()
        return False
    return _edit_named_float_fields(name, distribution, fields, type(distribution))


def _edit_named_float_fields(
    name: str,
    distribution: DistributionBase,
    fields: tuple[tuple[str, str], ...],
    cls: type[DistributionBase],
) -> bool:
    """Prompt for each ``(attr, label)`` pair, reconstruct via ``cls(**values)``."""
    values: dict[str, float] = {}
    for attr, label in fields:
        current = getattr(distribution, attr)
        new_value = _prompt_float(
            f"{label} [current {current:g}] (blank to keep)",
            default=current,
        )
        values[attr] = float(current) if new_value is None else new_value
    if all(values[attr] == getattr(distribution, attr) for attr, _ in fields):
        return False
    try:
        new_distribution = cls(**values)
    except (TypeError, ValueError) as exc:
        DisplayHelper.print_error(
            f"Invalid distribution parameters: {exc}", title="Edit Distribution"
        )
        return False
    MidasSettings().set_value(name, new_distribution)
    return True


def _edit_piecewise_distribution(
    name: str, distribution: PiecewiseCurveDistribution
) -> bool:
    """Sub-loop for editing piecewise (age_ratio, rate) control points."""
    working: list[tuple[float, float]] = list(distribution.points)
    changed = False
    while True:
        _print_piecewise_points(working)
        action = InputHelper.ask_choice(
            "Action: (a)dd, (e)dit, (r)emove, (d)one",
            choices=["a", "e", "r", "d"],
            default="d",
            allow_back=True,
        )
        if action is None or action is InputHelper.QUIT_TO_MENU or action == "d":
            break
        if action == "a":
            point = _prompt_piecewise_point()
            if point is not None:
                working.append(point)
                changed = True
            continue
        if action == "e":
            if not working:
                DisplayHelper.print_warning("No points to edit.")
                continue
            index = InputHelper.ask_number(
                f"Point number to edit (1-{len(working)}, b to cancel)",
                min_value=1,
                max_value=len(working),
                allow_back=True,
            )
            if index is None or index is InputHelper.QUIT_TO_MENU:
                continue
            current = working[index - 1]
            point = _prompt_piecewise_point(default=current)
            if point is not None:
                working[index - 1] = point
                changed = True
            continue
        if action == "r":
            if not working:
                DisplayHelper.print_warning("No points to remove.")
                continue
            index = InputHelper.ask_number(
                f"Point number to remove (1-{len(working)}, b to cancel)",
                min_value=1,
                max_value=len(working),
                allow_back=True,
            )
            if index is None or index is InputHelper.QUIT_TO_MENU:
                continue
            working.pop(index - 1)
            changed = True
            continue

    if not changed:
        return False
    try:
        new_distribution = PiecewiseCurveDistribution(working)
    except ValueError as exc:
        DisplayHelper.print_error(
            f"Invalid piecewise points: {exc}", title="Edit Distribution"
        )
        return False
    MidasSettings().set_value(name, new_distribution)
    return True


def _print_piecewise_points(points: list[tuple[float, float]]) -> None:
    table = Table(show_header=True, header_style="bold cyan", title="Current Points")
    table.add_column("#", style="bold yellow", justify="right", width=4)
    table.add_column("Age Ratio", style="magenta", justify="right")
    table.add_column("Rate", style="white", justify="right")
    if not points:
        table.add_row("-", "-", "[dim]No points configured[/dim]")
    else:
        for index, (age_ratio, rate) in enumerate(points, start=1):
            table.add_row(str(index), f"{age_ratio:g}", f"{rate:g}")
    console.print(table)
    console.print()


def _prompt_piecewise_point(
    default: tuple[float, float] | None = None,
) -> tuple[float, float] | None:
    default_age = default[0] if default is not None else None
    default_rate = default[1] if default is not None else None
    age_ratio = _prompt_float(
        "Age ratio (blank to cancel)",
        default=default_age,
    )
    if age_ratio is None:
        return None
    rate = _prompt_float(
        "Rate (blank to cancel)",
        default=default_rate,
    )
    if rate is None:
        return None
    return (age_ratio, rate)


# ! ==========================================================================================>
# ! INPUT HELPERS
# ! ==========================================================================================>


def _prompt_float(
    prompt: str,
    default: float | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    """Prompt for a float; blank input returns ``None`` to signal cancel/keep."""
    while True:
        raw = InputHelper.get_input_with_backspace(
            prompt,
            default=f"{default:g}" if default is not None else "",
            allow_empty=True,
        )
        if raw is None or raw == "":
            return None
        try:
            value = float(raw)
        except ValueError:
            console.print("[red]Invalid number. Please enter a valid float.[/red]\n")
            continue
        if minimum is not None and value < minimum:
            console.print(f"[red]Value must be at least {minimum}.[/red]\n")
            continue
        if maximum is not None and value > maximum:
            console.print(f"[red]Value must be at most {maximum}.[/red]\n")
            continue
        return value
