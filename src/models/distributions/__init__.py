"""Re-export distribution protocols and concrete curve/segment implementations."""

from .bathtub_curve_distribution import BathtubCurveDistribution
from .distribution_base import DistributionBase
from .distribution_context import DistributionContext
from .event_rate_distribution import EventRateDistribution
from .normal_curve_distribution import NormalCurveDistribution
from .piecewise_curve_distribution import PiecewiseCurveDistribution
from .weighted_probability_distribution import WeightedProbabilityDistribution
from .weighted_probability_segment import WeightedProbabilitySegment

_DISTRIBUTION_REGISTRY: dict[str, type] = {
    "WeightedProbabilityDistribution": WeightedProbabilityDistribution,
    "BathtubCurveDistribution": BathtubCurveDistribution,
    "NormalCurveDistribution": NormalCurveDistribution,
    "PiecewiseCurveDistribution": PiecewiseCurveDistribution,
}


def distribution_from_dict(data: dict) -> DistributionBase:
    """Reconstruct a distribution from a dict produced by its ``to_dict`` method.

    Args:
        data: A dict with a ``distribution_type`` key matching a known class name.

    Returns:
        The reconstructed distribution instance.

    Raises:
        ValueError: If ``distribution_type`` is missing or unrecognised.

    """
    dist_type = data.get("distribution_type")
    cls = _DISTRIBUTION_REGISTRY.get(dist_type) if dist_type else None
    if cls is None:
        raise ValueError(f"Unknown distribution type: {dist_type!r}")
    return cls.from_dict(data)


__all__ = [
    "DistributionBase",
    "DistributionContext",
    "EventRateDistribution",
    "WeightedProbabilitySegment",
    "WeightedProbabilityDistribution",
    "NormalCurveDistribution",
    "BathtubCurveDistribution",
    "PiecewiseCurveDistribution",
    "distribution_from_dict",
]
