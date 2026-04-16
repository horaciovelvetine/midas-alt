"""Facility/System condition index degradation model.

Simulates how a condition index (0-100) changes over time based on:
  1. Base degradation   - natural aging per timestep, scaled to interval
  2. Location stress    - environmental factors (salt air, humidity, etc.)
  3. Weather stress     - per-timestep weather severity (placeholder input)
  4. Deferred backlog   - accumulated deferred maintenance pressure
  5. Maintenance recovery - completed work orders restoring condition
  6. Stochastic noise   - Gaussian noise for realistic variation

The model also tracks discrete Markov-style condition states
(Healthy -> Minor -> Moderate -> Severe -> Failed) derived from
the continuous CI value at each step.

Condition Model Equation (per timestep):
    CI(t+1) = CI(t)
              - base_degradation_per_step * location_factor
              - weather_stress(t) * alpha_weather
              - deferred_backlog(t) * beta_deferred
              + recovery(t) * gamma_recovery
              + noise(t)

    clamped to [0.0, 100.0]
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..location import LocationProfile
from ..timestep import STEPS_PER_YEAR


# ── Discrete Condition States (Markov-style) ─────────────────────────

CONDITION_STATES = ("Healthy", "Minor", "Moderate", "Severe", "Failed")

# Thresholds: CI >= threshold maps to that state
STATE_THRESHOLDS: list[tuple[float, str]] = [
    (80.0, "Healthy"),
    (60.0, "Minor"),
    (40.0, "Moderate"),
    (20.0, "Severe"),
    (0.0, "Failed"),
]


def condition_to_state(condition: float) -> str:
    """Map a continuous condition index to a discrete state.

    Args:
        condition: Condition index value (0-100).

    Returns:
        One of "Healthy", "Minor", "Moderate", "Severe", "Failed".

    """
    for threshold, state in STATE_THRESHOLDS:
        if condition >= threshold:
            return state
    return "Failed"


# Work Order Priority Weights

# Maps maintenance priority (1-4) to impact weight.
# 1 = Critical/Emergency, 4 = Minor/Routine
# Aligned with WorkOrderPriority enum values.
PRIORITY_WEIGHTS: dict[int, float] = {
    1: 20.0,
    2: 15.0,
    3: 10.0,
    4: 5.0,
}


def priority_weight(priority: int) -> float:
    """Return the impact weight for a maintenance priority level.

    Args:
        priority: Priority level 1 (critical) through 4 (minor).

    Returns:
        Numeric weight representing the impact of that priority.

    """
    return PRIORITY_WEIGHTS.get(priority, 0.0)


# Configuration

@dataclass
class ConditionModelConfig:
    """Configuration for the FacilityConditionModel.

    All degradation/recovery parameters are defined here so the model
    itself stays clean. Tweak these values to calibrate the simulation.

    Attributes:
        initial_condition: Starting CI value (0-100).
        annual_base_degradation: How many CI points lost per year from
            pure aging with no other factors. This gets divided by
            steps_per_year to produce the per-step base degradation.
        alpha_location: Sensitivity multiplier for location stress.
            Location stress (0-1) is multiplied by this, then by the
            per-step scaling factor.
        alpha_weather: Sensitivity multiplier for weather stress input.
        beta_deferred: How much each unit of deferred backlog
            accelerates degradation per step.
        gamma_recovery: Multiplier on maintenance recovery amounts.
        noise_std: Standard deviation of per-step Gaussian noise.
        life_expectancy_years: Expected lifespan; used to scale base
            degradation so that CI reaches ~25 at end of life when
            other factors are moderate.

    """

    initial_condition: float = 100.0
    annual_base_degradation: float = 2.0
    alpha_location: float = 3.0
    alpha_weather: float = 5.0
    beta_deferred: float = 0.3
    gamma_recovery: float = 1.0
    noise_std: float = 0.5
    life_expectancy_years: float = 50.0


# Model

class FacilityConditionModel:
    """Simulates condition index degradation over time for a single entity.

    Driven by a TimeStepCounter (external) that determines the interval.
    The model computes per-step degradation by annualizing the base rate
    and scaling all factors to the chosen time interval.

    Usage:
        config = ConditionModelConfig(initial_condition=95.0)
        location = LocationProfile(ocean_proximity=ProximityLevel.IMMEDIATE, ...)
        model = FacilityConditionModel(config=config, location=location, interval="monthly")

        # Each call to step() advances one timestep
        model.step(weather_stress=0.3, deferred_reports=[2, 3], completed_reports=[3])

        # Or run a full series
        results = model.run(weather_series, deferred_series, completed_series)
    """

    def __init__(
        self,
        config: ConditionModelConfig | None = None,
        location: LocationProfile | None = None,
        interval: str = "monthly",
        seed: int | None = None,
    ) -> None:
        """Initialize the condition model.

        Args:
            config: Model parameters. Uses defaults if None.
            location: Environmental location profile. Uses default if None.
            interval: Time interval for stepping ("hourly", "weekly", "monthly", "quarterly").
            seed: Optional random seed for reproducible noise.

        """
        self.config = config or ConditionModelConfig()
        self.location = location or LocationProfile()
        self.interval = interval

        steps_yr = STEPS_PER_YEAR.get(interval, 12.0)
        self._steps_per_year = steps_yr

        # Base degradation per step = annual rate / steps per year
        self._base_deg_per_step = self.config.annual_base_degradation / steps_yr

        # Location is constant obviously lol — multiplicative factor on base aging
        self._location_factor = self.location.degradation_factor

        # Base degradation scaled by location (e.g. HOT_HUMID = 1.25x faster aging)
        self._location_deg_per_step = self._base_deg_per_step * self._location_factor

        # state
        self.condition: float = self.config.initial_condition
        self.deferred_backlog: float = 0.0

        # History
        self.condition_history: list[float] = [self.config.initial_condition]
        self.state_history: list[str] = [condition_to_state(self.config.initial_condition)]
        self.backlog_history: list[float] = [0.0]

        self._rng = np.random.default_rng(seed)

    @property
    def current_state(self) -> str:
        #Return the current discrete condition state
        return condition_to_state(self.condition)

    @property
    def location_factor(self) -> float:
        #Return the location degradation multiplier (1.0 = normal, 1.25 = hot/humid, etc.)
        return self._location_factor

    @property
    def base_degradation_per_step(self) -> float:
        #Return the base degradation amount applied each step
        return self._base_deg_per_step

    def step(
        self,
        weather_stress: float = 0.0,
        deferred_reports: list[int] | None = None,
        completed_reports: list[int] | None = None,
    ) -> float:
        """Advance the model by one timestep.

        Args:
            weather_stress: Weather severity this step (0.0 - 1.0).
                0.0 = calm/benign, 1.0 = extreme weather event.
            deferred_reports: List of priority levels (1-5) for work
                orders that were deferred (not completed) this step.
            completed_reports: List of priority levels (1-5) for work
                orders completed this step.

        Returns:
            The new condition index after this step.

        """
        deferred_reports = deferred_reports or []
        completed_reports = completed_reports or []

        # 1. Update deferred backlog
        for p in deferred_reports:
            self.deferred_backlog += priority_weight(p)

        # 2. Compute recovery from completed maintenance 
        recovery = sum(priority_weight(p) for p in completed_reports)
        recovery *= self.config.gamma_recovery

        # Reduce backlog by recovery (floor at 0)
        self.deferred_backlog = max(0.0, self.deferred_backlog - recovery)

        # 3. Compute total degradation
        # Scale weather by steps_per_year so annual impact is consistent
        weather_deg = (
            weather_stress * self.config.alpha_weather / self._steps_per_year
        )

        degradation = (
            self._location_deg_per_step  # base aging * location multiplier
            + weather_deg                # weather this step
            + self.config.beta_deferred * self.deferred_backlog / self._steps_per_year
        )

        # 4. Stochastic noise
        noise = self._rng.normal(0.0, self.config.noise_std / np.sqrt(self._steps_per_year))

        # 5. Apply condition update
        # Recovery restores CI directly (scaled per step)
        recovery_ci = recovery / self._steps_per_year

        self.condition = self.condition - degradation + recovery_ci + noise
        self.condition = max(0.0, min(100.0, self.condition))

        # 6. Record history
        self.condition_history.append(round(self.condition, 4))
        self.state_history.append(condition_to_state(self.condition))
        self.backlog_history.append(round(self.deferred_backlog, 4))

        return self.condition

    def run(
        self,
        weather_series: list[float],
        deferred_series: list[list[int]],
        completed_series: list[list[int]],
    ) -> dict:
        """Run the model for a full time series.

        All input lists must be the same length (one entry per timestep).

        Args:
            weather_series: Weather stress per step (0.0 - 1.0 each).
            deferred_series: Deferred work order priorities per step.
            completed_series: Completed work order priorities per step.

        Returns:
            Dict with keys:
                condition_history: list[float]
                state_history: list[str]
                backlog_history: list[float]

        """
        n = len(weather_series)
        if len(deferred_series) != n or len(completed_series) != n:
            raise ValueError(
                f"All series must have the same length. Got weather={n}, "
                f"deferred={len(deferred_series)}, completed={len(completed_series)}"
            )

        for t in range(n):
            self.step(
                weather_stress=weather_series[t],
                deferred_reports=deferred_series[t],
                completed_reports=completed_series[t],
            )

        return {
            "condition_history": self.condition_history,
            "state_history": self.state_history,
            "backlog_history": self.backlog_history,
        }

    def reset(self) -> None:
        """Reset the model to its initial state."""
        self.condition = self.config.initial_condition
        self.deferred_backlog = 0.0
        self.condition_history = [self.config.initial_condition]
        self.state_history = [condition_to_state(self.config.initial_condition)]
        self.backlog_history = [0.0]
