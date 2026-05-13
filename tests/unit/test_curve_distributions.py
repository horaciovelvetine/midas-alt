"""Unit tests for normal and piecewise curve distributions."""

from __future__ import annotations

import math

import pytest

from src.models.distributions import (
    BathtubCurveDistribution,
    NormalCurveDistribution,
    PiecewiseCurveDistribution,
)
from src.models.distributions.distribution_context import DistributionContext

# ! ==========================================================================================>
# ! NormalCurveDistribution
# ! ==========================================================================================>


def test_normal_distribution_rejects_zero_or_negative_stddev() -> None:
    """A non-positive ``stddev`` is rejected at construction time."""
    with pytest.raises(ValueError, match="stddev"):
        NormalCurveDistribution(stddev=0)
    with pytest.raises(ValueError, match="stddev"):
        NormalCurveDistribution(stddev=-0.1)


def test_normal_distribution_rate_peaks_at_mean() -> None:
    """Peak rate is reached at ``mean`` (``baseline_rate + amplitude``)."""
    distribution = NormalCurveDistribution(
        baseline_rate=0.2, amplitude=1.0, mean=0.5, stddev=0.1
    )
    context = DistributionContext(age_years=5, life_expectancy_years=10)
    assert distribution.rate(context) == pytest.approx(1.2)


def test_normal_distribution_rate_decays_away_from_mean() -> None:
    """Two-sigma offset yields ``baseline_rate + amplitude * e^{-2}``."""
    distribution = NormalCurveDistribution(
        baseline_rate=0.0, amplitude=1.0, mean=0.5, stddev=0.1
    )
    context = DistributionContext(age_years=7, life_expectancy_years=10)
    assert distribution.rate(context) == pytest.approx(math.exp(-2.0))


def test_normal_distribution_uses_default_age_ratio_when_context_missing() -> None:
    """Without a context, ``rate`` falls back to the default age ratio (0.5)."""
    distribution = NormalCurveDistribution(
        baseline_rate=0.0, amplitude=1.0, mean=0.5, stddev=0.1
    )
    assert distribution.rate() == pytest.approx(1.0)


def test_normal_distribution_round_trips_through_dict() -> None:
    """``to_dict`` / ``from_dict`` preserve all parameters."""
    distribution = NormalCurveDistribution(
        baseline_rate=0.3, amplitude=0.6, mean=0.4, stddev=0.25
    )
    payload = distribution.to_dict()
    assert payload["distribution_type"] == "NormalCurveDistribution"
    restored = NormalCurveDistribution.from_dict(payload)
    assert restored.baseline_rate == 0.3
    assert restored.amplitude == 0.6
    assert restored.mean == 0.4
    assert restored.stddev == 0.25


# ! ==========================================================================================>
# ! PiecewiseCurveDistribution
# ! ==========================================================================================>


def test_piecewise_requires_at_least_two_points() -> None:
    """One-point curves are rejected."""
    with pytest.raises(ValueError, match="at least two points"):
        PiecewiseCurveDistribution([(0.0, 0.5)])


def test_piecewise_rejects_zero_x_span() -> None:
    """All points sharing an x value are rejected."""
    with pytest.raises(ValueError, match="non-zero x-range"):
        PiecewiseCurveDistribution([(0.5, 0.1), (0.5, 0.9)])


def test_piecewise_sorts_points_by_x_on_construction() -> None:
    """Constructor stores points in ascending ``x`` order regardless of input."""
    distribution = PiecewiseCurveDistribution([(1.0, 0.3), (0.0, 0.0), (0.5, 0.1)])
    assert distribution.points == [(0.0, 0.0), (0.5, 0.1), (1.0, 0.3)]


def test_piecewise_clamps_below_first_point_and_above_last_point() -> None:
    """``rate`` returns the first/last y for x outside the curve range."""
    distribution = PiecewiseCurveDistribution([(0.2, 0.3), (0.8, 0.9)])
    below = DistributionContext(age_years=0, life_expectancy_years=10)
    above = DistributionContext(age_years=15, life_expectancy_years=10)
    assert distribution.rate(below) == pytest.approx(0.3)
    assert distribution.rate(above) == pytest.approx(0.9)


def test_piecewise_interpolates_between_neighbors() -> None:
    """``rate`` linearly interpolates between two adjacent control points."""
    distribution = PiecewiseCurveDistribution([(0.0, 0.0), (1.0, 1.0)])
    midpoint = DistributionContext(age_years=5, life_expectancy_years=10)
    assert distribution.rate(midpoint) == pytest.approx(0.5)


def test_piecewise_clamps_negative_rate_to_zero() -> None:
    """Negative interpolated values are clamped to ``0.0`` for safety."""
    distribution = PiecewiseCurveDistribution([(0.0, -1.0), (1.0, -0.5)])
    context = DistributionContext(age_years=5, life_expectancy_years=10)
    assert distribution.rate(context) == 0.0


def test_piecewise_round_trips_through_dict() -> None:
    """``to_dict`` / ``from_dict`` preserve points list verbatim."""
    distribution = PiecewiseCurveDistribution([(0.0, 0.2), (0.5, 0.7), (1.0, 1.4)])
    payload = distribution.to_dict()
    assert payload["distribution_type"] == "PiecewiseCurveDistribution"
    restored = PiecewiseCurveDistribution.from_dict(payload)
    assert restored.points == distribution.points


# ! ==========================================================================================>
# ! BathtubCurveDistribution
# ! ==========================================================================================>


def test_bathtub_rejects_invalid_ratio_ordering() -> None:
    """Bathtub ratios must satisfy ``0 <= early_end < wearout_start <= max``."""
    with pytest.raises(ValueError, match="boundaries"):
        BathtubCurveDistribution(
            early_end_ratio=0.5, wearout_start_ratio=0.4, max_ratio=1.0
        )


def test_bathtub_interpolates_in_early_phase() -> None:
    """The early phase linearly drops from ``early_peak_rate`` to ``useful_life_rate``."""
    distribution = BathtubCurveDistribution(
        early_peak_rate=0.8,
        useful_life_rate=0.2,
        wearout_peak_rate=1.0,
        early_end_ratio=0.2,
        wearout_start_ratio=0.8,
        max_ratio=1.5,
    )
    context = DistributionContext(age_years=1, life_expectancy_years=10)
    assert distribution.rate(context) == pytest.approx(0.5)


def test_bathtub_useful_life_flat() -> None:
    """Within the useful-life band, the rate equals ``useful_life_rate``."""
    distribution = BathtubCurveDistribution()
    context = DistributionContext(age_years=5, life_expectancy_years=10)
    assert distribution.rate(context) == pytest.approx(distribution.useful_life_rate)


def test_bathtub_wearout_increases_toward_peak() -> None:
    """The wear-out phase ramps from useful-life-rate to wearout-peak-rate."""
    distribution = BathtubCurveDistribution(
        early_peak_rate=0.8,
        useful_life_rate=0.2,
        wearout_peak_rate=1.0,
        early_end_ratio=0.2,
        wearout_start_ratio=0.5,
        max_ratio=1.0,
    )
    midpoint = DistributionContext(age_years=75, life_expectancy_years=100)
    assert distribution.rate(midpoint) == pytest.approx(0.6)
