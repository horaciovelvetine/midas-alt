"""Probability distributions for data simulation.

These classes define probability distributions used to generate
realistic simulated values for condition indices, ages, grades, etc.
"""

import random
import re


class ProbabilitySegment:
    """Represents a single segment in a probability distribution.
    
    A segment has a percentage weight and a value (either a single int or a range).
    """

    def __init__(self, percentage: int, value: str) -> None:
        """Initialize a probability segment.

        Args:
            percentage: Percentage weight (1-100).
            value: Segment value string (e.g., "50" or "20-40").
        """
        if not (1 <= percentage <= 100):
            raise ValueError(f"Percentage must be between 1 and 100, got {percentage}")
        if value is None or str(value).strip() == "":
            raise ValueError("Value cannot be None or an empty string")

        self._percentage = percentage
        self._value = str(value)
        self._parsed_value: int | tuple[int, int] | None = None

    @property
    def percentage(self) -> float:
        """Return percentage as decimal (0.0-1.0)."""
        return self._percentage / 100.0

    @percentage.setter
    def percentage(self, percent: int) -> None:
        """Set percentage value."""
        if not (1 <= percent <= 100):
            raise ValueError(f"Percentage must be between 1 and 100, got {percent}")
        self._percentage = percent

    @property
    def value(self) -> str:
        """Return segment value string."""
        return self._value

    @value.setter
    def value(self, value: str) -> None:
        """Set segment value string."""
        if value is None or str(value).strip() == "":
            raise ValueError("Value cannot be None or an empty string")
        self._value = str(value)
        self._parsed_value = None  # Invalidate cache

    @property
    def parsed_value(self) -> int | tuple[int, int] | None:
        """Return parsed value (int or tuple range)."""
        if self._parsed_value is None:
            self._parsed_value = self._parse_value()
        return self._parsed_value

    def is_range_value(self) -> bool:
        """Check if parsed value is a range (tuple)."""
        return isinstance(self.parsed_value, tuple)

    def _parse_value(self) -> int | tuple[int, int] | None:
        """Parse the value string into int or tuple."""
        if "-" in self._value:
            parts = self._value.split("-")
            if len(parts) == 2:
                try:
                    left = int(parts[0].strip())
                    right = int(parts[1].strip())
                    if left > right:
                        left, right = right, left
                    if left != right:
                        return (left, right)
                    else:
                        return left
                except ValueError:
                    return None

        try:
            return int(self._value.strip())
        except (ValueError, TypeError):
            return None

    def sample(self) -> float:
        """Sample a random value from this segment."""
        parsed = self.parsed_value
        if isinstance(parsed, tuple):
            return random.uniform(parsed[0], parsed[1])
        elif isinstance(parsed, int):
            return float(parsed)
        else:
            return 50.0  # Default fallback

    def __str__(self) -> str:
        """Return string representation."""
        return f"ProbabilitySegment(percentage={self._percentage}, value='{self._value}')"

    @staticmethod
    def is_matching_segment_data_format(line_value: str) -> re.Match[str] | None:
        """Check if line matches expected segment format.

        Args:
            line_value: String to check (e.g., '50: 20-40').

        Returns:
            Match object if format matches, None otherwise.
        """
        return re.match(r"(?:\d+:)?\s*\(?\s*(\d+)\s*[,|:]\s*(\d+)\s*-\s*(\d+)\s*\)?", line_value)


class ProbabilityDistribution:
    """Represents a probability distribution with multiple segments."""

    def __init__(self, segments: list[ProbabilitySegment]) -> None:
        """Initialize a probability distribution.

        Args:
            segments: List of probability segments.
        """
        if not segments:
            raise ValueError("ProbabilityDistribution must have at least one segment")
        self._segments = segments

    def get_total_percentage(self) -> int:
        """Return total percentage across all segments."""
        return sum(segment._percentage for segment in self._segments)

    def percentages_exceed_100(self) -> bool:
        """Check if total percentages exceed 100."""
        return self.get_total_percentage() > 100

    @property
    def segments(self) -> list[ProbabilitySegment]:
        """Return list of probability segments."""
        return self._segments

    def select_random_segment(self) -> ProbabilitySegment:
        """Select a random segment based on probability distribution."""
        rand = random.random()
        cumulative = 0.0

        total = sum(segment._percentage for segment in self._segments)
        factor = 100.0 / total if total != 0 else 1.0

        for segment in self._segments:
            normalized = (segment._percentage * factor) / 100.0
            cumulative += normalized

            if rand < cumulative:
                return segment

        # Fallback to last segment
        return self._segments[-1] if self._segments else None

    def __str__(self) -> str:
        """Return string representation."""
        segments_str = ",\n".join("\t" + str(s) for s in self._segments)
        return f"ProbabilityDistribution(segments=[\n{segments_str}])"
