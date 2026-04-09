"""Piecewise-linear event rates over age ratio control points."""

from .event_rate_distribution import EventRateDistribution
from .distribution_context import DistributionContext


class PiecewiseCurveDistribution(EventRateDistribution):
    """Linear interpolation over arbitrary (age_ratio, rate) points."""

    def __init__(self, points: list[tuple[float, float]]) -> None:
        """Initialize piecewise linear curve with sorted points."""
        if len(points) < 2:
            raise ValueError("PiecewiseCurveDistribution requires at least two points")
        self.points = sorted(points, key=lambda p: p[0])
        if self.points[0][0] == self.points[-1][0]:
            raise ValueError("Piecewise points must span a non-zero x-range")

    def rate(self, context: DistributionContext | None = None) -> float:
        """Return interpolated event rate for the current age ratio."""
        x = self._resolve_age_ratio(context)
        if x <= self.points[0][0]:
            return max(0.0, self.points[0][1])
        if x >= self.points[-1][0]:
            return max(0.0, self.points[-1][1])

        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:], strict=False):
            if x0 <= x <= x1:
                span = max(1e-9, x1 - x0)
                pct = (x - x0) / span
                return max(0.0, y0 + (y1 - y0) * pct)
        return max(0.0, self.points[-1][1])
