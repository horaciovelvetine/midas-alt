# MIDAS Codebase Structure Improvements

## Executive Summary

This document outlines recommendations for improving the MIDAS codebase structure to enhance maintainability, testability, and support for predictive modeling capabilities.

## Current Architecture Assessment

### Strengths
- ✅ Clear module separation (models, types, config, cli)
- ✅ Good use of type hints and protocols
- ✅ Strategy pattern for extensibility
- ✅ Existing predictive capability foundation

### Areas for Improvement
- ⚠️ Circular dependencies via runtime imports
- ⚠️ Singleton configuration pattern (hard to test)
- ⚠️ Missing unified prediction service
- ⚠️ Inconsistent API across model hierarchy

## Recommended Structure Changes

### 1. Service Layer for Predictions

**Current State:**
- Prediction logic scattered in `ConditionIndex` class
- No unified interface for predictions
- Installation missing predictive properties

**Proposed Structure:**
```
src/
├── services/              # NEW: Business logic layer
│   ├── __init__.py
│   ├── prediction_service.py    # Unified prediction interface
│   └── condition_index_service.py # Condition index calculations
├── models/
│   ├── installation.py
│   ├── facility.py
│   ├── system.py
│   └── condition_index.py  # Keep for core calculations
```

**Benefits:**
- Separation of concerns
- Easier testing
- Consistent API across all models
- Extensible for future prediction models

### 2. Configuration Management

**Current State:**
- `MIDASConfig` as singleton with class variables
- Hard to test
- Global state issues

**Proposed Structure:**
```python
# src/config/config.py
@dataclass(frozen=True)
class MIDASConfig:
    """Immutable configuration dataclass."""
    condition_index_degraded_threshold: int = 25
    maximum_system_age: int = 80
    # ... other config values
    
    @classmethod
    def from_excel(cls, path: Path) -> "MIDASConfig":
        """Load config from Excel file."""
        # Implementation
```

**Benefits:**
- Immutable configuration
- Easier testing (can create test configs)
- No global state
- Type-safe

### 3. Dependency Injection Pattern

**Current State:**
- Runtime imports to avoid circular dependencies
- Tight coupling

**Proposed Structure:**
```python
# src/services/prediction_service.py
class PredictionService:
    """Service for predicting condition index degradation."""
    
    def __init__(
        self,
        config: MIDASConfig,
        condition_index_calculator: ConditionIndexCalculator
    ):
        self._config = config
        self._calculator = condition_index_calculator
    
    def predict_degradation(
        self, 
        obj: HasConditionIndexAndAge
    ) -> ConditionIndexRecord | None:
        """Predict when object will degrade."""
        # Implementation
```

**Benefits:**
- No circular dependencies
- Testable (can inject mocks)
- Clear dependencies

### 4. Unified Prediction Interface

**Proposed API:**
```python
# All models get consistent predictive properties
class Installation:
    @property
    def degraded_state_anticipated(self) -> ConditionIndexRecord | None:
        """Predict when installation will degrade."""
        return self._prediction_service.predict_degradation(self)

class Facility:
    @property
    def degraded_state_anticipated(self) -> ConditionIndexRecord | None:
        """Predict when facility will degrade."""
        return self._prediction_service.predict_degradation(self)

class System:
    @property
    def degraded_state_anticipated(self) -> ConditionIndexRecord | None:
        """Predict when system will degrade."""
        return self._prediction_service.predict_degradation(self)
```

### 5. Enhanced Prediction Models

**Current State:**
- Single exponential decay model
- No support for different prediction strategies

**Proposed Structure:**
```python
# src/services/prediction/
├── __init__.py
├── base.py              # Abstract prediction model
├── exponential_decay.py # Current model
├── linear_decay.py      # Future: Linear model
└── ml_model.py          # Future: ML-based predictions
```

## Implementation Priority

### Phase 1: Foundation (High Priority)
1. Create `services/` directory structure
2. Extract prediction logic to `PredictionService`
3. Add `degraded_state_anticipated` to `Installation`
4. Create config dataclass (keep backward compatibility)

### Phase 2: Refactoring (Medium Priority)
1. Replace runtime imports with dependency injection
2. Update all models to use services
3. Add comprehensive tests

### Phase 3: Enhancement (Future)
1. Multiple prediction models
2. ML-based predictions
3. Confidence intervals
4. What-if scenario analysis

## Migration Strategy

1. **Incremental**: Keep existing code working while adding new structure
2. **Backward Compatible**: Maintain existing APIs during transition
3. **Test Coverage**: Add tests for new services before refactoring
4. **Documentation**: Update docs as changes are made

## File Structure Comparison

### Current
```
src/
├── models/
│   ├── installation.py
│   ├── facility.py
│   ├── system.py
│   └── condition_index.py
├── config/
│   └── midas_config.py  # Singleton
└── types/
```

### Proposed
```
src/
├── models/              # Domain models (data only)
│   ├── installation.py
│   ├── facility.py
│   └── system.py
├── services/            # Business logic
│   ├── prediction_service.py
│   └── condition_index_service.py
├── config/
│   ├── config.py        # Dataclass
│   └── loader.py        # Excel loading
└── types/
```

## Testing Strategy

### Current Issues
- Hard to test due to singleton config
- Runtime imports make mocking difficult

### Proposed Approach
```python
# tests/services/test_prediction_service.py
def test_predict_degradation():
    config = MIDASConfig(condition_index_degraded_threshold=25)
    service = PredictionService(config, mock_calculator)
    facility = create_test_facility()
    result = service.predict_degradation(facility)
    assert result is not None
```

## Python Best Practices Alignment

### ✅ Already Following
- Type hints
- Docstrings
- Dataclasses for simple data
- Protocols for duck typing

### 🔄 Should Improve
- **Dependency Injection**: Replace runtime imports
- **Immutability**: Use frozen dataclasses for config
- **Single Responsibility**: Extract services from models
- **Interface Segregation**: Separate prediction interfaces
- **Dependency Inversion**: Depend on abstractions, not concretions

## Next Steps

1. Review and approve structure changes
2. Create `services/` directory
3. Implement `PredictionService` with tests
4. Add `degraded_state_anticipated` to `Installation`
5. Gradually migrate existing code
6. Update documentation
