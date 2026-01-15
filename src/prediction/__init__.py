"""Prediction module for degradation forecasting.

This module provides:
- Feature extraction from domain entities
- Multiple prediction models (analytical and ML-based)
- Training dataset generation
- Model evaluation utilities
"""

from .datasets import DatasetConfig, LabelType, ModelEvaluator, TrainingDataGenerator
from .features import DegradationFeatures, FeatureExtractor
from .models import DegradationModel, ExponentialDecayModel, Prediction, SklearnRegressionModel

__all__ = [
    # Features
    "DegradationFeatures",
    "FeatureExtractor",
    # Models
    "DegradationModel",
    "Prediction",
    "ExponentialDecayModel",
    "SklearnRegressionModel",
    # Datasets
    "DatasetConfig",
    "LabelType",
    "TrainingDataGenerator",
    "ModelEvaluator",
]
