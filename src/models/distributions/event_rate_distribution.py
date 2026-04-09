"""Event-rate distributions with expected counts and Poisson sampling."""

from .distribution_base import DistributionBase
from .distribution_context import DistributionContext


class EventRateDistribution(DistributionBase):
    """Base class for curve distributions that model event rates."""

    def expected_events(
        self, context: DistributionContext | None = None, horizon_years: float = 1.0
    ) -> float:
        """Return expected event count over the horizon."""
        return max(0.0, self.rate(context) * max(0.0, horizon_years))

    def rate(self, context: DistributionContext | None = None) -> float:
        """Return instantaneous event rate for the given context."""
        raise NotImplementedError

    def sample(self, context: DistributionContext | None = None) -> float:
        """Sample event rate for compatibility with BaseDistribution."""
        return self.rate(context)

    def sample_count(
        self, context: DistributionContext | None = None, horizon_years: float = 1.0
    ) -> int:
        """Sample an integer count using a Poisson process."""
        lam = self.expected_events(context=context, horizon_years=horizon_years)
        return self._sample_poisson(lam)
