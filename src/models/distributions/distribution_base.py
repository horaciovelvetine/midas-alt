"""Protocol and default helpers for MIDAS probability distributions."""

import math
import random
from typing import Protocol

from .distribution_context import DistributionContext


class DistributionBase(Protocol):
    """Protocol for reusable distributions."""

    def sample(self, context: DistributionContext | None = None) -> float | str:
        """Sample a value from the distribution."""

    def _sample_poisson(self, lam: float) -> int:
        """Generate a random sample from the Poisson distribution with parameter lam.

        This implementation does not require external dependencies, using only the standard
        library. It uses the classic inverse transform sampling algorithm, also known as
        Knuth's method, to generate integer-valued Poisson samples.

        Args:
            lam: The expected value (rate parameter, λ) of the Poisson distribution. Must be non-negative.

        Returns:
            An integer sampled from Poisson(lam). Returns 0 if lam <= 0.

        """
        if lam <= 0:
            return 0
        l_bound = math.exp(-lam)
        k = 0
        p = 1.0
        while p > l_bound:
            k += 1
            p *= random.random()
        return k - 1

    def _resolve_age_ratio(
        self,
        context: DistributionContext | None,
        default_ratio: float = 0.5,
        max_ratio: float = 1.5,
    ) -> float:
        """Resolve an age ratio from the given distribution context, enforcing boundaries.

        If the context or its age_ratio is None, uses the provided default_ratio.
        The result is clamped to the range [0.0, max_ratio].

        Args:
            context: Optional DistributionContext that may provide an age_ratio.
            default_ratio: Value to use if context or context.age_ratio is None.
            max_ratio: The maximum allowed age ratio.

        Returns:
            The resolved and clamped age ratio as a float.

        """
        if context is None:
            return default_ratio
        ratio = context.age_ratio
        if ratio is None:
            return default_ratio
        return max(0.0, min(max_ratio, ratio))
