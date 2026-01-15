"""Training dataset generation for ML models.

Creates labeled datasets by simulating entities and computing
their actual time to degradation.
"""

import math
from dataclasses import dataclass
from enum import Enum

import pandas as pd

from ..config.settings import MIDASSettings
from ..domain import Facility, System
from ..simulation import DataGenerator
from .features import DegradationFeatures, FeatureExtractor


class LabelType(Enum):
    """How to label training data."""

    # Regression targets
    MONTHS_TO_DEGRADATION = "months_to_degradation"
    DEGRADATION_RATE = "degradation_rate"  # Monthly CI loss

    # Classification targets
    WILL_DEGRADE_6MO = "will_degrade_6mo"
    WILL_DEGRADE_12MO = "will_degrade_12mo"
    WILL_DEGRADE_24MO = "will_degrade_24mo"


@dataclass
class DatasetConfig:
    """Configuration for training dataset generation."""

    n_installations: int = 100
    label_type: LabelType = LabelType.MONTHS_TO_DEGRADATION
    degradation_threshold: float = 25.0
    initial_ci: float = 99.99

    # Include historical features (requires simulating history)
    include_historical: bool = False

    # Random seed for reproducibility
    seed: int | None = 42


class TrainingDataGenerator:
    """Generate labeled training datasets for degradation prediction.

    Creates synthetic data by:
    1. Generating installations with facilities and systems
    2. Extracting features from current state
    3. Computing actual time to degradation as labels
    """

    def __init__(
        self,
        settings: MIDASSettings | None = None,
        config: DatasetConfig | None = None,
    ):
        """Initialize the training data generator.

        Args:
            settings: Application settings.
            config: Dataset generation configuration.
        """
        self.settings = settings or MIDASSettings.with_defaults()
        self.config = config or DatasetConfig()

        self.data_generator = DataGenerator(
            settings=self.settings,
            seed=self.config.seed,
        )
        self.feature_extractor = FeatureExtractor(self.settings)

    def generate(self) -> tuple[pd.DataFrame, pd.Series]:
        """Generate features (X) and labels (y) for training.

        Returns:
            Tuple of (features_df, labels_series).
        """
        # Generate installations
        installations, facilities, systems = self.data_generator.generate_installations(
            self.config.n_installations
        )

        # Build facility lookup for system feature extraction
        facilities_map = {f.id: f for f in facilities}

        # Extract features and compute labels
        feature_rows = []
        labels = []

        for facility in facilities:
            features = self.feature_extractor.extract_facility_features(facility)
            label = self._compute_label(facility)

            feature_rows.append(features.to_dict())
            labels.append(label)

        for system in systems:
            parent_facility = facilities_map.get(system.facility_id)
            features = self.feature_extractor.extract_system_features(
                system, parent_facility
            )
            label = self._compute_label(system)

            feature_rows.append(features.to_dict())
            labels.append(label)

        X = pd.DataFrame(feature_rows)
        y = pd.Series(labels, name=self.config.label_type.value)

        return X, y

    def generate_facility_dataset(self) -> tuple[pd.DataFrame, pd.Series]:
        """Generate dataset for facilities only.

        Returns:
            Tuple of (features_df, labels_series).
        """
        installations, facilities, _ = self.data_generator.generate_installations(
            self.config.n_installations
        )

        feature_rows = []
        labels = []

        for facility in facilities:
            features = self.feature_extractor.extract_facility_features(facility)
            label = self._compute_label(facility)

            feature_rows.append(features.to_dict())
            labels.append(label)

        X = pd.DataFrame(feature_rows)
        y = pd.Series(labels, name=self.config.label_type.value)

        return X, y

    def generate_system_dataset(self) -> tuple[pd.DataFrame, pd.Series]:
        """Generate dataset for systems only.

        Returns:
            Tuple of (features_df, labels_series).
        """
        installations, facilities, systems = self.data_generator.generate_installations(
            self.config.n_installations
        )

        facilities_map = {f.id: f for f in facilities}

        feature_rows = []
        labels = []

        for system in systems:
            parent_facility = facilities_map.get(system.facility_id)
            features = self.feature_extractor.extract_system_features(
                system, parent_facility
            )
            label = self._compute_label(system)

            feature_rows.append(features.to_dict())
            labels.append(label)

        X = pd.DataFrame(feature_rows)
        y = pd.Series(labels, name=self.config.label_type.value)

        return X, y

    def _compute_label(self, entity: Facility | System) -> float:
        """Compute the label for an entity based on label_type.

        Args:
            entity: Facility or System to compute label for.

        Returns:
            Label value (type depends on label_type).
        """
        current_ci = entity.condition_index or 50.0
        age_months = entity.age_months or 0

        if self.config.label_type == LabelType.MONTHS_TO_DEGRADATION:
            return self._compute_months_to_degradation(current_ci, age_months)

        elif self.config.label_type == LabelType.DEGRADATION_RATE:
            return self._compute_degradation_rate(current_ci, age_months)

        elif self.config.label_type == LabelType.WILL_DEGRADE_6MO:
            months = self._compute_months_to_degradation(current_ci, age_months)
            return 1.0 if months <= 6 else 0.0

        elif self.config.label_type == LabelType.WILL_DEGRADE_12MO:
            months = self._compute_months_to_degradation(current_ci, age_months)
            return 1.0 if months <= 12 else 0.0

        elif self.config.label_type == LabelType.WILL_DEGRADE_24MO:
            months = self._compute_months_to_degradation(current_ci, age_months)
            return 1.0 if months <= 24 else 0.0

        return 0.0

    def _compute_months_to_degradation(
        self, current_ci: float, age_months: int
    ) -> float:
        """Compute months until CI falls below threshold.

        Uses exponential decay model: CI(t) = CI_0 * (1-R)^t
        """
        if current_ci <= self.config.degradation_threshold:
            return 0.0

        decay_rate = self._compute_decay_rate(current_ci, age_months)

        if decay_rate is None or decay_rate <= 0:
            return 999.0  # No degradation

        if decay_rate >= 1.0:
            return 0.0  # Already fully degraded

        try:
            months = math.log(self.config.degradation_threshold / current_ci) / math.log(
                1 - decay_rate
            )
            return max(0, months)
        except (ValueError, ZeroDivisionError):
            return 999.0

    def _compute_degradation_rate(
        self, current_ci: float, age_months: int
    ) -> float:
        """Compute monthly degradation rate."""
        rate = self._compute_decay_rate(current_ci, age_months)
        return rate if rate is not None else 0.0

    def _compute_decay_rate(
        self, current_ci: float, age_months: int
    ) -> float | None:
        """Calculate monthly decay rate from current state.

        Formula: R = 1 - (CI_current / CI_initial)^(1/age)
        """
        if age_months <= 0:
            return None

        if current_ci <= 0 or self.config.initial_ci <= 0:
            return None

        ratio = current_ci / self.config.initial_ci
        if ratio <= 0 or ratio >= 1:
            return None

        try:
            decay_rate = 1 - ratio ** (1 / age_months)
            return decay_rate if decay_rate > 0 else None
        except (ValueError, ZeroDivisionError):
            return None


