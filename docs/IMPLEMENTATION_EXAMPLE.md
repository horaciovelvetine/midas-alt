# Implementation Example: Prediction Service

This document shows a concrete example of how to implement the improved structure for predictive modeling.

## Example: Prediction Service Implementation

### Step 1: Create Service Interface

```python
# src/services/__init__.py
"""Services layer for business logic."""

from .prediction_service import PredictionService
from .condition_index_service import ConditionIndexService

__all__ = ["PredictionService", "ConditionIndexService"]
```

### Step 2: Prediction Service

```python
# src/services/prediction_service.py
"""Service for predicting condition index degradation."""

from datetime import datetime
from typing import Protocol

from ..models.condition_index import ConditionIndex
from ..types import ConditionIndexRecord
from ..config import MIDASConfig


class HasConditionIndexAndAge(Protocol):
    """Protocol for objects that can be predicted."""
    condition_index: float | None
    age: int | None


class PredictionService:
    """Service for predicting when objects will degrade below threshold."""
    
    def __init__(self, config: MIDASConfig):
        """Initialize prediction service.
        
        Args:
            config: MIDAS configuration instance.
        """
        self._config = config
    
    def predict_degradation(
        self,
        obj: HasConditionIndexAndAge
    ) -> ConditionIndexRecord | None:
        """Predict when an object's condition index will fall below degraded threshold.
        
        Args:
            obj: Object with condition_index and age properties.
            
        Returns:
            ConditionIndexRecord with predicted degradation date, or None if:
            - Object data is invalid
            - Decay rate cannot be calculated
            - Object will never degrade
        """
        if not self._validate_object(obj):
            return None
        
        now = datetime.now()
        current_index = obj.condition_index
        degraded_threshold = self._config.condition_index_degraded_threshold
        
        # If already degraded, return current date
        if current_index <= degraded_threshold:
            return ConditionIndexRecord(
                year=now.year,
                month=now.month,
                value=current_index
            )
        
        # Calculate decay rate
        age_in_months = self._calculate_age_in_months(obj, now)
        decay_rate = ConditionIndex._calculate_decay_rate(
            current_index,
            age_in_months,
            ConditionIndex.INITIAL_CONDITION_INDEX
        )
        
        if decay_rate is None or decay_rate <= 0:
            return None
        
        # Predict future degradation
        return self._calculate_degradation_date(
            current_index,
            decay_rate,
            degraded_threshold,
            now
        )
    
    def _validate_object(self, obj: HasConditionIndexAndAge) -> bool:
        """Validate object has required data."""
        return (
            obj is not None
            and obj.condition_index is not None
            and obj.age is not None
        )
    
    def _calculate_age_in_months(
        self,
        obj: HasConditionIndexAndAge,
        reference_date: datetime
    ) -> int:
        """Calculate object age in months."""
        if obj.age is None:
            return 0
        return obj.age * 12 + reference_date.month - 1
    
    def _calculate_degradation_date(
        self,
        current_index: float,
        decay_rate: float,
        threshold: float,
        reference_date: datetime
    ) -> ConditionIndexRecord | None:
        """Calculate when degradation will occur."""
        import math
        
        if decay_rate >= 1.0:
            return None
        
        try:
            months_from_now = math.log(threshold / current_index) / math.log(1 - decay_rate)
        except (ValueError, ZeroDivisionError):
            return None
        
        total_months = round(months_from_now)
        year, month = self._calculate_date_months_from_now(reference_date, total_months)
        
        return ConditionIndexRecord(
            year=year,
            month=month,
            value=threshold
        )
    
    def _calculate_date_months_from_now(
        self,
        reference_date: datetime,
        months_from_now: int
    ) -> tuple[int, int]:
        """Calculate date N months from reference date."""
        year = reference_date.year
        month = reference_date.month + months_from_now
        
        while month > 12:
            year += 1
            month -= 12
        
        while month < 1:
            year -= 1
            month += 12
        
        return (year, month)
```

### Step 3: Update Models to Use Service

```python
# src/models/installation.py (updated)
"""Installation model with prediction support."""

import uuid
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .facility import Facility
    from ..services.prediction_service import PredictionService


class Installation:
    """Represents an installation containing multiple facilities."""
    
    def __init__(
        self,
        title: str | None = "",
        prediction_service: Optional["PredictionService"] = None
    ) -> None:
        """Initialize an installation instance.
        
        Args:
            title: Installation title.
            prediction_service: Optional prediction service for degradation predictions.
        """
        self._id: str = str(uuid.uuid4())
        self._title: str = title
        self._facilities: list["Facility"] = []
        self._prediction_service = prediction_service
    
    @property
    def degraded_state_anticipated(self) -> "ConditionIndexRecord | None":
        """Predict when installation will degrade below threshold.
        
        Returns:
            ConditionIndexRecord with predicted degradation date, or None.
        """
        if self._prediction_service is None:
            # Fallback to direct calculation for backward compatibility
            from .condition_index import ConditionIndex
            return ConditionIndex.find_degraded_state_anticipated(self)
        
        return self._prediction_service.predict_degradation(self)
    
    # ... rest of existing code ...
```

