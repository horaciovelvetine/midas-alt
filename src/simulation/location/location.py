"""
This module defines a location profile that can be used to model the impact of environmental conditions on degradation. The location profile is represented as a simple bucket
(hot/humid, cold, normal) that corresponds to a multiplicative degradation factor. This allows us to easily incorporate location-based degradation into our simulation models.

Earlier this approach used the kopengeiger climate classification system, but we found that it was too granular for our needs and made it difficult to interpret the results.
By using a simpler bucket system, we can still capture the key differences in environmental impact while keeping the model more interpretable and easier to work with.

Also change from prior design, the location module used to sit on its own, as a factor that would be additive. However, looking back on the design,
It's not as if the location of where the infrastructure is built is going to suddenly change, there is no reason to have the factor be an additive calc
rather simply put it as a scaling/mult factor on the base degredation.

Simple location-based degradation model (3-bucket version)

Bucket assignments come from K-means clustering (3 clusters) performed by the weather team
on 210+ AF bases using historical weather data:

    Cluster 0 = NORMAL    (dry/mild western bases)
    Cluster 1 = COLD      (cold/wet northeastern bases)
    Cluster 2 = HOT_HUMID (warm/humid southeastern bases)

Source data: src/simulation/location/data/bases_with_cluster_labels.csv
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pandas as pd


_DATA_PATH = Path(__file__).parent / "data" / "bases_with_cluster_labels.csv"

# Loaded once on first use
_BASE_LOOKUP: dict[str, int] | None = None


def _get_base_lookup() -> dict[str, int]:
    """Return a name→cluster mapping, loading the CSV on first call."""
    global _BASE_LOOKUP
    if _BASE_LOOKUP is None:
        df = pd.read_csv(_DATA_PATH, usecols=["Site_Name", "Cluster"])
        _BASE_LOOKUP = dict(zip(df["Site_Name"].str.strip(), df["Cluster"].astype(int)))
    return _BASE_LOOKUP


# Cluster to Bucket mapping

_CLUSTER_TO_BUCKET: dict[int, "LocationBucket"] = {}  # populated after class def


class LocationBucket(str, Enum):
    HOT_HUMID = "hot_humid"
    COLD = "cold"
    NORMAL = "normal"


_CLUSTER_TO_BUCKET = {
    0: LocationBucket.NORMAL,
    1: LocationBucket.COLD,
    2: LocationBucket.HOT_HUMID,
}


# degradation factors
"""

Currently these factors numbers are simply based off a bit of research and intuition,
but we can adjust them as we see fit based on how they impact the overall simulation results.

"""
LOCATION_BUCKET_FACTORS = {
    LocationBucket.NORMAL:    1.00,
    LocationBucket.COLD:      1.15,
    LocationBucket.HOT_HUMID: 1.25,
}


@dataclass(frozen=True)
class LocationProfile:
    """Represents environmental impact via simple bucket."""

    name: str = "Unknown"
    bucket: LocationBucket = LocationBucket.NORMAL

    @property
    def degradation_factor(self) -> float:
        """Multiplicative factor applied to base degradation (>= 1.0)."""
        return LOCATION_BUCKET_FACTORS[self.bucket]

    @classmethod
    def from_cluster(cls, name: str, cluster_id: int) -> LocationProfile:
        """
        Build a LocationProfile from a known cluster ID (0, 1, or 2).

        Args:
            name:       Installation name, for display/debugging.
            cluster_id: Weather cluster label assigned by the weather team.

        Raises:
            ValueError: If cluster_id is not 0, 1, or 2.
        """
        if cluster_id not in _CLUSTER_TO_BUCKET:
            raise ValueError(
                f"Unknown cluster_id {cluster_id!r}. Expected 0, 1, or 2."
            )
        return cls(name=name, bucket=_CLUSTER_TO_BUCKET[cluster_id])

    @classmethod
    def from_base_name(cls, name: str) -> LocationProfile:
        """
        Look up a base by name and return its LocationProfile.

        Performs a case-insensitive lookup against the cluster CSV.
        Falls back to NORMAL bucket if the base is not found, so the
        simulation can still run for bases not yet in the dataset.

        Args:
            name: Installation name (e.g. "Eglin Air Force Base").
        """
        lookup = _get_base_lookup()

        # Exact match first
        cluster_id = lookup.get(name.strip())

        # Case-insensitive fallback
        if cluster_id is None:
            name_lower = name.strip().lower()
            for key, val in lookup.items():
                if key.lower() == name_lower:
                    cluster_id = val
                    break

        if cluster_id is None:
            return cls(name=name, bucket=LocationBucket.NORMAL)

        return cls.from_cluster(name=name, cluster_id=cluster_id)