class ModelEvaluator:
    """Evaluate and compare multiple degradation models."""

    def __init__(self, models: list):
        """Initialize with list of DegradationModel instances."""
        self.models = models
        self.results: list[dict] = []

    def evaluate_all(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        test_size: float = 0.2,
    ) -> pd.DataFrame:
        """Evaluate all models on the dataset.

        Args:
            X: Feature DataFrame.
            y: Labels Series.
            test_size: Fraction of data to use for testing.

        Returns:
            DataFrame comparing model performance.
        """
        from sklearn.model_selection import train_test_split

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )

        results = []

        for model in self.models:
            # Train if required
            if model.requires_training:
                model.fit(X_train, y_train)

            # Evaluate
            metrics = model.score(X_test, y_test)
            metrics["model"] = model.name

            results.append(metrics)

        self.results = results
        return pd.DataFrame(results).set_index("model")

    def get_best_model(self, metric: str = "mae") -> str:
        """Get the name of the best performing model.

        Args:
            metric: Metric to use for comparison (lower is better for mae/rmse).

        Returns:
            Name of the best model.
        """
        if not self.results:
            return ""

        df = pd.DataFrame(self.results)

        if metric in ["mae", "rmse"]:
            best_idx = df[metric].idxmin()
        else:
            best_idx = df[metric].idxmax()

        return df.loc[best_idx, "model"]
