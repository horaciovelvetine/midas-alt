"""Base classes and protocols for degradation prediction models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Prediction:
    """A degradation prediction with uncertainty bounds.

    Attributes:
        months_to_degradation: Predicted months until condition index
                               falls below the degradation threshold.
        confidence_low: Lower bound of prediction (e.g., 10th percentile).
        confidence_high: Upper bound of prediction (e.g., 90th percentile).
        predicted_trajectory: Optional list of (month_offset, predicted_ci) tuples
                             showing the expected degradation path.
    """

    months_to_degradation: float
    confidence_low: float
    confidence_high: float
    predicted_trajectory: list[tuple[int, float]] | None = None

    @property
    def years_to_degradation(self) -> float:
        """Get prediction in years."""
        return self.months_to_degradation / 12

    def is_imminent(self, threshold_months: int = 12) -> bool:
        """Check if degradation is predicted within threshold."""
        return self.months_to_degradation <= threshold_months


class DegradationModel(ABC):
    """Abstract base class for degradation prediction models.

    All prediction models must implement this interface to be used
    in the evaluation and comparison framework.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return a unique identifier for this model."""
        pass

    @property
    def requires_training(self) -> bool:
        """Whether this model requires training data.

        Override to return False for analytical models (like ExponentialDecay).
        """
        return True

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "DegradationModel":
        """Train the model on labeled data.

        Args:
            X: Feature DataFrame with columns matching DegradationFeatures.
            y: Target Series with months_to_degradation values.

        Returns:
            self for method chaining.
        """
        pass

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict months to degradation for each sample.

        Args:
            X: Feature DataFrame.

        Returns:
            Array of predicted months to degradation.
        """
        pass

    def predict_with_uncertainty(
        self, X: pd.DataFrame, confidence: float = 0.8
    ) -> list[Prediction]:
        """Predict with confidence intervals.

        Default implementation returns symmetric intervals based on
        a simple heuristic. Override for model-specific uncertainty.

        Args:
            X: Feature DataFrame.
            confidence: Confidence level (e.g., 0.8 for 80% interval).

        Returns:
            List of Prediction objects with uncertainty bounds.
        """
        predictions = self.predict(X)
        margin = (1 - confidence) / 2

        results = []
        for pred in predictions:
            # Simple symmetric interval (override for better uncertainty)
            results.append(
                Prediction(
                    months_to_degradation=float(pred),
                    confidence_low=float(pred * (1 - margin * 2)),
                    confidence_high=float(pred * (1 + margin * 2)),
                )
            )

        return results

    def score(self, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
        """Compute evaluation metrics.

        Args:
            X: Feature DataFrame.
            y: True months to degradation.

        Returns:
            Dictionary of metric name -> value.
        """
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

        y_pred = self.predict(X)

        return {
            "mae": mean_absolute_error(y, y_pred),
            "rmse": np.sqrt(mean_squared_error(y, y_pred)),
            "r2": r2_score(y, y_pred),
            "within_6mo": np.mean(np.abs(y - y_pred) <= 6),
            "within_12mo": np.mean(np.abs(y - y_pred) <= 12),
        }
