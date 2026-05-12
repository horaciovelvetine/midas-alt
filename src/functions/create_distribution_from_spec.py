"""Construct distribution instances from declarative workbook-style specs."""

from typing import Any

from src.models.distributions import (
    DistributionBase,
    WeightedProbabilitySegment,
    WeightedProbabilityDistribution,
    NormalCurveDistribution,
    BathtubCurveDistribution,
    PiecewiseCurveDistribution,
)


def create_distribution_from_spec(spec: dict[str, Any]) -> DistributionBase:
    """Build a ``DistributionBase`` subclass from ``spec`` (requires ``type`` key).

    Supported ``type`` values:

    - ``segments``: ``WeightedProbabilityDistribution`` from ``segments`` list.
    - ``normal``: ``NormalCurveDistribution`` from ``baseline_rate``, ``amplitude``,
      ``mean``, ``stddev``.
    - ``bathtub``: ``BathtubCurveDistribution`` from rate/ratio keys such as
      ``early_peak_rate``, ``useful_life_rate``, ``wearout_peak_rate``,
      ``early_end_ratio``, ``wearout_start_ratio``, ``max_ratio``.
    - ``piecewise``: ``PiecewiseCurveDistribution`` from ``points`` as ``(x, y)`` pairs.

    Args:
        spec: Declarative distribution description (must include ``type``).

    Returns:
        Instantiated distribution for the given spec.

    Raises:
        ValueError: If ``type`` is missing or not supported.
    """
    dist_type = str(spec.get("type", "")).strip().lower()
    if dist_type == "segments":
        raw_segments = spec.get("segments", [])
        segments = [
            WeightedProbabilitySegment(int(item["percentage"]), str(item["value"]))
            for item in raw_segments
        ]
        return WeightedProbabilityDistribution(segments)

    # Default values for these distributions...
    if dist_type == "normal":
        return NormalCurveDistribution(
            baseline_rate=float(spec.get("baseline_rate", 0.1)),
            amplitude=float(spec.get("amplitude", 0.5)),
            mean=float(spec.get("mean", 0.5)),
            stddev=float(spec.get("stddev", 0.2)),
        )

    if dist_type == "bathtub":
        return BathtubCurveDistribution(
            early_peak_rate=float(spec.get("early_peak_rate", 0.7)),
            useful_life_rate=float(spec.get("useful_life_rate", 0.2)),
            wearout_peak_rate=float(spec.get("wearout_peak_rate", 0.9)),
            early_end_ratio=float(spec.get("early_end_ratio", 0.2)),
            wearout_start_ratio=float(spec.get("wearout_start_ratio", 0.8)),
            max_ratio=float(spec.get("max_ratio", 1.5)),
        )

    if dist_type == "piecewise":
        points = [(float(x), float(y)) for x, y in spec.get("points", [])]
        return PiecewiseCurveDistribution(points=points)

    raise ValueError(f"Unknown distribution type '{dist_type}'")
