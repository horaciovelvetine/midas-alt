#!/usr/bin/env python3
"""Demo script showing the ML prediction pipeline.

This script demonstrates:
1. Generating synthetic training data
2. Extracting features from domain entities
3. Training multiple prediction models
4. Comparing model performance

Run from project root:
    uv run python examples/ml_prediction_demo.py
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import MIDASSettings
from src.prediction import (
    DatasetConfig,
    ExponentialDecayModel,
    LabelType,
    ModelEvaluator,
    SklearnRegressionModel,
    TrainingDataGenerator,
)


def main():
    """Run the ML prediction demo."""
    print("=" * 60)
    print("MIDAS ML Prediction Demo")
    print("=" * 60)

    # Load settings (use defaults if no config file)
    config_path = Path(__file__).parent.parent / "src" / "config" / "midas_config_values.xlsx"
    
    if config_path.exists():
        print(f"\nLoading settings from: {config_path}")
        settings = MIDASSettings.from_excel(config_path)
        print(f"  Loaded {len(settings.facility_types)} facility types")
        print(f"  Loaded {len(settings.system_types)} system types")
    else:
        print("\nUsing default settings (no config file found)")
        settings = MIDASSettings.with_defaults()

    # Configure dataset generation
    print("\n" + "-" * 60)
    print("Step 1: Generate Training Data")
    print("-" * 60)

    dataset_config = DatasetConfig(
        n_installations=50,  # Generate 50 installations
        label_type=LabelType.MONTHS_TO_DEGRADATION,
        degradation_threshold=25.0,
        seed=42,  # For reproducibility
    )

    generator = TrainingDataGenerator(settings=settings, config=dataset_config)

    # Generate facility-only dataset
    print("\nGenerating facility dataset...")
    X_facilities, y_facilities = generator.generate_facility_dataset()
    print(f"  Generated {len(X_facilities)} facility samples")
    print(f"  Feature columns: {len(X_facilities.columns)}")

    # Show sample features
    print("\nSample features (first row):")
    sample = X_facilities.iloc[0]
    for col in ["condition_index", "age_months", "life_expectancy_months", 
                "mission_criticality", "resiliency_grade", "remaining_life_ratio"]:
        if col in sample:
            print(f"  {col}: {sample[col]}")

    print(f"\nLabel distribution:")
    print(f"  Min months to degradation: {y_facilities.min():.1f}")
    print(f"  Max months to degradation: {y_facilities.max():.1f}")
    print(f"  Mean months to degradation: {y_facilities.mean():.1f}")

    # Train and evaluate models
    print("\n" + "-" * 60)
    print("Step 2: Train Prediction Models")
    print("-" * 60)

    models = [
        ExponentialDecayModel(degradation_threshold=25.0),
        SklearnRegressionModel(model_type="ridge"),
        SklearnRegressionModel(model_type="random_forest", n_estimators=50),
        SklearnRegressionModel(model_type="gradient_boosting", n_estimators=50),
    ]

    print(f"\nModels to evaluate: {[m.name for m in models]}")

    evaluator = ModelEvaluator(models)
    results = evaluator.evaluate_all(X_facilities, y_facilities, test_size=0.2)

    print("\n" + "-" * 60)
    print("Step 3: Model Comparison Results")
    print("-" * 60)

    print("\nMetrics (lower MAE/RMSE is better, higher R2/accuracy is better):")
    print(results.to_string())

    # Get best model
    best_model_name = evaluator.get_best_model(metric="mae")
    print(f"\nBest model (by MAE): {best_model_name}")

    # Show feature importances for Random Forest
    print("\n" + "-" * 60)
    print("Step 4: Feature Importance (Random Forest)")
    print("-" * 60)

    rf_model = models[2]  # Random Forest
    top_features = rf_model.get_top_features(n=8)
    
    if top_features:
        print("\nTop features:")
        for feature, importance in top_features:
            print(f"  {feature}: {importance:.4f}")

    # Make predictions on new data
    print("\n" + "-" * 60)
    print("Step 5: Make Predictions with Uncertainty")
    print("-" * 60)

    # Get predictions with confidence intervals
    sample_X = X_facilities.head(5)
    sample_y = y_facilities.head(5)

    predictions = rf_model.predict_with_uncertainty(sample_X, confidence=0.8)

    print("\nSample predictions (Random Forest with 80% confidence interval):")
    print(f"{'Actual':>10} | {'Predicted':>10} | {'Low':>8} | {'High':>8} | {'Error':>8}")
    print("-" * 55)
    
    for i, (pred, actual) in enumerate(zip(predictions, sample_y)):
        error = abs(pred.months_to_degradation - actual)
        print(
            f"{actual:>10.1f} | {pred.months_to_degradation:>10.1f} | "
            f"{pred.confidence_low:>8.1f} | {pred.confidence_high:>8.1f} | {error:>8.1f}"
        )

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
