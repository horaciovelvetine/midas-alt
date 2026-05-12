"""Shared sampling helpers for synthetic data generators (distributions, context)."""

import random
from datetime import datetime
from typing import Any

from src.config.midas_config_data import MidasConfigData
from src.config.midas_settings import MidasSettings
from src.enums import UFCGrade
from src.models import DistributionContext, EventRateDistribution, System, SystemType


class DataGeneratorBase:
    """Sampling and aggregation helpers shared by installation through work-order generators.

    Reads probability distributions from the ``MidasSettings`` singleton and
    reference-data lookups from the ``MidasConfigData`` singleton.
    """

    def __init__(self, seed: int | None = None) -> None:
        """Optionally seed ``random`` for reproducible generation.

        Args:
            seed: When not ``None``, passed to ``random.seed``.
        """
        self.settings: MidasSettings = MidasSettings()
        self.config_data: MidasConfigData = MidasConfigData()
        if seed is not None:
            random.seed(seed)

    def sample_year_constructed(self, max_age: int) -> int:
        """Return a construction year capped by ``max_age`` (years)."""
        distribution = self.settings.get_value("generated_age_distribution")
        rnd_age = int(distribution.select_random_segment().sample())
        age = min(rnd_age, max_age)
        return datetime.now().year - age

    def sample_condition_index(self) -> float:
        """Sample a starting condition index rounded to two decimal places."""
        distribution = self.settings.get_value("generated_condition_index_distribution")
        sampled = distribution.select_random_segment().sample()
        return round(float(sampled), 2)

    def sample_ufc_resiliency_grade(self) -> UFCGrade:
        """Sample a UFC resiliency grade (G1-G4); unmapped values use G1."""
        distribution = self.settings.get_value(
            "generated_resiliency_grade_distribution"
        )
        sampled = distribution.select_random_segment().sample()
        str_key = str(int(sampled)) if isinstance(sampled, float) else str(sampled)
        return UFCGrade.from_value(str_key) or UFCGrade.G1

    def build_system_distribution_context(
        self, system: System, system_type: SystemType | None = None
    ) -> DistributionContext:
        """Build ``DistributionContext`` for lifecycle-aware distributions."""
        resolved_system_type = system_type
        if resolved_system_type is None and system.system_type_key is not None:
            resolved_system_type = self.config_data.get_system_type(
                system.system_type_key
            )

        life_expectancy = (
            resolved_system_type.life_expectancy
            if resolved_system_type is not None
            else None
        )
        return DistributionContext(
            age_years=system.age_years,
            life_expectancy_years=life_expectancy,
            condition_index=system.condition_index,
            metadata={
                "system_type_key": system.system_type_key,
                "system_id": system.id,
                "facility_id": system.facility_id,
            },
        )

    def sample_event_count(
        self,
        distribution: Any,
        context: DistributionContext | None = None,
        horizon_years: float = 1.0,
    ) -> int:
        """Non-negative integer count: Poisson for ``EventRateDistribution``, else coerced ``sample()``."""
        if isinstance(distribution, EventRateDistribution):
            return distribution.sample_count(
                context=context, horizon_years=horizon_years
            )

        sampled = (
            distribution.sample(context=context)
            if context is not None
            else distribution.sample()
        )
        try:
            return max(0, int(round(float(sampled))))
        except (TypeError, ValueError):
            return 0

    def average_condition_index(self, entities: list[object]) -> float | None:
        """Mean of defined ``condition_index`` values on ``entities`` (two decimals)."""
        values = [
            float(value)
            for value in (
                getattr(entity, "condition_index", None) for entity in entities
            )
            if value is not None
        ]
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    def random_choice(self, values: list[Any]) -> Any:
        """Uniform random element from ``values``."""
        if not values:
            raise ValueError("random_choice requires at least one value")
        return random.choice(values)
