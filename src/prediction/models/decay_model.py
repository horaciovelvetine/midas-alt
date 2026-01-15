"""Exponential decay model for degradation prediction.

This is the analytical baseline model based on the PERT decay formula:
CI(t) = CI_0 * (1 - R)^t

Where:
- CI_0 is the initial condition index (assumed 99.99)
- R is the monthly decay rate
- t is time in months
"""

import math

import numpy as np
import pandas as pd

from .base import DegradationModel, Prediction


class ExponentialDecayModel(DegradationModel):
    """Analytical exponential decay model for degradation prediction.

    This model doesn't require training - it calculates decay rate from
    current condition and age, then projects forward to find when CI
    will fall below the degradation threshold.

    This serves as a baseline to compare ML models against.
    """

    def __init__(
        self,
        initial_ci: float = 99.99,
        degradation_threshold: float = 25.0,
    ):
        """Initialize the decay model.

        Args:
            initial_ci: Assumed initial condition index for all entities.
            degradation_threshold: CI value below which entity is degraded.
        """
        self.initial_ci = initial_ci
        self.degradation_threshold = degradation_threshold

    @property
    def name(self) -> str:
        return "exponential_decay"

    @property
    def requires_training(self) -> bool:
        """This model doesn't require training."""
        return False

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ExponentialDecayModel":
        """No-op for analytical model."""
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict months to degradation using exponential decay formula.

        Required columns in X:
        - condition_index: Current CI value
        - age_months: Current age in months

        Args:
            X: Feature DataFrame.

        Returns:
            Array of predicted months to degradation.
        """
        predictions = []

        for _, row in X.iterrows():
            current_ci = row.get("condition_index", 50)
            age_months = row.get("age_months", 0)

            months_to_degrade = self._calculate_months_to_degradation(
                current_ci, age_months
            )
            predictions.append(months_to_degrade)

        return np.array(predictions)

    def predict_with_uncertainty(
        self, X: pd.DataFrame, confidence: float = 0.8
    ) -> list[Prediction]:
        """Predict with uncertainty based on decay rate variance.

        For the analytical model, we estimate uncertainty by varying
        the decay rate assumption.
        """
        predictions = []

        for _, row in X.iterrows():
            current_ci = row.get("condition_index", 50)
            age_months = row.get("age_months", 0)

            # Central prediction
            months = self._calculate_months_to_degradation(current_ci, age_months)

            # Uncertainty bounds (faster/slower decay scenarios)
            decay_rate = self._calculate_decay_rate(current_ci, age_months)

            if decay_rate and decay_rate > 0:
                # Faster decay (higher rate) = sooner degradation
                fast_decay = decay_rate * 1.5
                slow_decay = decay_rate * 0.5

                months_fast = self._months_until_threshold(current_ci, fast_decay)
                months_slow = self._months_until_threshold(current_ci, slow_decay)

                predictions.append(
                    Prediction(
                        months_to_degradation=months,
                        confidence_low=months_fast,
                        confidence_high=months_slow,
                        predicted_trajectory=self._generate_trajectory(
                            current_ci, decay_rate, int(months)
                        ),
                    )
                )
            else:
                # No decay - use large value with wide bounds
                predictions.append(
                    Prediction(
                        months_to_degradation=months,
                        confidence_low=months * 0.5,
                        confidence_high=months * 2.0,
                    )
                )

        return predictions

    def _calculate_decay_rate(
        self, current_ci: float, age_months: int
    ) -> float | None:
        """Calculate monthly decay rate from current state.

        Formula: R = 1 - (CI_current / CI_initial)^(1/age)

        Args:
            current_ci: Current condition index.
            age_months: Age in months.

        Returns:
            Monthly decay rate, or None if cannot be calculated.
        """
        if age_months <= 0:
            return None

        if current_ci <= 0 or self.initial_ci <= 0:
            return None

        ratio = current_ci / self.initial_ci
        if ratio <= 0 or ratio >= 1:
            return None

        try:
            decay_rate = 1 - ratio ** (1 / age_months)
            return decay_rate if decay_rate > 0 else None
        except (ValueError, ZeroDivisionError):
            return None

    def _calculate_months_to_degradation(
        self, current_ci: float, age_months: int
    ) -> float:
        """Calculate months until CI falls below threshold.

        Args:
            current_ci: Current condition index.
            age_months: Current age in months.

        Returns:
            Predicted months until degradation (0 if already degraded,
            large value if decay rate is zero/negative).
        """
        # Already degraded
        if current_ci <= self.degradation_threshold:
            return 0.0

        decay_rate = self._calculate_decay_rate(current_ci, age_months)

        if decay_rate is None or decay_rate <= 0:
            # No degradation trend - return large value
            return 999.0

        return self._months_until_threshold(current_ci, decay_rate)

    def _months_until_threshold(self, current_ci: float, decay_rate: float) -> float:
        """Calculate months until CI reaches threshold given decay rate.

        Formula: months = log(threshold / current_ci) / log(1 - decay_rate)
        """
        if decay_rate >= 1.0 or decay_rate <= 0:
            return 999.0

        if current_ci <= self.degradation_threshold:
            return 0.0

        try:
            months = math.log(self.degradation_threshold / current_ci) / math.log(
                1 - decay_rate
            )
            return max(0, months)
        except (ValueError, ZeroDivisionError):
            return 999.0

    def _generate_trajectory(
        self, current_ci: float, decay_rate: float, months_ahead: int
    ) -> list[tuple[int, float]]:
        """Generate predicted CI trajectory.

        Args:
            current_ci: Starting condition index.
            decay_rate: Monthly decay rate.
            months_ahead: How many months to project.

        Returns:
            List of (month_offset, predicted_ci) tuples.
        """
        trajectory = [(0, current_ci)]
        ci = current_ci

        for month in range(1, min(months_ahead + 1, 121)):  # Cap at 10 years
            ci = ci * (1 - decay_rate)
            trajectory.append((month, round(ci, 2)))

            if ci <= self.degradation_threshold:
                break

        return trajectory
