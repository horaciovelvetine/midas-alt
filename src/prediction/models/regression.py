"""Sklearn-based regression models for degradation prediction."""

from typing import Any

import numpy as np
import pandas as pd

from .base import DegradationModel, Prediction


class SklearnRegressionModel(DegradationModel):
    """Wrapper for sklearn regression models.

    Supports various sklearn regressors with a unified interface.
    The model predicts months_to_degradation from features.
    """

    # Columns to drop before fitting (identifiers, not features)
    NON_FEATURE_COLUMNS = [
        "entity_id",
        "entity_type",
        "snapshot_timestamp",
    ]

    def __init__(
        self,
        model_type: str = "random_forest",
        random_state: int = 42,
        **model_kwargs: Any,
    ):
        """Initialize with sklearn model type.

        Args:
            model_type: Type of sklearn model to use. Options:
                - "random_forest": RandomForestRegressor
                - "gradient_boosting": GradientBoostingRegressor
                - "ridge": Ridge regression
                - "xgboost": XGBRegressor (if installed)
            random_state: Random seed for reproducibility.
            **model_kwargs: Additional arguments passed to the model constructor.
        """
        self._model_type = model_type
        self._random_state = random_state
        self._model_kwargs = model_kwargs
        self._model = self._create_model()
        self._feature_columns: list[str] | None = None
        self._is_fitted = False

    @property
    def name(self) -> str:
        return f"sklearn_{self._model_type}"

    def _create_model(self):
        """Create the sklearn model instance."""
        if self._model_type == "random_forest":
            from sklearn.ensemble import RandomForestRegressor

            return RandomForestRegressor(
                n_estimators=self._model_kwargs.get("n_estimators", 100),
                max_depth=self._model_kwargs.get("max_depth", 15),
                min_samples_split=self._model_kwargs.get("min_samples_split", 5),
                random_state=self._random_state,
                n_jobs=-1,
            )

        elif self._model_type == "gradient_boosting":
            from sklearn.ensemble import GradientBoostingRegressor

            return GradientBoostingRegressor(
                n_estimators=self._model_kwargs.get("n_estimators", 100),
                max_depth=self._model_kwargs.get("max_depth", 5),
                learning_rate=self._model_kwargs.get("learning_rate", 0.1),
                random_state=self._random_state,
            )

        elif self._model_type == "ridge":
            from sklearn.linear_model import Ridge

            return Ridge(
                alpha=self._model_kwargs.get("alpha", 1.0),
                random_state=self._random_state,
            )

        elif self._model_type == "xgboost":
            try:
                from xgboost import XGBRegressor

                return XGBRegressor(
                    n_estimators=self._model_kwargs.get("n_estimators", 100),
                    max_depth=self._model_kwargs.get("max_depth", 6),
                    learning_rate=self._model_kwargs.get("learning_rate", 0.1),
                    random_state=self._random_state,
                    n_jobs=-1,
                )
            except ImportError:
                raise ImportError(
                    "XGBoost is not installed. Install with: pip install xgboost"
                )

        else:
            raise ValueError(f"Unknown model type: {self._model_type}")

    def _prepare_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for the model.

        - Drops non-feature columns
        - Encodes categorical variables
        - Handles missing values
        """
        # Drop identifier columns
        feature_cols = [c for c in X.columns if c not in self.NON_FEATURE_COLUMNS]
        X_features = X[feature_cols].copy()

        # Encode categorical columns (dependency_tier)
        if "dependency_tier" in X_features.columns:
            X_features["dependency_tier"] = (
                X_features["dependency_tier"]
                .map({"P": 0, "S": 1, "T": 2})
                .fillna(-1)
                .astype(int)
            )

        # Fill missing values
        X_features = X_features.fillna(0).infer_objects(copy=False)

        # Convert any remaining object columns to numeric
        for col in X_features.select_dtypes(include=["object"]).columns:
            X_features[col] = pd.to_numeric(X_features[col], errors="coerce").fillna(0)

        return X_features

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "SklearnRegressionModel":
        """Train the model on labeled data.

        Args:
            X: Feature DataFrame.
            y: Target Series (months_to_degradation).

        Returns:
            self for method chaining.
        """
        X_prepared = self._prepare_features(X)
        self._feature_columns = list(X_prepared.columns)

        self._model.fit(X_prepared, y)
        self._is_fitted = True

        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict months to degradation.

        Args:
            X: Feature DataFrame.

        Returns:
            Array of predicted months.
        """
        if not self._is_fitted:
            raise RuntimeError("Model must be fitted before predicting")

        X_prepared = self._prepare_features(X)

        # Ensure columns match training
        if self._feature_columns:
            missing_cols = set(self._feature_columns) - set(X_prepared.columns)
            for col in missing_cols:
                X_prepared[col] = 0
            X_prepared = X_prepared[self._feature_columns]

        predictions = self._model.predict(X_prepared)

        # Ensure non-negative predictions
        return np.maximum(predictions, 0)

    def predict_with_uncertainty(
        self, X: pd.DataFrame, confidence: float = 0.8
    ) -> list[Prediction]:
        """Predict with uncertainty estimates.

        For tree-based models, uses individual tree predictions
        to estimate variance. For other models, uses a heuristic.
        """
        base_predictions = self.predict(X)

        # For Random Forest, we can get uncertainty from tree variance
        if self._model_type == "random_forest" and hasattr(
            self._model, "estimators_"
        ):
            X_prepared = self._prepare_features(X)
            if self._feature_columns:
                X_prepared = X_prepared[self._feature_columns]

            # Get predictions from all trees
            tree_predictions = np.array(
                [tree.predict(X_prepared) for tree in self._model.estimators_]
            )

            # Calculate percentiles
            margin = (1 - confidence) / 2
            low_percentile = margin * 100
            high_percentile = (1 - margin) * 100

            predictions = []
            for i in range(len(base_predictions)):
                tree_preds = tree_predictions[:, i]
                predictions.append(
                    Prediction(
                        months_to_degradation=float(base_predictions[i]),
                        confidence_low=float(
                            max(0, np.percentile(tree_preds, low_percentile))
                        ),
                        confidence_high=float(
                            np.percentile(tree_preds, high_percentile)
                        ),
                    )
                )

            return predictions

        # Fallback to simple heuristic
        return super().predict_with_uncertainty(X, confidence)

    def feature_importances(self) -> dict[str, float] | None:
        """Get feature importances if available.

        Returns:
            Dict of feature_name -> importance, or None if not available.
        """
        if not self._is_fitted or not self._feature_columns:
            return None

        if hasattr(self._model, "feature_importances_"):
            return dict(
                zip(self._feature_columns, self._model.feature_importances_)
            )

        if hasattr(self._model, "coef_"):
            return dict(zip(self._feature_columns, np.abs(self._model.coef_)))

        return None

    def get_top_features(self, n: int = 10) -> list[tuple[str, float]]:
        """Get the top N most important features.

        Args:
            n: Number of features to return.

        Returns:
            List of (feature_name, importance) tuples, sorted by importance.
        """
        importances = self.feature_importances()
        if importances is None:
            return []

        sorted_features = sorted(
            importances.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_features[:n]
