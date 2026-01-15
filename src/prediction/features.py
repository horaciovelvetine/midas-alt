"""Feature extraction for ML-based degradation prediction.

Extracts features from domain entities for use in prediction models.
"""

from dataclasses import asdict, dataclass
from datetime import datetime

import pandas as pd

from ..config.reference_data import FacilityType, SystemType
from ..config.settings import MIDASSettings
from ..domain import EntityType, Facility, System


@dataclass
class DegradationFeatures:
    """Feature vector for degradation prediction models.

    These features are extracted from domain entities and used as
    input to ML models for predicting time to degradation.
    """

    # Identifiers (not used as features, but useful for tracking)
    entity_id: str
    entity_type: str  # "facility" or "system"
    snapshot_timestamp: str  # ISO format timestamp

    # Core features
    condition_index: float
    age_months: int
    life_expectancy_months: int

    # Type features
    facility_type_key: int
    system_type_key: int | None  # None for facilities

    # Context features
    mission_criticality: int
    resiliency_grade: int  # 1-4, 0 if unknown
    dependency_tier: str | None  # "P", "S", "T", or None
    dependency_group_count: int

    # Derived features (computed from core features)
    remaining_life_ratio: float  # age / life_expectancy (0 = new, 1 = at life expectancy)
    condition_age_ratio: float  # condition_index / (100 - age_ratio * 100)

    # Historical features (optional, for time-series aware models)
    condition_index_lag_3mo: float | None = None
    condition_index_lag_6mo: float | None = None
    condition_index_lag_12mo: float | None = None
    ci_delta_3mo: float | None = None  # Change in CI over last 3 months
    ci_delta_12mo: float | None = None  # Change in CI over last 12 months

    def to_dict(self) -> dict:
        """Convert to dictionary for DataFrame creation."""
        return asdict(self)

    @property
    def feature_dict(self) -> dict:
        """Get only the ML feature columns (excludes identifiers)."""
        d = self.to_dict()
        # Remove identifier columns
        del d["entity_id"]
        del d["entity_type"]
        del d["snapshot_timestamp"]
        return d


