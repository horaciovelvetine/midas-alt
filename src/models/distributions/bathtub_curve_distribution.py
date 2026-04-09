"""Bathtub-shaped hazard curve over normalized asset age."""

from .event_rate_distribution import EventRateDistribution
from .distribution_context import DistributionContext


class BathtubCurveDistribution(EventRateDistribution):
    """Piecewise bathtub hazard over normalized age ratio."""

    def __init__(
        self,
        early_peak_rate: float = 0.7,
        useful_life_rate: float = 0.2,
        wearout_peak_rate: float = 0.9,
        early_end_ratio: float = 0.2,
        wearout_start_ratio: float = 0.8,
        max_ratio: float = 1.5,
    ) -> None:
        """Initialize a bathtub-shaped hazard curve."""
        if not (0 <= early_end_ratio < wearout_start_ratio <= max_ratio):
            raise ValueError("Invalid bathtub ratio boundaries")
        self.early_peak_rate = early_peak_rate
        self.useful_life_rate = useful_life_rate
        self.wearout_peak_rate = wearout_peak_rate
        self.early_end_ratio = early_end_ratio
        self.wearout_start_ratio = wearout_start_ratio
        self.max_ratio = max_ratio

    def rate(self, context: DistributionContext | None = None) -> float:
        """Return event rate from early-life, useful-life, and wearout phases."""
        x = self._resolve_age_ratio(context, max_ratio=self.max_ratio)

        if x <= self.early_end_ratio:
            if self.early_end_ratio == 0:
                return max(0.0, self.useful_life_rate)
            pct = x / self.early_end_ratio
            value = (
                self.early_peak_rate
                + (self.useful_life_rate - self.early_peak_rate) * pct
            )
            return max(0.0, value)

        if x < self.wearout_start_ratio:
            return max(0.0, self.useful_life_rate)

        span = max(1e-9, self.max_ratio - self.wearout_start_ratio)
        pct = (x - self.wearout_start_ratio) / span
        value = (
            self.useful_life_rate
            + (self.wearout_peak_rate - self.useful_life_rate) * pct
        )
        return max(0.0, value)
