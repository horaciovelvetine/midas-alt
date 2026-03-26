"""Passive system condition-index degradation for runtime simulation."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from ...enums.entity_type import EntityType
from ..runtime.clock import TickSize, TickUnit
from .base import Base, ModuleEvent

if TYPE_CHECKING:
    from ...config.reference_data import SystemType
    from ...models import System
    from ..runtime.session import SimulationSession

_STATE_ORDER = ("excellent", "good", "fair", "poor", "critical", "failed")
_STATE_RATE_MULTIPLIERS = {
    "excellent": 0.9,
    "good": 1.0,
    "fair": 1.15,
    "poor": 1.3,
    "critical": 1.65,
    "failed": 0.0,
}
_AGE_RATIO_RATE_POINTS = (
    (0.0, 0.012),
    (0.25, 0.02),
    (0.5, 0.05),
    (0.75, 0.09),
    (1.0, 0.18),
    (1.25, 0.32),
    (1.5, 0.55),
)
_EPSILON = 1e-9


class SystemDegradationModule(Base):
    """Passively degrade systems based on age relative to service life."""

    def __init__(self, seed: int | None = None) -> None:
        """Initialize degradation state and optional deterministic randomness."""
        self._rng = random.Random(seed)
        self._remaining_transition_exposure: dict[str, float] = {}
        self._tracked_states: dict[str, str] = {}

    def apply(self, session: SimulationSession) -> list[ModuleEvent]:
        """Advance passive system degradation for one simulation tick."""
        tick_years = _tick_size_to_years(session.clock.tick_size)
        if tick_years <= 0:
            return []

        degraded_threshold = (
            session.settings.degradation.condition_index_degraded_threshold
        )
        events: list[ModuleEvent] = []

        for system in session.systems:
            system_type = self._resolve_system_type(session, system)
            if system.condition_index is None or system_type is None:
                self._clear_tracking(system.id)
                continue

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
                )
            )

        return events

    def _apply_system_degradation(
        self,
        system: System,
        system_type: SystemType,
        current_state: str,
        age_ratio: float,
        tick_years: float,
        degraded_threshold: float,
    ) -> list[ModuleEvent]:
        """Consume hazard exposure and emit events for any state drops."""
        remaining_years = tick_years
        state = current_state
        events: list[ModuleEvent] = []

        while remaining_years > _EPSILON and state != "failed":
            annual_rate = _annual_transition_rate(
                age_ratio=age_ratio, current_state=state
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
        """Resolve reference data for a system from session settings."""
        if system.system_type_key is None:
            return None
        return session.settings.get_system_type(system.system_type_key)

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
    age_months: int, life_expectancy_months: int, tick_years: float
) -> float:
    """Estimate the average age ratio over the current tick window."""
    tick_months = tick_years * 12.0
    effective_age_months = max(0.0, age_months - (tick_months / 2.0))
    if life_expectancy_months <= 0:
        return 0.0
    return max(
        0.0,
        min(
            _AGE_RATIO_RATE_POINTS[-1][0], effective_age_months / life_expectancy_months
        ),
    )


def _annual_transition_rate(age_ratio: float, current_state: str) -> float:
    """Return the annualized state-transition hazard for the current condition band."""
    return _base_transition_rate(age_ratio) * _STATE_RATE_MULTIPLIERS[current_state]


def _base_transition_rate(age_ratio: float) -> float:
    """Interpolate the passive deterioration rate from normalized age."""
    # Passive deterioration accelerates late in life; early-life defects belong in
    # separate fault or maintenance modules rather than this background CI drift.
    clamped_ratio = max(
        _AGE_RATIO_RATE_POINTS[0][0], min(_AGE_RATIO_RATE_POINTS[-1][0], age_ratio)
    )

    for (left_ratio, left_rate), (right_ratio, right_rate) in zip(
        _AGE_RATIO_RATE_POINTS, _AGE_RATIO_RATE_POINTS[1:], strict=False
    ):
        if clamped_ratio <= right_ratio:
            span = max(_EPSILON, right_ratio - left_ratio)
            pct = (clamped_ratio - left_ratio) / span
            return left_rate + ((right_rate - left_rate) * pct)

    return _AGE_RATIO_RATE_POINTS[-1][1]


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