### Step 4: Configuration as Dataclass

```python
# src/config/config.py
"""Configuration dataclass for MIDAS application."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..types import FacilityType, SystemType


@dataclass(frozen=True)
class MIDASConfig:
    """Immutable configuration for MIDAS application."""
    
    # Thresholds
    condition_index_degraded_threshold: int = 25
    resiliency_grade_threshold: int = 70
    
    # Age limits
    maximum_system_age: int = 80
    maximum_facility_age: int = 80
    
    # Random degradation
    facility_condition_randomly_degrades_chance: int = 35
    
    # Facility and system types
    facilities: tuple[FacilityType, ...] = ()
    systems: tuple[SystemType, ...] = ()
    
    # Output configuration
    output_json_indent: int = 2
    output_excel_sheet_main_name: str = "Main Data"
    # ... other output configs ...
    
    @classmethod
    def from_excel(cls, path: Path) -> "MIDASConfig":
        """Load configuration from Excel file.
        
        Args:
            path: Path to Excel configuration file.
            
        Returns:
            MIDASConfig instance loaded from Excel.
        """
        # Implementation would use existing loading logic
        # but return a new config instance instead of modifying class variables
        pass
    
    def get_facility_type_by_key(self, key: int) -> FacilityType | None:
        """Get facility type by key."""
        for facility in self.facilities:
            if facility.key == key:
                return facility
        return None
    
    def get_system_types_by_facility_key(self, key: int) -> list[SystemType]:
        """Get system types for a facility key."""
        return [
            system for system in self.systems
            if key in system.facility_keys
        ]
```

### Step 5: Factory for Creating Models with Services

```python
# src/models/factory.py
"""Factory for creating models with proper service injection."""

from typing import Optional

from ..config import MIDASConfig
from ..services.prediction_service import PredictionService
from .installation import Installation
from .facility import Facility
from .system import System


class ModelFactory:
    """Factory for creating models with injected services."""
    
    def __init__(self, config: MIDASConfig):
        """Initialize factory.
        
        Args:
            config: MIDAS configuration.
        """
        self._config = config
        self._prediction_service = PredictionService(config)
    
    def create_installation(self, title: str | None = "") -> Installation:
        """Create an installation with services injected.
        
        Args:
            title: Installation title.
            
        Returns:
            Installation instance with prediction service.
        """
        return Installation(
            title=title,
            prediction_service=self._prediction_service
        )
    
    def create_facility(
        self,
        facility_type=None,
        year_constructed: int | None = None,
        # ... other params
    ) -> Facility:
        """Create a facility with services injected."""
        return Facility(
            facility_type=facility_type,
            year_constructed=year_constructed,
            prediction_service=self._prediction_service
            # ... other params
        )
    
    def create_system(
        self,
        system_type=None,
        condition_index_value: float | None = None,
        # ... other params
    ) -> System:
        """Create a system with services injected."""
        return System(
            system_type=system_type,
            condition_index_value=condition_index_value,
            prediction_service=self._prediction_service
            # ... other params
        )
```

### Step 6: Usage Example

```python
# Example: Using the improved structure

from src.config import MIDASConfig
from src.models.factory import ModelFactory

# Load configuration
config = MIDASConfig.from_excel(Path("src/config/midas_config_values.xlsx"))

# Create factory
factory = ModelFactory(config)

# Create models with services
installation = factory.create_installation("Main Base")
facility = factory.create_facility(facility_type=some_type, year_constructed=1990)
system = factory.create_system(system_type=some_system_type, condition_index_value=75.0)

# All models now have consistent prediction API
installation_prediction = installation.degraded_state_anticipated
facility_prediction = facility.degraded_state_anticipated
system_prediction = system.degraded_state_anticipated

print(f"Installation will degrade in: {installation_prediction}")
print(f"Facility will degrade in: {facility_prediction}")
print(f"System will degrade in: {system_prediction}")
```

## Benefits of This Approach

1. **Testability**: Easy to inject mock services in tests
2. **Consistency**: All models have same prediction API
3. **Extensibility**: Easy to add new prediction models
4. **No Circular Dependencies**: Clear dependency flow
5. **Type Safety**: Full type hints throughout
6. **Backward Compatible**: Can keep old code working during migration

## Migration Path

1. Create services directory and implement `PredictionService`
2. Add `degraded_state_anticipated` to `Installation` (using fallback)
3. Create `ModelFactory` for new code
4. Gradually migrate existing code to use factory
5. Eventually deprecate old patterns
