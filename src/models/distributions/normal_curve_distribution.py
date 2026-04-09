"""Bell-shaped event rate over normalized age ratio."""

import math
from .event_rate_distribution import EventRateDistribution
from .distribution_context import DistributionContext


class NormalCurveDistribution(EventRateDistribution):
    """Bell curve over normalized age ratio."""

    def __init__(
        self,
        baseline_rate: float = 0.1,
        amplitude: float = 0.5,
        mean: float = 0.5,
        stddev: float = 0.2,
    ) -> None:
        """Initialize a Gaussian-shaped event-rate curve."""
        if stddev <= 0:
            raise ValueError("stddev must be > 0")
        self.baseline_rate = baseline_rate
        self.amplitude = amplitude
        self.mean = mean
        self.stddev = stddev

    def rate(self, context: DistributionContext | None = None) -> float:
        """Return event rate based on Gaussian age-ratio response."""
        x = self._resolve_age_ratio(context)
        z = (x - self.mean) / self.stddev
        bell = math.exp(-0.5 * z * z)
        return max(0.0, self.baseline_rate + (self.amplitude * bell))
