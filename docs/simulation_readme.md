# Simulation Module

The `simulation` module generates synthetic infrastructure data and exports it to various file formats. It creates realistic installations, facilities, and systems with proper dependency hierarchies and probability-based attribute values.

## Module Structure

```
simulation/
├── __init__.py           # Public API exports
├── distributions.py      # Probability distribution classes
├── generator.py          # Data generation logic
└── export/
    ├── __init__.py
    ├── config.py         # Export configuration
    ├── enums.py          # Output format/layout enums
    ├── exporter.py       # Main export interface
    ├── transformers.py   # Entity-to-DataFrame conversion
    └── formatters/
        ├── __init__.py
        ├── base.py           # Abstract formatter base
        ├── csv_formatter.py  # CSV output
        ├── excel_formatter.py # Excel output
        └── json_formatter.py  # JSON output
```

## Data Generation

### SimulationConfig

| Setting | Default | Description |
|---------|---------|-------------|
| `facilities_per_installation` | (8, 14) | Range of facilities per installation |
| `dependency_group_range` | (1, 3) | Range for dependency chain group IDs |
| `max_facility_age` | 80 | Maximum facility age in years |
| `max_system_age` | 80 | Maximum system age in years |
| `condition_index_distribution` | See below | CI value distribution |
| `age_distribution` | See below | Age distribution |
| `grade_distribution` | See below | UFC grade distribution |

### DegradationPattern

Enum for different degradation simulation curves (for future use):

| Pattern | Description |
|---------|-------------|
| `LINEAR` | Steady, constant decline |
| `EXPONENTIAL` | Accelerating decline over time |
| `STEPPED` | Sudden drops at intervals |
| `BATHTUB` | Early failures, stable period, then wear-out |

### DataGenerator

Creates complete installation hierarchies with:

1. **Installations**: Container with title and aggregated CI
2. **Facilities**: Typed entities with dependency chains and resiliency grades
3. **Systems**: Lowest-level components with direct CI measurements

```python
generator = DataGenerator(settings, config, seed=42)

# Single installation
installation, facilities, systems = generator.generate_installation()

# Multiple installations
installations, all_facilities, all_systems = generator.generate_installations(count=100)
```

### Generation Process

1. **Create Installation**: Generate UUID and title
2. **Generate Facilities**: 
   - Select random count from `facilities_per_installation` range
   - Assign facility types (prefer unused types for variety)
   - Generate dependency chains
   - Sample year constructed from age distribution
3. **Generate Systems**:
   - Look up valid system types for each facility type
   - Create one system per type (or random count if no types defined)
   - Sample condition index and construction year
4. **Calculate Aggregates**:
   - Facility CI = average of system CIs
   - Installation CI = average of facility CIs
5. **Assign Resiliency Grades**:
   - Bottom-up based on dependency relationships
   - Uses 70% majority threshold

### Dependency Chain Validation

The generator ensures valid dependency hierarchies:
- Secondary facilities must have a Primary in the same group
- Tertiary facilities must have Primary or Secondary support
- "Floating" facilities are elevated to Primary

## Probability Distributions

### ProbabilitySegment

Represents a weighted segment in a distribution:

```python
segment = ProbabilitySegment(percentage=50, value="20-40")
segment.sample()  # Returns random float between 20 and 40
```

### ProbabilityDistribution

Collection of segments for random sampling:

```python
dist = ProbabilityDistribution([
    ProbabilitySegment(7, "1-50"),    # 7% chance: CI between 1-50
    ProbabilitySegment(88, "50-85"),  # 88% chance: CI between 50-85
    ProbabilitySegment(5, "85-100"),  # 5% chance: CI between 85-100
])

selected_segment = dist.select_random_segment()
value = selected_segment.sample()
```

## Data Export

### ExportConfig

| Setting | Type | Description |
|---------|------|-------------|
| `file_name` | str | Base name for output files |
| `output_format` | OutputFormat | CSV, JSON, or XLSX |
| `output_directory` | Path | Directory for output files |
| `include_time_series` | bool | Generate time series data |
| `layout` | OutputLayout | Normalized or denormalized |
| `generate_metadata` | bool | Create metadata JSON file |
| `description` | str | Dataset description |

### OutputFormat

| Format | Description |
|--------|-------------|
| `CSV` | Separate CSV files per entity type |
| `JSON` | Single JSON file with nested structure |
| `XLSX` | Excel workbook with multiple sheets |

### OutputLayout

| Layout | Description |
|--------|-------------|
| `NORMALIZED` | Separate tables for installations, facilities, systems |
| `DENORMALIZED` | Single flattened table with all data |

### DataExporter

Main interface for generating and exporting data:

```python
exporter = DataExporter(
    file_name="my_dataset",
    output_format="xlsx",
    output_directory="./output",
    include_time_series=True,
    layout="normalized",
)

# Generate new data and export
path = exporter.generate_and_export(
    method="installations",
    target_count=50,
)

# Or export existing data
path = exporter.export_existing(installations, facilities, systems)
```

### Generation Methods

| Method | Description |
|--------|-------------|
| `default` | Single installation with its facilities and systems |
| `installations` | Multiple complete installations (requires `target_count`) |
| `facilities` | Target number of facilities across installations |

### Output Structure

For `file_name="dataset"` with CSV format:

```
dataset/
├── dataset_facilities.csv
├── dataset_installations.csv
├── dataset_systems.csv
├── dataset_facility_time_series.csv  (if include_time_series)
├── dataset_system_time_series.csv    (if include_time_series)
└── dataset_metadata.json
```

## Metadata

Each export generates a metadata JSON file containing:

```json
{
  "generated_at": "2024-01-15T10:30:00",
  "description": "Training dataset",
  "generation_method": "installations",
  "target_count": 50,
  "output_format": "csv",
  "layout": "normalized",
  "include_time_series": false,
  "counts": {
    "installations": 50,
    "facilities": 523,
    "systems": 2847
  }
}
```

## Usage Example

```python
from src.config import MIDASSettings
from src.simulation import DataGenerator, DataExporter, SimulationConfig

# Configure and generate
settings = MIDASSettings.from_excel(Path("config.xlsx"))
config = SimulationConfig.from_settings(settings)

generator = DataGenerator(settings, config, seed=42)
installations, facilities, systems = generator.generate_installations(100)

# Export to Excel
exporter = DataExporter(
    file_name="training_data",
    output_format="xlsx",
    output_directory="./datasets",
    include_time_series=True,
    description="ML training dataset with 100 installations",
    settings=settings,
)

output_path = exporter.export_existing(installations, facilities, systems)
print(f"Exported to: {output_path}")
```
