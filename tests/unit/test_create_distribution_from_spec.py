"""Unit tests for ``create_distribution_from_spec`` dispatch."""

from __future__ import annotations

import pytest

from src.functions.create_distribution_from_spec import create_distribution_from_spec
from src.models.distributions import (
    BathtubCurveDistribution,
    NormalCurveDistribution,
    PiecewiseCurveDistribution,
    WeightedProbabilityDistribution,
)


def test_segments_spec_returns_weighted_probability_distribution() -> None:
    """A ``segments`` spec produces a ``WeightedProbabilityDistribution``."""
    spec = {
        "type": "segments",
        "segments": [
            {"percentage": 30, "value": "low"},
            {"percentage": 70, "value": "high"},
        ],
    }
    distribution = create_distribution_from_spec(spec)

    assert isinstance(distribution, WeightedProbabilityDistribution)
    assert [s.weight_percent for s in distribution.segments] == [30, 70]
    assert [s.value for s in distribution.segments] == ["low", "high"]


def test_normal_spec_uses_provided_parameters() -> None:
    """A ``normal`` spec wires parameters through to ``NormalCurveDistribution``."""
    spec = {
        "type": "normal",
        "baseline_rate": 0.25,
        "amplitude": 1.5,
        "mean": 0.7,
        "stddev": 0.15,
    }
    distribution = create_distribution_from_spec(spec)

    assert isinstance(distribution, NormalCurveDistribution)
    assert distribution.baseline_rate == 0.25
    assert distribution.amplitude == 1.5
    assert distribution.mean == 0.7
    assert distribution.stddev == 0.15


def test_normal_spec_falls_back_to_defaults_when_unspecified() -> None:
    """A bare ``normal`` spec uses documented defaults."""
    distribution = create_distribution_from_spec({"type": "normal"})

    assert isinstance(distribution, NormalCurveDistribution)
    assert distribution.baseline_rate == 0.1
    assert distribution.amplitude == 0.5
    assert distribution.mean == 0.5
    assert distribution.stddev == 0.2


def test_bathtub_spec_builds_bathtub_distribution() -> None:
    """A ``bathtub`` spec is dispatched to ``BathtubCurveDistribution``."""
    spec = {
        "type": "bathtub",
        "early_peak_rate": 0.6,
        "useful_life_rate": 0.1,
        "wearout_peak_rate": 1.2,
        "early_end_ratio": 0.15,
        "wearout_start_ratio": 0.85,
        "max_ratio": 2.0,
    }
    distribution = create_distribution_from_spec(spec)

    assert isinstance(distribution, BathtubCurveDistribution)
    assert distribution.early_peak_rate == 0.6
    assert distribution.useful_life_rate == 0.1
    assert distribution.wearout_peak_rate == 1.2
    assert distribution.max_ratio == 2.0


def test_piecewise_spec_produces_sorted_points() -> None:
    """A ``piecewise`` spec is dispatched and the points are normalized."""
    spec = {
        "type": "piecewise",
        "points": [[0.0, 0.5], [1.0, 1.5], [0.5, 1.0]],
    }
    distribution = create_distribution_from_spec(spec)

    assert isinstance(distribution, PiecewiseCurveDistribution)
    assert distribution.points == [(0.0, 0.5), (0.5, 1.0), (1.0, 1.5)]


def test_unknown_type_raises_value_error() -> None:
    """An unrecognized ``type`` value raises ``ValueError``."""
    with pytest.raises(ValueError, match="Unknown distribution type"):
        create_distribution_from_spec({"type": "exotic"})


def test_missing_type_is_treated_as_unknown() -> None:
    """A spec without ``type`` is treated as unknown and raises."""
    with pytest.raises(ValueError, match="Unknown distribution type"):
        create_distribution_from_spec({})


def test_type_is_case_and_whitespace_insensitive() -> None:
    """Type strings are stripped and lowercased before dispatch."""
    distribution = create_distribution_from_spec({"type": "  Normal  "})
    assert isinstance(distribution, NormalCurveDistribution)
