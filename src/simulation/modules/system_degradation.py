"""Passive system condition-index degradation for runtime simulation."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from src.enums.entity_type import EntityType
from src.simulation.modules.base import ModuleEvent, SimulationModuleBase
from src.simulation.runtime.clock import TickSize, TickUnit

if TYPE_CHECKING:
    from src.models import System, SystemType
    from src.simulation.runtime.session import SimulationSession

_STATE_ORDER = ("excellent", "good", "fair", "poor", "critical", "failed")

# Fallback curve used when the configurable setting is missing or malformed.
# Mirrors the original hard-coded breakpoints; treat as the documented baseline.
_DEFAULT_AGE_RATIO_RATE_POINTS: tuple[tuple[float, float], ...] = (
    (0.0, 0.012),
    (0.25, 0.02),
    (0.5, 0.05),
    (0.75, 0.09),
    (1.0, 0.18),
    (1.25, 0.32),
    (1.5, 0.55),
)

_EPSILON = 1e-9


class SystemDegradationModule(SimulationModuleBase):
    """Passively degrade systems based on age relative to service life."""

    def __init__(self, seed: int | None = None) -> None:
        """Initialize degradation state and optional deterministic randomness."""
        self._rng = random.Random(seed)
        self._remaining_transition_exposure: dict[str, float] = {}
        self._tracked_states: dict[str, str] = {}

    # ! ======================================================================================================>
    # ! APPLY
    # ! ======================================================================================================>

    def apply(self, session: SimulationSession) -> list[ModuleEvent]:
        """Advance passive system degradation for one simulation tick."""
        tick_years = _tick_size_to_years(session.clock.tick_size)
        if tick_years <= 0:
            return []

        degraded_threshold = float(
            session.settings.get_value("condition_index_degraded_threshold")
        )
        state_multipliers: dict[str, float] = session.settings.get_value(
            "system_degradation_state_rate_multipliers"
        )
        random_annual_chance = float(
            session.settings.get_value("random_system_degradation_chance")
        )
        random_ci_drop = float(
            session.settings.get_value("random_system_degradation_ci_drop")
        )
        random_tick_chance = max(
            0.0, min(1.0, (random_annual_chance / 100.0) * tick_years)
        )
        curve_points = _curve_points_from_setting(
            session.settings.get_value("system_degradation_age_ratio_rate_curve")
        )
        events: list[ModuleEvent] = []

        for system in session.systems:
            system_type = self._resolve_system_type(session, system)
            if system.condition_index is None or system_type is None:
                self._clear_tracking(system.id)
                continue

            random_event = self._maybe_apply_random_degradation(
                system=system,
                system_type=system_type,
                tick_chance=random_tick_chance,
                ci_drop=random_ci_drop,
                degraded_threshold=degraded_threshold,
            )
            if random_event is not None:
                events.append(random_event)

            current_state = _state_from_ci(system.condition_index, degraded_threshold)
            if current_state == "failed":
                self._clear_tracking(system.id)
                continue

            age_months = system.age_months
            life_expectancy_months = system_type.life_expectancy_months

            if age_months is None or life_expectancy_months <= 0:
                self._clear_tracking(system.id)
                continue

            age_ratio = _effective_age_ratio(
                age_months=age_months,
                life_expectancy_months=life_expectancy_months,
                tick_years=tick_years,
                curve_points=curve_points,
            )
            self._sync_tracking(system.id, current_state)
            events.extend(
                self._apply_system_degradation(
                    system=system,
                    system_type=system_type,
                    current_state=current_state,
                    age_ratio=age_ratio,
                    tick_years=tick_years,
                    degraded_threshold=degraded_threshold,
                    state_multipliers=state_multipliers,
                    curve_points=curve_points,
                )
            )

        return events

    # ! ======================================================================================================>
    # ! RANDOM_DEGRADATION_EVENT
    # ! ======================================================================================================>

    def _maybe_apply_random_degradation(
        self,
        system: System,
        system_type: SystemType,
        tick_chance: float,
        ci_drop: float,
        degraded_threshold: float,
    ) -> ModuleEvent | None:
        """Roll an independent per-tick random-degradation event for one system.

        The configured chance is treated as the probability over a 1-year tick and
        scaled linearly to ``tick_chance`` for the current tick. When the roll
        succeeds, ``ci_drop`` points are subtracted from the system's condition
        index (clamped at 0); the exponential exposure tracker for the age-driven
        loop is resampled if the resulting condition band changes.
        """
        if tick_chance <= 0.0 or ci_drop <= 0.0:
            return None
        if system.condition_index is None or system.condition_index <= 0:
            return None
        if self._rng.random() >= tick_chance:
            return None

        previous_ci = system.condition_index
        previous_state = _state_from_ci(previous_ci, degraded_threshold)
        new_ci = round(max(0.0, previous_ci - ci_drop), 2)
        system.condition_index = new_ci
        new_state = _state_from_ci(new_ci, degraded_threshold)

        if new_state != previous_state:
            if new_state == "failed":
                self._clear_tracking(system.id)
            else:
                self._tracked_states[system.id] = new_state
                self._remaining_transition_exposure[system.id] = (
                    self._sample_transition_exposure()
                )

        return ModuleEvent(
            code="system_random_degradation_event",
            message=(
                f"System {system.id} ({system_type.title}) hit by random degradation: "
                f"CI {previous_ci:.2f} -> {new_ci:.2f} "
                f"({previous_state.title()} -> {new_state.title()}, drop {ci_drop:.2f})."
            ),
            entity_id=system.id,
            entity_type=EntityType.SYSTEM,
        )

    # ! ======================================================================================================>
    # ! SYSTEM_DEGRADATION_LOOP
    # ! ======================================================================================================>

    def _apply_system_degradation(
        self,
        system: System,
        system_type: SystemType,
        current_state: str,
        age_ratio: float,
        tick_years: float,
        degraded_threshold: float,
        state_multipliers: dict[str, float],
        curve_points: tuple[tuple[float, float], ...] = _DEFAULT_AGE_RATIO_RATE_POINTS,
    ) -> list[ModuleEvent]:
        """Consume hazard exposure and emit events for any state drops."""
        remaining_years = tick_years
        state = current_state
        events: list[ModuleEvent] = []

        while remaining_years > _EPSILON and state != "failed":
            annual_rate = _annual_transition_rate(
                age_ratio=age_ratio,
                current_state=state,
                state_multipliers=state_multipliers,
                curve_points=curve_points,
            )

            if annual_rate <= 0:
                break

            remaining_exposure = self._remaining_transition_exposure[system.id]
            available_exposure = annual_rate * remaining_years

            if available_exposure + _EPSILON < remaining_exposure:
                self._remaining_transition_exposure[system.id] = (
                    remaining_exposure - available_exposure
                )
                break

            time_to_transition = remaining_exposure / annual_rate
            remaining_years = max(0.0, remaining_years - time_to_transition)
            previous_state = state
            next_state = _next_state_name(state)
            system.condition_index = _next_ci_value(
                current_ci=system.condition_index or 0.0,
                next_state=next_state,
                degraded_threshold=degraded_threshold,
            )
            state = _state_from_ci(system.condition_index, degraded_threshold)
            self._tracked_states[system.id] = state

            if state == "failed":
                self._clear_tracking(system.id)
            else:
                self._remaining_transition_exposure[system.id] = (
                    self._sample_transition_exposure()
                )

            events.append(
                ModuleEvent(
                    code="system_condition_state_declined",
                    message=(
                        f"System {system.id} ({system_type.title}) degraded from "
                        f"{previous_state.title()} to {state.title()} (CI {system.condition_index:.2f})."
                    ),
                    entity_id=system.id,
                    entity_type=EntityType.SYSTEM,
                )
            )

        return events

    # ! ======================================================================================================>
    # ! HELPERS / UTILS
    # ! ======================================================================================================>

    def _resolve_system_type(
        self, session: SimulationSession, system: System
    ) -> SystemType | None:
        """Resolve reference data for a system from the config-data singleton."""
        if system.system_type_key is None:
            return None
        return session.settings.config_data.get_system_type(system.system_type_key)

    def _sync_tracking(self, system_id: str, state: str) -> None:
        """Reset the exposure clock if another process changes the state band."""
        if (
            self._tracked_states.get(system_id) == state
            and system_id in self._remaining_transition_exposure
        ):
            return

        self._tracked_states[system_id] = state
        self._remaining_transition_exposure[system_id] = (
            self._sample_transition_exposure()
        )

    def _clear_tracking(self, system_id: str) -> None:
        """Forget per-system hazard state when degradation cannot proceed."""
        self._remaining_transition_exposure.pop(system_id, None)
        self._tracked_states.pop(system_id, None)

    def _sample_transition_exposure(self) -> float:
        """Sample an exponential waiting-time threshold for the next state drop."""
        sample = max(1e-12, 1.0 - self._rng.random())
        return -math.log(sample)


def _state_from_ci(condition_index: float, degraded_threshold: float) -> str:
    """Map a continuous condition index onto a discrete condition band."""
    if condition_index <= 0:
        return "failed"
    if condition_index <= degraded_threshold:
        return "critical"
    if condition_index < 50:
        return "poor"
    if condition_index < 70:
        return "fair"
    if condition_index < 85:
        return "good"
    return "excellent"


def _tick_size_to_years(tick_size: TickSize) -> float:
    """Convert a tick size into an approximate fraction of a year."""
    if tick_size.unit == TickUnit.DAY:
        return tick_size.amount / 365.25
    if tick_size.unit == TickUnit.WEEK:
        return (tick_size.amount * 7) / 365.25
    if tick_size.unit == TickUnit.MONTH:
        return tick_size.amount / 12.0
    return float(tick_size.amount)


def _effective_age_ratio(
    age_months: int,
    life_expectancy_months: int,
    tick_years: float,
    curve_points: tuple[tuple[float, float], ...] = _DEFAULT_AGE_RATIO_RATE_POINTS,
) -> float:
    """Estimate the average age ratio over the current tick window.

    The result is clamped to the largest configured age-ratio breakpoint in
    ``curve_points`` so callers always land inside the interpolation domain.
    """
    tick_months = tick_years * 12.0
    effective_age_months = max(0.0, age_months - (tick_months / 2.0))
    if life_expectancy_months <= 0:
        return 0.0
    return max(
        0.0,
        min(curve_points[-1][0], effective_age_months / life_expectancy_months),
    )


def _annual_transition_rate(
    age_ratio: float,
    current_state: str,
    state_multipliers: dict[str, float],
    curve_points: tuple[tuple[float, float], ...] = _DEFAULT_AGE_RATIO_RATE_POINTS,
) -> float:
    """Return the annualized state-transition hazard for the current condition band.

    States missing from ``state_multipliers`` (or mapped to a non-positive value)
    short-circuit to ``0.0`` so the caller's loop terminates cleanly. ``failed``
    is intentionally not configurable and falls into this branch. ``curve_points``
    supplies the (age_ratio, base_rate) breakpoints used by the underlying
    interpolation; tests may rely on the ``_DEFAULT_AGE_RATIO_RATE_POINTS``
    fallback.
    """
    multiplier = state_multipliers.get(current_state, 0.0)
    if multiplier <= 0:
        return 0.0
    return _base_transition_rate(age_ratio, curve_points) * multiplier


def _base_transition_rate(
    age_ratio: float,
    curve_points: tuple[tuple[float, float], ...] = _DEFAULT_AGE_RATIO_RATE_POINTS,
) -> float:
    """Interpolate the passive deterioration rate from normalized age."""
    # Passive deterioration accelerates late in life; early-life defects belong in
    # separate fault or maintenance modules rather than this background CI drift.
    clamped_ratio = max(curve_points[0][0], min(curve_points[-1][0], age_ratio))

    for (left_ratio, left_rate), (right_ratio, right_rate) in zip(
        curve_points, curve_points[1:], strict=False
    ):
        if clamped_ratio <= right_ratio:
            span = max(_EPSILON, right_ratio - left_ratio)
            pct = (clamped_ratio - left_ratio) / span
            return left_rate + ((right_rate - left_rate) * pct)

    return curve_points[-1][1]


def _curve_points_from_setting(
    raw_value: object,
) -> tuple[tuple[float, float], ...]:
    """Convert the configured mapping into sorted ``(age_ratio, rate)`` points.

    The setting is stored as ``MappingSettingState`` with stringified age-ratio
    keys (e.g. ``"0.25"``) and float annual-rate values. Entries with non-numeric
    keys are skipped silently. When the resulting curve has fewer than two valid
    breakpoints (the minimum needed for interpolation) the documented default
    curve is used so the module never produces nonsensical hazard rates.
    """
    if not isinstance(raw_value, dict):
        return _DEFAULT_AGE_RATIO_RATE_POINTS

    points: list[tuple[float, float]] = []
    for key, value in raw_value.items():
        try:
            age_ratio = float(key)
            rate = float(value)
        except (TypeError, ValueError):
            continue
        points.append((age_ratio, max(0.0, rate)))

    if len(points) < 2:
        return _DEFAULT_AGE_RATIO_RATE_POINTS

    points.sort(key=lambda item: item[0])
    return tuple(points)


def _next_state_name(current_state: str) -> str:
    """Return the next worse condition state, stopping at failed."""
    index = _STATE_ORDER.index(current_state)
    return _STATE_ORDER[min(len(_STATE_ORDER) - 1, index + 1)]


def _next_ci_value(
    current_ci: float, next_state: str, degraded_threshold: float
) -> float:
    """Project a representative CI value for the next condition band."""
    targets = {
        "excellent": 92.5,
        "good": 77.5,
        "fair": 60.0,
        "poor": (50.0 + degraded_threshold) / 2.0,
        "critical": max(0.5, degraded_threshold / 2.0),
        "failed": 0.0,
    }
    return round(max(0.0, min(current_ci, targets[next_state])), 2)
