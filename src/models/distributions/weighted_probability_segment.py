"""One weighted outcome row (percentage and value) for discrete distributions."""

from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .distribution_context import DistributionContext


class WeightedProbabilitySegment:
    """Represents a single segment in a weighted probability distribution."""

    def __init__(self, percentage: int, value: str) -> None:
        """Initialize a weighted segment with percent and raw value."""
        if not (1 <= percentage <= 100):
            raise ValueError(f"Percentage must be between 1 and 100, got {percentage}")
        if value is None or str(value).strip() == "":
            raise ValueError("Value cannot be None or an empty string")

        self._percentage = percentage
        self._value = str(value)
        self._parsed_value: int | tuple[int, int] | None = None

    @property
    def weight_percent(self) -> int:
        """Return the configured segment weight as an integer percent (1-100)."""
        return self._percentage

    @property
    def percentage(self) -> float:
        """Return the segment weight as a 0-1 fraction."""
        return self._percentage / 100.0

    @percentage.setter
    def percentage(self, percent: int) -> None:
        if not (1 <= percent <= 100):
            raise ValueError(f"Percentage must be between 1 and 100, got {percent}")
        self._percentage = percent

    @property
    def value(self) -> str:
        """Return the raw configured segment value."""
        return self._value

    @value.setter
    def value(self, value: str) -> None:
        if value is None or str(value).strip() == "":
            raise ValueError("Value cannot be None or an empty string")
        self._value = str(value)
        self._parsed_value = None

    @property
    def parsed_value(self) -> int | tuple[int, int] | None:
        """Return parsed integer/range form when possible."""
        if self._parsed_value is None:
            self._parsed_value = self._parse_value()
        return self._parsed_value

    def is_range_value(self) -> bool:
        """Return True when the segment represents a numeric range."""
        return isinstance(self.parsed_value, tuple)

    def _parse_value(self) -> int | tuple[int, int] | None:
        if "-" in self._value:
            parts = self._value.split("-")
            if len(parts) == 2:
                try:
                    left = int(parts[0].strip())
                    right = int(parts[1].strip())
                    if left > right:
                        left, right = right, left
                    return (left, right) if left != right else left
                except ValueError:
                    return None

        try:
            return int(self._value.strip())
        except (ValueError, TypeError):
            return None

    def sample(self, context: DistributionContext | None = None) -> float | str:
        """Sample numeric value, else return literal string value."""
        del context
        parsed = self.parsed_value
        if isinstance(parsed, tuple):
            return random.uniform(parsed[0], parsed[1])
        if isinstance(parsed, int):
            return float(parsed)
        return self._value.strip()

    def to_dict(self) -> dict:
        """Serialize to a plain dict for JSON encoding."""
        return {"percentage": self._percentage, "value": self._value}

    def __str__(self) -> str:
        """Return a readable representation for diagnostics."""
        return f"WeightedProbabilitySegment(percentage={self._percentage}, value='{self._value}')"

    @staticmethod
    def is_matching_segment_data_format(line_value: str) -> re.Match[str] | None:
        """Check whether text matches a supported segment pattern."""
        return re.match(r"(?:\d+:)?\s*\(?\s*(\d+)\s*[,|:]\s*(\d+)\s*-\s*(\d+)\s*\)?", line_value)
