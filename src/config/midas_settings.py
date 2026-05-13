"""Process-wide ``MidasSettings`` singleton holding configurable runtime settings.

Each configurable value is held as a :class:`SettingState`. State is persisted
to ``<output_dir>/midas_settings.json`` via :meth:`MidasSettings.save_state`
and reloaded via :meth:`MidasSettings.load_state` on startup.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from src.config._singleton import SingletonMeta
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
from src.models import (
    BathtubCurveDistribution,
    WeightedProbabilityDistribution,
    WeightedProbabilitySegment,
)

if TYPE_CHECKING:
    from src.config.midas_config_data import MidasConfigData
    from src.simulation.modules.base import SimulationModuleBase

logger = logging.getLogger(__name__)


class MidasSettings(metaclass=SingletonMeta):
    """Singleton container for all MIDAS configurable runtime settings.

    Instantiation is cached: ``MidasSettings()`` always returns the same
    object. Use :meth:`get_value`, :meth:`set_value`, and :meth:`get_state`
    to interact with stored values. State can be serialized to disk via
    :meth:`save_state` and reloaded via :meth:`load_state`.
    """

    # ! ==========================================================================================>
    # ! CLASS CONSTANTS
    # ! ==========================================================================================>

    DEFAULT_CONFIG_DATA_FILENAME = "midas_config_data.xlsx"
    DEFAULT_STATE_FILE_NAME: str = "midas_settings.json"
    DEFAULT_OUTPUT_DIRECTORY: Path = (
        Path(__file__).resolve().parent.parent.parent / "output"
    )
    DEFAULT_CONFIG_DATA_PATH: Path = (
        Path(__file__).resolve().parent.parent.parent
        / "docs"
        / DEFAULT_CONFIG_DATA_FILENAME
    )

    # ! ==========================================================================================>
    # ! INITIALIZATION
    # ! ==========================================================================================>

    def __init__(self) -> None:
        """Populate the setting states with documented defaults (singleton-safe)."""
        self._states: dict[str, SettingState] = {}
        self._dirty: bool = False
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Seed the singleton with documented default setting states."""
        # --- Degradation Settings ---
        self._states["condition_index_degraded_threshold"] = FloatSettingState(
            label="Infrastructure Condition Index Degraded Threshold",
            description=(
                "The value at which any piece of infrastructure "
                "[Installation, Facility, System] is considered to have a degraded state."
            ),
            value=25.0,
            min=0.0,
            max=100.0,
        )
        self._states["resiliency_grade_rating_threshold"] = IntegerSettingState(
            label="Resiliency Grade Rating Threshold",
            description=(
                "Percentage of dependant infrastructure required to evaluate a parent "
                "infrastructure instance's resiliency to one of four UFC Grades. E.g. for 70 - "
                "70% of dependant Facilities must be at least UFC G3 for the parent to be rated UFC G3."
            ),
            value=70,
            min=0,
            max=100,
        )
        self._states["initial_condition_index_default"] = FloatSettingState(
            label="Initial Condition Index Default Value",
            description=(
                "Initial rating given to new infrastructure when it starts its life. "
                "Out of 100; typical values are 99.99 or 100.00."
            ),
            value=99.99,
            min=0.0,
            max=100.0,
        )
        self._states["system_degradation_state_rate_multipliers"] = MappingSettingState(
            label="System Degradation Hazard Multipliers by Condition State",
            description=(
                "Per-condition-state multipliers applied to the base age-driven degradation "
                "hazard rate in the System Degradation simulation module. Higher values make "
                "Systems in that condition band degrade faster (1.0 = baseline). The 'failed' "
                "state is excluded because failed Systems are no longer degraded."
            ),
            value={
                "excellent": 0.9,
                "good": 1.0,
                "fair": 1.15,
                "poor": 1.3,
                "critical": 1.65,
            },
            keys=("excellent", "good", "fair", "poor", "critical"),
            min=0.0,
            max=10.0,
            key_label="Condition State",
            value_label="Hazard Multiplier",
        )
        self._states["random_system_degradation_chance"] = FloatSettingState(
            label="System Random Degradation Annual Chance",
            description=(
                "Percentage chance per year that an individual System suffers an independent "
                "random degradation event in addition to the age-driven hazard. The System "
                "Degradation simulation module scales this base rate linearly by tick length "
                "(1 year = full chance, 1 month tick gets ~1/12 of the chance, 1 day tick gets "
                "~1/365 of the chance) and caps the per-tick probability at 100%."
            ),
            value=35.0,
            min=0.0,
            max=100.0,
        )
        self._states["random_system_degradation_ci_drop"] = FloatSettingState(
            label="System Random Degradation CI Drop",
            description=(
                "Condition-index points subtracted from a System's condition index when a "
                "random degradation event fires in the System Degradation simulation module. "
                "Applied as a single drop independent of the age-driven hazard's per-band "
                "transition logic; the resulting CI is clamped at 0."
            ),
            value=15.0,
            min=0.0,
            max=100.0,
        )
        self._states["system_degradation_age_ratio_rate_curve"] = MappingSettingState(
            label="System Degradation Age Ratio Rate Curve",
            description=(
                "Piecewise-linear curve of base annual condition-state transition rates "
                "indexed by normalized System age (current age / life expectancy). The "
                "System Degradation simulation module reads this setting once per tick, "
                "interpolates between the configured breakpoints to compute a base hazard "
                "rate for the System's current age, then multiplies it by the per-band "
                "value from 'system_degradation_state_rate_multipliers' to get the annual "
                "transition rate driving the exponential waiting-time loop. Keys are the "
                "normalized age ratios (0.00 = brand new, 1.00 = at life expectancy, "
                ">1.00 = past life expectancy) and values are the corresponding base "
                "annual rates (events/year). The curve is clamped at the smallest and "
                "largest configured age ratios; raise values to make older Systems "
                "degrade faster, lower them to slow the late-life acceleration."
            ),
            value={
                "0.00": 0.012,
                "0.25": 0.02,
                "0.50": 0.05,
                "0.75": 0.09,
                "1.00": 0.18,
                "1.25": 0.32,
                "1.50": 0.55,
            },
            keys=("0.00", "0.25", "0.50", "0.75", "1.00", "1.25", "1.50"),
            min=0.0,
            max=10.0,
            key_label="Age Ratio",
            value_label="Base Annual Rate",
        )

        # --- Data Generation Settings ---
        self._states["facilities_per_installation"] = RangeSettingState(
            label="Number of Facilities Generated per Installation (range)",
            description=(
                "A range value (min, max) guideline used when randomly generating data to use "
                "in the MIDAS application which defines how many Facilities can be created for "
                "a given Installation instance."
            ),
            value=(8, 14),
            min=1,
            max=99,
        )
        self._states["dependency_chain_group_range"] = RangeSettingState(
            label="Dependency Chain Group Count (range)",
            description=(
                "A range value (min, max) guideline used to randomly generate grouping data in "
                "the MIDAS application. This range defines the count of dependency sub-groups "
                "which exist in a single instance of an Installation comprised of individual "
                "Facilities."
            ),
            value=(1, 3),
            min=0,
            max=9,
        )
        self._states["maximum_vertical_dependency_depth"] = IntegerSettingState(
            label="Maximum Vertical Dependency Depth",
            description=(
                "Maximum number of vertical positions which can exist in a randomly generated "
                "Dependency Chain for a given Installation."
            ),
            value=3,
            min=1,
            max=26,
        )
        self._states["maximum_system_age"] = IntegerSettingState(
            label="Maximum generated System Age",
            description="Maximum age allowed for a randomly generated System instance.",
            value=80,
            min=1,
            max=999,
        )
        self._states["maximum_facility_age"] = IntegerSettingState(
            label="Maximum generated Facility Age",
            description="Maximum age allowed for a randomly generated Facility instance.",
            value=80,
            min=1,
            max=999,
        )

        # --- Data Generation Distributions ---
        self._states["generated_condition_index_distribution"] = (
            DistributionSettingState(
                label="Generated Condition Index Data Distribution",
                description=(
                    "The probability distribution used to randomly select a starting condition "
                    "index value for a generated piece of infrastructure."
                ),
                value=WeightedProbabilityDistribution(
                    [
                        WeightedProbabilitySegment(7, "1-50"),
                        WeightedProbabilitySegment(88, "50-85"),
                        WeightedProbabilitySegment(5, "85-100"),
                    ]
                ),
            )
        )
        self._states["generated_age_distribution"] = DistributionSettingState(
            label="Generated Age Data Distribution",
            description=(
                "The probability distribution used to randomly select an age for a generated "
                "piece of infrastructure."
            ),
            value=WeightedProbabilityDistribution(
                [
                    WeightedProbabilitySegment(50, "20-40"),
                    WeightedProbabilitySegment(20, "10-20"),
                    WeightedProbabilitySegment(20, "41-80"),
                    WeightedProbabilitySegment(10, "0-9"),
                ]
            ),
        )
        self._states["generated_resiliency_grade_distribution"] = (
            DistributionSettingState(
                label="Generated Resiliency Grade Data Distribution",
                description=(
                    "The probability distribution used to randomly select a UFC Grade for a "
                    "generated piece of infrastructure."
                ),
                value=WeightedProbabilityDistribution(
                    [
                        WeightedProbabilitySegment(52, "1"),
                        WeightedProbabilitySegment(32, "2"),
                        WeightedProbabilitySegment(12, "3"),
                        WeightedProbabilitySegment(4, "4"),
                    ]
                ),
            )
        )
        self._states["generated_work_order_count_distribution"] = (
            DistributionSettingState(
                label="Generated Work Order Count Distribution",
                description=(
                    "Probability distribution used to determine the number of Work Order instances "
                    "to create for a randomly generated System."
                ),
                value=BathtubCurveDistribution(),
            )
        )
        self._states["generated_work_order_status_distribution"] = (
            DistributionSettingState(
                label="Generated Work Order Status Distribution",
                description=(
                    "Probability distribution used to determine the status of randomly generated "
                    "Work Order instances on creation."
                ),
                value=WeightedProbabilityDistribution(
                    [
                        WeightedProbabilitySegment(8, "Submitted"),
                        WeightedProbabilitySegment(14, "Approved"),
                        WeightedProbabilitySegment(26, "In Progress"),
                        WeightedProbabilitySegment(52, "Completed"),
                    ]
                ),
            )
        )
        self._states["generated_work_order_priority_distribution"] = (
            DistributionSettingState(
                label="Generated Work Order Priority Distribution",
                description=(
                    "Reference probability distribution for work-order work category / priority. "
                    "Generation now copies the category directly from the sampled workbook template; "
                    "this setting is retained for reporting and future re-weighting."
                ),
                value=WeightedProbabilityDistribution(
                    [
                        WeightedProbabilitySegment(7, "Emergency"),
                        WeightedProbabilitySegment(18, "Urgent"),
                        WeightedProbabilitySegment(50, "Routine"),
                        WeightedProbabilitySegment(25, "Preventive Maintenance"),
                    ]
                ),
            )
        )
        self._states["generated_work_order_requesting_organization_distribution"] = (
            DistributionSettingState(
                label="Generated Work Order Requesting Organization Distribution",
                description=(
                    "Probability distribution used to determine the requesting organization of "
                    "randomly generated Work Order instances on creation."
                ),
                value=WeightedProbabilityDistribution(
                    [
                        WeightedProbabilitySegment(1, "J1"),
                        WeightedProbabilitySegment(1, "J2"),
                        WeightedProbabilitySegment(1, "J3"),
                        WeightedProbabilitySegment(1, "J4"),
                        WeightedProbabilitySegment(1, "J5"),
                        WeightedProbabilitySegment(1, "J6"),
                    ]
                ),
            )
        )

        # --- Simulation Settings ---
        self._states["enabled_simulation_modules"] = BooleanMappingSettingState(
            label="Enabled Simulation Modules",
            description=(
                "Selects which simulation modules run during a live simulation tick. "
                "Entries are populated from the modules discovered under "
                "src/simulation/modules/ during ApplicationState startup."
            ),
            value={},
            keys=None,
            labels={},
            key_label="Module",
            value_label="Enabled",
        )
        # --- Output Settings ---
        self._states["excel_sheet_main"] = StringSettingState(
            label="Excel Main Sheet Name",
            description="Sheet name for denormalized exports written to .xlsx files.",
            value="Main Data",
        )
        self._states["excel_sheet_metadata"] = StringSettingState(
            label="Excel Metadata Sheet Name",
            description="Sheet name used to store export metadata inside .xlsx workbooks.",
            value="_metadata",
        )
        self._states["excel_sheet_work_orders"] = StringSettingState(
            label="Excel Work Orders Sheet Name",
            description=(
                "Sheet name used for the work-orders table in normalized .xlsx exports."
            ),
            value="Work Orders",
        )
        self._states["metadata_file_suffix"] = StringSettingState(
            label="Metadata File Suffix",
            description="Filename suffix appended when writing the CSV metadata JSON sidecar.",
            value="_metadata.json",
        )
        self._states["csv_table_separator"] = StringSettingState(
            label="CSV Table Separator",
            description=(
                "Character placed between the export base name and table name in normalized "
                "CSV exports (e.g. 'mydata_facilities.csv' when separator is '_')."
            ),
            value="_",
        )

    # ! ==========================================================================================>
    # ! VALUE ACCESS HELPERS
    # ! ==========================================================================================>

    def get_state(self, name: str) -> SettingState:
        """Return the ``SettingState`` registered under ``name``.

        Raises:
            KeyError: If ``name`` is not a known setting.
        """
        try:
            return self._states[name]
        except KeyError as exc:
            raise KeyError(f"Unknown MidasSettings setting: {name!r}") from exc

    def get_value(self, name: str) -> Any:
        """Return the underlying value of the setting state named ``name``."""
        return self.get_state(name).value

    def set_value(self, name: str, value: Any) -> None:
        """Replace the value of the setting state named ``name``.

        Range checks (when ``min``/``max`` are defined) are enforced for
        scalar setting types; range tuples are coerced to ``(int, int)``.

        Raises:
            KeyError: If ``name`` is not a known setting.
            ValueError: If the value is out of declared bounds or invalid shape.
        """
        state = self.get_state(name)
        if isinstance(state, FloatSettingState):
            coerced = float(value)
            _check_bounds(name, coerced, state.min, state.max)
            state.value = coerced
        elif isinstance(state, IntegerSettingState):
            coerced_int = int(value)
            _check_bounds(name, coerced_int, state.min, state.max)
            state.value = coerced_int
        elif isinstance(state, RangeSettingState):
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError(
                    f"Range setting {name!r} requires a (min, max) pair (got {value!r})"
                )
            low, high = int(value[0]), int(value[1])
            _check_bounds(name, low, state.min, state.max)
            _check_bounds(name, high, state.min, state.max)
            state.value = (low, high)
        elif isinstance(state, StringSettingState):
            text = str(value)
            if state.choices is not None and text not in state.choices:
                raise ValueError(
                    f"String setting {name!r} must be one of {list(state.choices)} (got {text!r})"
                )
            state.value = text
        elif isinstance(state, BooleanMappingSettingState):
            if not isinstance(value, dict):
                raise ValueError(
                    f"Boolean mapping setting {name!r} requires a dict "
                    f"(got {type(value).__name__})"
                )
            if state.keys is not None:
                expected = set(state.keys)
                provided = set(value.keys())
                if provided != expected:
                    missing = sorted(expected - provided)
                    extra = sorted(provided - expected)
                    raise ValueError(
                        f"Boolean mapping setting {name!r} requires keys "
                        f"{sorted(expected)} (missing={missing}, unexpected={extra})"
                    )
                ordered_keys = state.keys
            else:
                ordered_keys = tuple(str(key) for key in value.keys())
            state.value = {key: bool(value[key]) for key in ordered_keys}
        elif isinstance(state, MappingSettingState):
            if not isinstance(value, dict):
                raise ValueError(
                    f"Mapping setting {name!r} requires a dict (got {type(value).__name__})"
                )
            if state.keys is not None:
                expected = set(state.keys)
                provided = set(value.keys())
                if provided != expected:
                    missing = sorted(expected - provided)
                    extra = sorted(provided - expected)
                    raise ValueError(
                        f"Mapping setting {name!r} requires keys {sorted(expected)} "
                        f"(missing={missing}, unexpected={extra})"
                    )
                ordered_keys: tuple[str, ...] = state.keys
            else:
                ordered_keys = tuple(str(key) for key in value.keys())
            coerced_values: dict[str, float] = {}
            for key in ordered_keys:
                coerced = float(value[key])
                _check_bounds(f"{name}[{key}]", coerced, state.min, state.max)
                coerced_values[key] = coerced
            state.value = coerced_values
        elif isinstance(state, DistributionSettingState):
            # ``DistributionBase`` is a non-runtime Protocol, so duck-type the contract
            # callers actually rely on (``sample`` plus ``to_dict`` for round-tripping).
            if not (
                callable(getattr(value, "sample", None))
                and callable(getattr(value, "to_dict", None))
            ):
                raise ValueError(
                    f"Distribution setting {name!r} requires a DistributionBase instance "
                    f"(got {type(value).__name__})"
                )
            state.value = value
        else:
            raise ValueError(
                f"Unsupported setting state type for {name!r}: {type(state).__name__}"
            )
        self._dirty = True

    def is_dirty(self) -> bool:
        """Return ``True`` when there are unsaved in-memory setting changes."""
        return self._dirty

    def mark_clean(self) -> None:
        """Reset the unsaved-changes flag (used after an explicit save/load)."""
        self._dirty = False

    def iter_states(self) -> Iterable[tuple[str, SettingState]]:
        """Iterate over ``(name, setting_state)`` pairs in registration order."""
        return self._states.items()

    def has_setting(self, name: str) -> bool:
        """Return ``True`` if ``name`` is a registered setting."""
        return name in self._states

    # ! ==========================================================================================>
    # ! REFERENCE-DATA ACCESS
    # ! ==========================================================================================>

    @property
    def config_data(self) -> "MidasConfigData":
        """Return the reference-data singleton (lazy import to avoid cycles)."""
        from src.config.midas_config_data import MidasConfigData

        return MidasConfigData()

    # ! ==========================================================================================>
    # ! DERIVED HELPERS (DATA GENERATION SAMPLING)
    # ! ==========================================================================================>

    def get_random_facility_count(self) -> int:
        """Random facility count within ``facilities_per_installation`` range."""
        low, high = self.get_value("facilities_per_installation")
        return random.randint(low, high)

    def get_dependency_chain_vertical_positions(self) -> list[str]:
        """Return dependency-chain vertical labels based on max depth."""
        max_depth = self.get_value("maximum_vertical_dependency_depth")
        if isinstance(max_depth, int) and max_depth > 0:
            return [chr(ord("A") + i) for i in range(max_depth)]
        return ["A", "B", "C"]

    def get_random_dependency_chain_vertical_position(self) -> str:
        """Return a random vertical position from configured dependency levels."""
        return random.choice(self.get_dependency_chain_vertical_positions())

    def get_random_dependency_chain_group_count(self) -> int:
        """Return a random dependency-group count from the configured range."""
        low, high = self.get_value("dependency_chain_group_range")
        if low > high:
            low, high = high, low
        return random.randint(low, high)

    def get_random_dependency_chain_group_ids(self) -> list[int]:
        """Return sorted unique dependency-group IDs for a dependency chain."""
        low, high = self.get_value("dependency_chain_group_range")
        if high < low:
            low, high = high, low
        id_pool = list(range(max(1, low), high + 1))
        if not id_pool:
            return []
        count = self.get_random_dependency_chain_group_count()
        sample_count = min(count, len(id_pool))
        return sorted(random.sample(id_pool, sample_count))

    # ! ==========================================================================================>
    # ! SIMULATION MODULE REGISTRY HELPERS
    # ! ==========================================================================================>

    def sync_simulation_module_registry(self) -> None:
        """Reconcile ``enabled_simulation_modules`` with the runtime registry.

        Newly discovered module keys are added (using ``default_enabled``),
        keys that are no longer registered are dropped, and ``keys`` /
        ``labels`` on the setting state are refreshed. Called during
        ``ApplicationState.initialize()`` after settings load from disk.
        """
        from src.simulation.modules.registry import get_module_specs

        state = self.get_state("enabled_simulation_modules")
        if not isinstance(state, BooleanMappingSettingState):
            raise TypeError(
                "enabled_simulation_modules must be a BooleanMappingSettingState"
            )

        specs = get_module_specs()
        ordered_keys = tuple(spec.key for spec in specs)
        existing = state.value
        merged: dict[str, bool] = {}
        for spec in specs:
            if spec.key in existing:
                merged[spec.key] = bool(existing[spec.key])
            else:
                merged[spec.key] = spec.default_enabled

        dropped = sorted(set(existing) - set(ordered_keys))
        if dropped:
            logger.info(
                "Dropping unknown simulation module keys from settings: %s",
                dropped,
            )

        state.keys = ordered_keys
        state.labels = {spec.key: spec.label for spec in specs}
        state.value = merged

    def iter_enabled_simulation_module_keys(self) -> list[str]:
        """Return registry keys that are currently enabled in settings."""
        state = self.get_state("enabled_simulation_modules")
        if not isinstance(state, BooleanMappingSettingState):
            return []
        return [key for key, enabled in state.value.items() if enabled]

    def build_enabled_simulation_modules(self) -> list["SimulationModuleBase"]:
        """Instantiate the simulation modules currently enabled in settings."""
        from src.simulation.modules.registry import get_module_specs

        enabled_keys = set(self.iter_enabled_simulation_module_keys())
        if not enabled_keys:
            return []
        instances: list["SimulationModuleBase"] = []
        for spec in get_module_specs():
            if spec.key in enabled_keys:
                instances.append(spec.factory())
        return instances

    # ! ==========================================================================================>
    # ! JSON STATE I/O
    # ! ==========================================================================================>

    @classmethod
    def default_state_path(cls) -> Path:
        """Default path used when ``load_state`` / ``save_state`` get no argument."""
        return cls.DEFAULT_OUTPUT_DIRECTORY / cls.DEFAULT_STATE_FILE_NAME

    def load_state(self, path: str | Path | None = None) -> bool:
        """Replace setting values from a JSON file written by :meth:`save_state`.

        Args:
            path: Optional override; defaults to :meth:`default_state_path`.

        Returns:
            ``True`` if a file was found and applied; ``False`` if no file exists.

        Raises:
            ValueError: If the file is malformed or references an unknown setting type.
        """
        target = Path(path) if path is not None else self.default_state_path()
        if not target.exists():
            logger.info("No MidasSettings state file at %s; using defaults", target)
            return False

        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(
                f"MidasSettings state file must contain a JSON object (got {type(raw).__name__})"
            )

        applied = 0
        for name, payload in raw.items():
            if name not in self._states:
                logger.warning(
                    "MidasSettings state file references unknown setting %r; ignoring",
                    name,
                )
                continue
            if not isinstance(payload, dict):
                logger.warning(
                    "MidasSettings state for %r must be an object; ignoring", name
                )
                continue
            try:
                self._states[name] = SettingState.deserialize(payload)
                applied += 1
            except ValueError as exc:
                logger.warning(
                    "Failed to deserialize MidasSettings entry %r: %s", name, exc
                )

        logger.info("Applied %s setting overrides from %s", applied, target)
        self._dirty = False
        return True

    def save_state(self, path: str | Path | None = None) -> Path:
        """Serialize all setting states to a JSON file.

        Args:
            path: Optional override; defaults to :meth:`default_state_path`.

        Returns:
            The path that was written.
        """
        target = Path(path) if path is not None else self.default_state_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {name: state.serialize() for name, state in self._states.items()}
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Wrote MidasSettings state to %s", target)
        self._dirty = False
        return target

    # ! ==========================================================================================>
    # ! BACK-COMPAT HELPERS
    # ! ==========================================================================================>

    @classmethod
    def reset(cls) -> None:
        """Drop and re-initialize the singleton (test-friendly helper)."""
        cls._reset_for_tests()  # type: ignore[attr-defined]


def _check_bounds(
    name: str,
    value: int | float,
    minimum: int | float | None,
    maximum: int | float | None,
) -> None:
    """Validate ``value`` against optional inclusive bounds."""
    if minimum is not None and value < minimum:
        raise ValueError(f"Setting {name!r} value {value} is below minimum {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"Setting {name!r} value {value} is above maximum {maximum}")