class FeatureExtractor:
    """Extracts ML features from domain entities.

    Uses settings to look up reference data (facility types, system types)
    for feature enrichment.
    """

    # Feature columns that are always present
    CORE_FEATURE_COLUMNS = [
        "condition_index",
        "age_months",
        "life_expectancy_months",
        "facility_type_key",
        "system_type_key",
        "mission_criticality",
        "resiliency_grade",
        "dependency_tier",
        "dependency_group_count",
        "remaining_life_ratio",
        "condition_age_ratio",
    ]

    # Optional historical feature columns
    HISTORICAL_FEATURE_COLUMNS = [
        "condition_index_lag_3mo",
        "condition_index_lag_6mo",
        "condition_index_lag_12mo",
        "ci_delta_3mo",
        "ci_delta_12mo",
    ]

    def __init__(self, settings: MIDASSettings):
        """Initialize with settings for reference data lookup.

        Args:
            settings: Application settings with facility/system types.
        """
        self.settings = settings

    def extract_facility_features(
        self,
        facility: Facility,
        historical_ci: dict[int, float] | None = None,
    ) -> DegradationFeatures:
        """Extract features from a facility.

        Args:
            facility: The facility to extract features from.
            historical_ci: Optional dict mapping months_ago -> condition_index
                          for historical features.

        Returns:
            DegradationFeatures for the facility.
        """
        # Get reference data
        facility_type = self.settings.get_facility_type(facility.facility_type_key or 0)
        life_expectancy = (
            facility_type.life_expectancy_months if facility_type else 600
        )  # Default 50 years
        mission_crit = facility_type.mission_criticality if facility_type else 1

        age_months = facility.age_months or 0

        # Compute derived features
        remaining_life_ratio = min(age_months / life_expectancy, 2.0) if life_expectancy > 0 else 0
        ci = facility.condition_index or 50.0

        # Condition-age ratio: how good is CI relative to age?
        expected_ci_for_age = 100 - (remaining_life_ratio * 75)  # Simple linear expectation
        condition_age_ratio = ci / expected_ci_for_age if expected_ci_for_age > 0 else 1.0

        # Extract historical features
        ci_lag_3, ci_lag_6, ci_lag_12 = None, None, None
        ci_delta_3, ci_delta_12 = None, None

        if historical_ci:
            ci_lag_3 = historical_ci.get(3)
            ci_lag_6 = historical_ci.get(6)
            ci_lag_12 = historical_ci.get(12)

            if ci_lag_3 is not None:
                ci_delta_3 = ci - ci_lag_3
            if ci_lag_12 is not None:
                ci_delta_12 = ci - ci_lag_12

        return DegradationFeatures(
            entity_id=facility.id,
            entity_type=EntityType.FACILITY.value,
            snapshot_timestamp=datetime.now().isoformat(),
            condition_index=ci,
            age_months=age_months,
            life_expectancy_months=life_expectancy,
            facility_type_key=facility.facility_type_key or 0,
            system_type_key=None,
            mission_criticality=mission_crit,
            resiliency_grade=facility.resiliency_grade.value if facility.resiliency_grade else 0,
            dependency_tier=facility.dependency_chain.tier.value if facility.dependency_chain.tier else None,
            dependency_group_count=len(facility.dependency_chain.group_ids),
            remaining_life_ratio=round(remaining_life_ratio, 4),
            condition_age_ratio=round(condition_age_ratio, 4),
            condition_index_lag_3mo=ci_lag_3,
            condition_index_lag_6mo=ci_lag_6,
            condition_index_lag_12mo=ci_lag_12,
            ci_delta_3mo=ci_delta_3,
            ci_delta_12mo=ci_delta_12,
        )

    def extract_system_features(
        self,
        system: System,
        facility: Facility | None = None,
        historical_ci: dict[int, float] | None = None,
    ) -> DegradationFeatures:
        """Extract features from a system.

        Args:
            system: The system to extract features from.
            facility: Optional parent facility for context features.
            historical_ci: Optional dict mapping months_ago -> condition_index.

        Returns:
            DegradationFeatures for the system.
        """
        # Get reference data
        system_type = self.settings.get_system_type(system.system_type_key or 0)
        life_expectancy = system_type.life_expectancy_months if system_type else 360  # Default 30 years

        # Get facility context
        facility_type_key = 0
        mission_crit = 1
        resiliency_grade = 0
        dep_tier = None
        dep_group_count = 0

        if facility:
            facility_type_key = facility.facility_type_key or 0
            facility_type = self.settings.get_facility_type(facility_type_key)
            if facility_type:
                mission_crit = facility_type.mission_criticality
            if facility.resiliency_grade:
                resiliency_grade = facility.resiliency_grade.value
            if facility.dependency_chain.tier:
                dep_tier = facility.dependency_chain.tier.value
            dep_group_count = len(facility.dependency_chain.group_ids)

        age_months = system.age_months or 0
        ci = system.condition_index or 50.0

        # Compute derived features
        remaining_life_ratio = min(age_months / life_expectancy, 2.0) if life_expectancy > 0 else 0
        expected_ci_for_age = 100 - (remaining_life_ratio * 75)
        condition_age_ratio = ci / expected_ci_for_age if expected_ci_for_age > 0 else 1.0

        # Historical features
        ci_lag_3, ci_lag_6, ci_lag_12 = None, None, None
        ci_delta_3, ci_delta_12 = None, None

        if historical_ci:
            ci_lag_3 = historical_ci.get(3)
            ci_lag_6 = historical_ci.get(6)
            ci_lag_12 = historical_ci.get(12)
            if ci_lag_3 is not None:
                ci_delta_3 = ci - ci_lag_3
            if ci_lag_12 is not None:
                ci_delta_12 = ci - ci_lag_12

        return DegradationFeatures(
            entity_id=system.id,
            entity_type=EntityType.SYSTEM.value,
            snapshot_timestamp=datetime.now().isoformat(),
            condition_index=ci,
            age_months=age_months,
            life_expectancy_months=life_expectancy,
            facility_type_key=facility_type_key,
            system_type_key=system.system_type_key,
            mission_criticality=mission_crit,
            resiliency_grade=resiliency_grade,
            dependency_tier=dep_tier,
            dependency_group_count=dep_group_count,
            remaining_life_ratio=round(remaining_life_ratio, 4),
            condition_age_ratio=round(condition_age_ratio, 4),
            condition_index_lag_3mo=ci_lag_3,
            condition_index_lag_6mo=ci_lag_6,
            condition_index_lag_12mo=ci_lag_12,
            ci_delta_3mo=ci_delta_3,
            ci_delta_12mo=ci_delta_12,
        )

    def extract_batch(
        self,
        entities: list[Facility | System],
        facilities_map: dict[str, Facility] | None = None,
    ) -> pd.DataFrame:
        """Extract features from multiple entities into a DataFrame.

        Args:
            entities: List of facilities or systems.
            facilities_map: Optional mapping of facility_id -> Facility for system context.

        Returns:
            DataFrame with one row per entity.
        """
        features_list = []

        for entity in entities:
            if isinstance(entity, Facility):
                features = self.extract_facility_features(entity)
            elif isinstance(entity, System):
                parent_facility = None
                if facilities_map and entity.facility_id:
                    parent_facility = facilities_map.get(entity.facility_id)
                features = self.extract_system_features(entity, parent_facility)
            else:
                continue

            features_list.append(features.to_dict())

        return pd.DataFrame(features_list)
