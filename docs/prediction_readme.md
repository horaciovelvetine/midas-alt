# Prediction Module

The `prediction` module provides machine learning and analytical models for forecasting infrastructure degradation. It extracts features from domain entities, trains models on simulated data, and predicts time to degradation.

## Module Structure

```
prediction/
├── __init__.py       # Public API exports
├── datasets.py       # Training data generation and model evaluation
├── features.py       # Feature extraction from domain entities
└── models/
    ├── __init__.py
    ├── base.py          # Abstract base class and Prediction dataclass
    ├── decay_model.py   # Analytical exponential decay baseline
    └── regression.py    # Sklearn-based ML models
```

## Feature Extraction

### DegradationFeatures

A feature vector containing all inputs for prediction models:

| Feature | Type | Description |
|---------|------|-------------|
| `condition_index` | float | Current CI value (0-100) |
| `age_months` | int | Entity age in months |
| `life_expectancy_months` | int | Expected lifespan from reference data |
| `facility_type_key` | int | Facility type identifier |
| `system_type_key` | int | System type identifier (None for facilities) |
| `mission_criticality` | int | Importance rating (1-5) |
| `resiliency_grade` | int | UFC grade (1-4, 0 if unknown) |
| `dependency_tier` | str | "P", "S", "T", or None |
| `dependency_group_count` | int | Number of dependency groups |
| `remaining_life_ratio` | float | age / life_expectancy (capped at 2.0) |
| `condition_age_ratio` | float | CI relative to expected CI for age |

### Historical Features (Optional)

| Feature | Type | Description |
|---------|------|-------------|
| `condition_index_lag_3mo` | float | CI value 3 months ago |
| `condition_index_lag_6mo` | float | CI value 6 months ago |
| `condition_index_lag_12mo` | float | CI value 12 months ago |
| `ci_delta_3mo` | float | CI change over last 3 months |
| `ci_delta_12mo` | float | CI change over last 12 months |

### FeatureExtractor

Extracts features from `Facility` or `System` entities, enriching with reference data (life expectancy, mission criticality) from configuration.

```python
extractor = FeatureExtractor(settings)
features = extractor.extract_facility_features(facility)
df = extractor.extract_batch([facility1, facility2, system1])
```

## Prediction Models

### Base Interface (`DegradationModel`)

All models implement this abstract interface:

| Method | Description |
|--------|-------------|
| `fit(X, y)` | Train on labeled data (no-op for analytical models) |
| `predict(X)` | Return array of predicted months to degradation |
| `predict_with_uncertainty(X)` | Return `Prediction` objects with confidence bounds |
| `score(X, y)` | Compute MAE, RMSE, R², and accuracy metrics |

### ExponentialDecayModel (Analytical Baseline)

Uses the PERT decay formula without requiring training:

```
CI(t) = CI_0 × (1 - R)^t
```

Where:
- `CI_0` = Initial condition index (99.99)
- `R` = Monthly decay rate (calculated from current CI and age)
- `t` = Time in months

**Key Properties:**
- No training required (`requires_training = False`)
- Serves as baseline for comparing ML models
- Generates trajectory predictions showing expected CI over time

### SklearnRegressionModel (ML Models)

Wrapper for sklearn regressors with automatic preprocessing:

| Model Type | Algorithm | Best For |
|------------|-----------|----------|
| `random_forest` | RandomForestRegressor | General use, feature importance |
| `gradient_boosting` | GradientBoostingRegressor | Complex patterns |
| `ridge` | Ridge | Linear relationships |
| `xgboost` | XGBRegressor | Large datasets (requires xgboost) |

**Features:**
- Automatic categorical encoding (`dependency_tier` → numeric)
- Missing value handling
- Feature importance extraction
- Uncertainty estimation (for Random Forest, uses tree variance)

## Dataset Generation

### DatasetConfig

| Setting | Default | Description |
|---------|---------|-------------|
| `n_installations` | 100 | Number of installations to generate |
| `label_type` | MONTHS_TO_DEGRADATION | Target variable type |
| `degradation_threshold` | 25.0 | CI threshold for "degraded" |
| `initial_ci` | 99.99 | Assumed starting CI |
| `include_historical` | False | Generate historical features |
| `seed` | 42 | Random seed for reproducibility |

### LabelType Options

| Type | Description |
|------|-------------|
| `MONTHS_TO_DEGRADATION` | Regression: months until CI < threshold |
| `DEGRADATION_RATE` | Regression: monthly CI loss rate |
| `WILL_DEGRADE_6MO` | Classification: degrade within 6 months? |
| `WILL_DEGRADE_12MO` | Classification: degrade within 12 months? |
| `WILL_DEGRADE_24MO` | Classification: degrade within 24 months? |

### TrainingDataGenerator

Generates labeled datasets by simulating entities and computing their time to degradation:

```python
generator = TrainingDataGenerator(settings, DatasetConfig(n_installations=200))
X, y = generator.generate()  # All entities
X, y = generator.generate_facility_dataset()  # Facilities only
X, y = generator.generate_system_dataset()    # Systems only
```

## Model Evaluation

### ModelEvaluator

Compare multiple models on the same dataset:

```python
evaluator = ModelEvaluator([
    ExponentialDecayModel(),
    SklearnRegressionModel("random_forest"),
    SklearnRegressionModel("gradient_boosting"),
])

results_df = evaluator.evaluate_all(X, y, test_size=0.2)
best_model = evaluator.get_best_model(metric="mae")
```

### Evaluation Metrics

| Metric | Description |
|--------|-------------|
| `mae` | Mean Absolute Error (months) |
| `rmse` | Root Mean Squared Error |
| `r2` | R² score |
| `within_6mo` | Proportion within 6 months of actual |
| `within_12mo` | Proportion within 12 months of actual |

## Usage Example

```python
from src.config import MIDASSettings
from src.prediction import (
    TrainingDataGenerator, DatasetConfig, FeatureExtractor,
    ExponentialDecayModel, SklearnRegressionModel, ModelEvaluator
)

# Generate training data
settings = MIDASSettings.from_excel(Path("config.xlsx"))
generator = TrainingDataGenerator(settings, DatasetConfig(n_installations=100))
X, y = generator.generate_facility_dataset()

# Train and evaluate models
models = [
    ExponentialDecayModel(),
    SklearnRegressionModel("random_forest"),
]

evaluator = ModelEvaluator(models)
results = evaluator.evaluate_all(X, y)
print(results)

# Make predictions with uncertainty
rf_model = models[1]
predictions = rf_model.predict_with_uncertainty(X[:5])
for pred in predictions:
    print(f"{pred.months_to_degradation:.1f} months ({pred.confidence_low:.1f}-{pred.confidence_high:.1f})")
```
