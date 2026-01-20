# Configuration Module

The `config` module provides centralized configuration management for the MIDAS application. It handles loading settings from Excel files, managing application state, and defining reference data types.

## Configurable Values

### Degradation Settings (`DegradationSettings`)

| Setting                              | Type  | Default | Description                                            |
|--------------------------------------|-------|---------|--------------------------------------------------------|
| `condition_index_degraded_threshold` | float | 25.0    | CI value below which an entity is considered degraded  |
| `resiliency_grade_threshold`         | int   | 70      | Percentage threshold for calculating resiliency grades |
| `initial_condition_index`            | float | 99.99   | Assumed initial CI for all new entities                |
| `max_time_series_years`              | int   | 10      | Maximum years of time series history to include        |

### Simulation Settings (`SimulationSettings`)

| Setting                                       | Type            | Default | Description                                       |
|-----------------------------------------------|-----------------|---------|---------------------------------------------------|
| `facilities_per_installation`                 | tuple[int, int] | (8, 14) | Min/max facilities to generate per installation   |
| `dependency_chain_group_range`                | tuple[int, int] | (1, 3)  | Range for dependency chain group IDs              |
| `maximum_system_age`                          | int             | 80      | Maximum age (years) for simulated systems         |
| `maximum_facility_age`                        | int             | 80      | Maximum age (years) for simulated facilities      |
| `facility_condition_randomly_degrades_chance` | int             | 35      | Percentage chance of random condition degradation |

### Output Settings (`OutputSettings`)

| Setting                   | Type | Default                | Description                       |
|---------------------------|------|------------------------|-----------------------------------|
| `json_indent`             | int  | 2                      | Indentation level for JSON output |
| `excel_sheet_main`        | str  | "Main Data"            | Name of main Excel sheet          |
| `excel_sheet_facility_ts` | str  | "Facility Time Series" | Facility time series sheet name   |
| `excel_sheet_system_ts`   | str  | "System Time Series"   | System time series sheet name     |
| `excel_sheet_metadata`    | str  | "_metadata"            | Metadata sheet name               |
| `metadata_file_suffix`    | str  | "_metadata.json"       | Suffix for metadata files         |
| `csv_table_separator`     | str  | "_"                    | Separator for CSV table names     |

### Simulation Distributions (`SimulationDistributions`)

Probability distributions control random value generation:

| Distribution      | Default Segments                                 | Description                            |
|-------------------|--------------------------------------------------|----------------------------------------|
| `condition_index` | 7% → 1-50, 88% → 50-85, 5% → 85-100              | Distribution for simulated CI values   |
| `age`             | 10% → 0-9, 20% → 10-20, 50% → 20-40, 20% → 41-80 | Distribution for simulated ages        |
| `grade`           | 52% → G1, 32% → G2, 12% → G3, 4% → G4            | Distribution for UFC resiliency grades |

### Reference Data Types

#### Facility Types (from Excel "Facilities" sheet)

| Field                 | Type | Description                |
|-----------------------|------|----------------------------|
| `key`                 | int  | Unique identifier          |
| `title`               | str  | Human-readable name        |
| `life_expectancy`     | int  | Expected lifespan in years |
| `mission_criticality` | int  | Importance rating (1-5)    |

#### System Types (from Excel "Systems" sheet)

| Field             | Type            | Description                                        |
|-------------------|-----------------|----------------------------------------------------|
| `key`             | int             | Unique identifier                                  |
| `title`           | str             | Human-readable name                                |
| `life_expectancy` | int             | Expected lifespan in years                         |
| `facility_keys`   | tuple[int, ...] | Valid facility type keys this system can belong to |

## Configuration Loading Process

1. **Initialization**: `ApplicationState.initialize()` is called at startup
2. **Path Resolution**: Defaults to `src/config/midas_config_values.xlsx` if no path provided
3. **Excel Parsing**: `load_settings_from_excel()` reads the Excel file:
   - Loads facility types from "Facilities" sheet
   - Loads system types from "Systems" sheet
   - Loads config values from "Config" sheet (key-value pairs)
4. **Validation**: Warnings are added for missing sheets or invalid data
5. **State Management**: Settings are stored in `ApplicationState` singleton
6. **Access**: Use `get_app_state().settings` to access configuration anywhere

## Module Structure

```
config/
├── __init__.py           # Public API exports
├── app_state.py          # ApplicationState singleton and load tracking
├── display.py            # Rich tables/panels for CLI display
├── loader.py             # Excel file parsing logic
├── reference_data.py     # FacilityType and SystemType dataclasses
├── settings.py           # MIDASSettings and sub-settings classes
└── functions/
    └── configure_logging.py  # Logging setup utility
```

## Usage Example

```python
from src.config import get_app_state, MIDASSettings

# Get the global application state
state = get_app_state()

# Access settings
threshold = state.settings.degradation.condition_index_degraded_threshold
facility_types = state.settings.facility_types

# Load custom configuration
custom_settings = MIDASSettings.from_excel(Path("custom_config.xlsx"))
```
