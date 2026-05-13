"""Process-wide ``MidasConfigData`` reference-data singleton.

Holds the facility-type, system-type, installation-location, and work-order
text caches that are loaded from ``docs/midas_config_data.xlsx`` at startup.
Distribution-driven random samplers that use these caches also live here so
callers have one entry point for reference-data lookups.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config._singleton import SingletonMeta
from src.models import (
    DistributionBase,
    FacilityType,
    InstallationLocation,
    SystemType,
    WorkOrderText,
)


@dataclass
class MidasConfigData(metaclass=SingletonMeta):
    """Singleton reference-data container populated from the config workbook."""

    facility_types: dict[int, FacilityType] = field(default_factory=dict)
    system_types: dict[int, SystemType] = field(default_factory=dict)
    installation_locations: list[InstallationLocation] = field(default_factory=list)
    work_order_text_cache: dict[str, list[WorkOrderText]] = field(default_factory=dict)
    config_workbook_path: Path | None = None

    # ! ==========================================================================================>
    # ! REFERENCE LOOKUPS
    # ! ==========================================================================================>

    def get_facility_type(self, key: int | None) -> FacilityType | None:
        """Get facility type by key."""
        if key is None:
            return None
        return self.facility_types.get(key)

    def get_system_type(self, key: int | None) -> SystemType | None:
        """Get system type by key."""
        if key is None:
            return None
        return self.system_types.get(key)

    def get_random_facility_type(self, excluded_keys: list[int] | None = None) -> FacilityType | None:
        """Get a random facility type, optionally excluding certain keys."""
        excluded = excluded_keys or []
        available = [ft for ft in self.facility_types.values() if ft.key not in excluded]
        return random.choice(available) if available else None

    def get_random_system_type_for_facility(self, facility_key: int) -> SystemType | None:
        """Get a random system type that belongs to the given facility type."""
        system_types = self.get_system_types_for_facility(facility_key)
        return random.choice(system_types) if system_types else None

    def get_system_types_for_facility(self, facility_key: int) -> list[SystemType]:
        """Get all system types that belong to a facility type."""
        return [st for st in self.system_types.values() if facility_key in st.facility_keys]

    def get_random_location(self) -> InstallationLocation | None:
        """Get a random location from loaded installation locations."""
        return random.choice(self.installation_locations) if self.installation_locations else None

    # ! ==========================================================================================>
    # ! DISTRIBUTION-DRIVEN SAMPLING
    # ! ==========================================================================================>

    def sample_work_order_template(self, system_title: str | None) -> WorkOrderText | None:
        """Return a workbook ``Work Orders`` row matching ``system_title``.

        Lookup is tolerant of minor casing/whitespace and trailing-digit
        differences between the ``Systems`` and ``Work Orders`` sheet titles
        (e.g. ``Electric`` matches ``Electrical``; ``Special construction2``
        matches ``Special Construction 2``). Falls back to a random row from
        the pooled cache when no system-specific rows are available.
        """
        from src.io.loaders.config_data.load_work_order_text_config_data import (
            FALLBACK_KEY,
            normalize_system_title,
        )

        if not self.work_order_text_cache:
            return None

        rows = self._lookup_template_rows(system_title, fallback_key=FALLBACK_KEY, normalize=normalize_system_title)
        if not rows:
            return None
        return random.choice(rows)

    def _lookup_template_rows(
        self,
        system_title: str | None,
        *,
        fallback_key: str,
        normalize,
    ) -> list[WorkOrderText]:
        """Return work-order template rows for ``system_title`` (tolerant match)."""
        key = normalize(system_title) if system_title else ""
        if key:
            exact = self.work_order_text_cache.get(key)
            if exact:
                return exact
            for candidate_key, candidate_rows in self.work_order_text_cache.items():
                if candidate_key == fallback_key or not candidate_key:
                    continue
                if candidate_key.startswith(key) or key.startswith(candidate_key):
                    return candidate_rows
        return self.work_order_text_cache.get(fallback_key, [])

    def sample_work_order_text(self, system_type: str | None) -> WorkOrderText | None:
        """Sample a work-order text template (deprecated alias for :meth:`sample_work_order_template`)."""
        return self.sample_work_order_template(system_type)

    def get_random_work_order_requesting_organization(self) -> str | None:
        """Return a requesting organization sampled from the configured distribution."""
        from src.config.midas_settings import MidasSettings

        distribution: DistributionBase = MidasSettings().get_value("generated_work_order_requesting_organization_distribution")
        sampled: Any = distribution.sample()
        text = str(sampled).strip() if sampled is not None else ""
        return text or None

    # ! ==========================================================================================>
    # ! POPULATION HELPERS
    # ! ==========================================================================================>

    def replace_reference_data(
        self,
        *,
        facility_types: dict[int, FacilityType] | None = None,
        system_types: dict[int, SystemType] | None = None,
        installation_locations: list[InstallationLocation] | None = None,
        work_order_text_cache: dict[str, list[WorkOrderText]] | None = None,
        config_workbook_path: Path | None = None,
    ) -> None:
        """Replace the singleton's reference-data slots in place."""
        if facility_types is not None:
            self.facility_types = facility_types
        if system_types is not None:
            self.system_types = system_types
        if installation_locations is not None:
            self.installation_locations = installation_locations
        if work_order_text_cache is not None:
            self.work_order_text_cache = work_order_text_cache
        if config_workbook_path is not None:
            self.config_workbook_path = config_workbook_path

    def clear(self) -> None:
        """Reset all reference-data slots to empty defaults."""
        self.facility_types = {}
        self.system_types = {}
        self.installation_locations = []
        self.work_order_text_cache = {}
        self.config_workbook_path = None

    @classmethod
    def reset(cls) -> None:
        """Drop and recreate the singleton (test-friendly helper)."""
        cls._reset_for_tests()  # type: ignore[attr-defined]
