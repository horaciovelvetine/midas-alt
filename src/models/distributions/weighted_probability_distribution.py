"""Discrete distribution defined by percentage-weighted segments."""

import random

from .distribution_base import DistributionBase
from .weighted_probability_segment import WeightedProbabilitySegment
from .distribution_context import DistributionContext


class WeightedProbabilityDistribution(DistributionBase):
    """Represents a probability distribution with weighted segments."""

    def __init__(self, segments: list[WeightedProbabilitySegment]) -> None:
        """Initialize with one or more weighted segments."""
        if not segments:
            raise ValueError(
                "WeightedProbabilityDistribution must have at least one segment"
            )
        self._segments = segments

    def get_total_percentage(self) -> int:
        """Return the sum of segment percentages."""
        return sum(segment._percentage for segment in self._segments)

    def percentages_exceed_100(self) -> bool:
        """Return whether cumulative percentage exceeds 100."""
        return self.get_total_percentage() > 100

    @property
    def segments(self) -> list[WeightedProbabilitySegment]:
        """Return configured probability segments."""
        return self._segments

    def select_random_segment(self) -> WeightedProbabilitySegment:
        """Choose a segment using normalized weighted sampling."""
        rand = random.random()
        cumulative = 0.0

        total = sum(segment._percentage for segment in self._segments)
        factor = 100.0 / total if total != 0 else 1.0

        for segment in self._segments:
            normalized = (segment._percentage * factor) / 100.0
            cumulative += normalized

            if rand < cumulative:
                return segment

        return self._segments[-1]

    def sample(self, context: DistributionContext | None = None) -> float | str:
        """Sample a value using weighted segment selection."""
        del context
        return self.select_random_segment().sample()

    def __str__(self) -> str:
        """Return a readable representation for diagnostics."""
        segments_str = ",\n".join("\t" + str(s) for s in self._segments)
        return f"WeightedProbabilityDistribution(segments=[\n{segments_str}])"
