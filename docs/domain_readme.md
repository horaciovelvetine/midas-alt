# Domain Module

The `domain` module contains the core business entities and enumerations for the MIDAS application. These are pure data containers with no business logic—all computation is handled by services in the `prediction/` and `simulation/` modules.

## Entity Hierarchy

MIDAS uses a three-level hierarchy representing infrastructure assets:

```
Installation
    └── Facility (1:N)
            └── System (1:N)
```

### Installation

The top-level container representing a physical location or site.

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | str | Unique UUID identifier |
| `title` | str | Human-readable name |
| `facility_ids` | list[str] | Child facility references |
| `condition_index` | float | Aggregate CI (computed from facilities) |

### Facility

A building or infrastructure unit within an installation.

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | str | Unique UUID identifier |
| `facility_type_key` | int | Reference to facility type definition |
| `year_constructed` | int | Year the facility was built |
| `dependency_chain` | DependencyChain | Position in dependency hierarchy |
| `resiliency_grade` | UFCGrade | UFC 4-141-03 redundancy grade |
| `installation_id` | str | Parent installation reference |
| `system_ids` | list[str] | Child system references |
| `condition_index` | float | Aggregate CI (computed from systems) |

### System

The lowest level—individual components within a facility.

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | str | Unique UUID identifier |
| `system_type_key` | int | Reference to system type definition |
| `year_constructed` | int | Year the system was installed |
| `condition_index` | float | Directly measured/simulated CI value |
| `facility_id` | str | Parent facility reference |

## Dependency Chain

The `DependencyChain` class models facility interdependencies within an installation.

### Structure

- **Tier**: Position in the hierarchy (Primary → Secondary → Tertiary)
- **Group IDs**: Numeric identifiers linking dependent facilities
- **Position String**: Compact format like "P12" (Primary, groups 1 and 2)

### Dependency Flow

```
PRIMARY (P)     ← No dependencies, supports others
    ↓
SECONDARY (S)   ← Depends on Primary
    ↓
TERTIARY (T)    ← Depends on Primary or Secondary
```

Facilities share group IDs to indicate dependency relationships. A facility depends on another if it's higher in the hierarchy and shares at least one group ID.

## Enumerations

### UFCGrade

UFC 4-141-03 Resiliency Grades indicate redundancy and fault-tolerance:

| Grade | Value | Description |
|-------|-------|-------------|
| G1 | 1 | No redundancy, maintenance causes downtime |
| G2 | 2 | Some component redundancy, single path to critical loads |
| G3 | 3 | Concurrently maintainable, N+1 redundancy |
| G4 | 4 | Fault-tolerant, 2N redundancy with automatic failover |

### DependencyTier

Hierarchy positions for facilities:

| Tier | Value | Description |
|------|-------|-------------|
| PRIMARY | "P" | Top-level, no dependencies |
| SECONDARY | "S" | Mid-level, depends on Primary |
| TERTIARY | "T" | Bottom-level, depends on Secondary or Primary |

### EntityType

Used for ML feature extraction to identify entity source:

| Type | Value |
|------|-------|
| INSTALLATION | "installation" |
| FACILITY | "facility" |
| SYSTEM | "system" |

## Design Principles

1. **Pure Data**: Entities are dataclasses with no business logic
2. **Immutable References**: Child entities store IDs, not object references
3. **Computed Properties**: Age calculations use current date
4. **Type Aliases**: `PredictableEntity = Facility | System` for ML compatibility

## Module Structure

```
domain/
├── __init__.py    # Public API exports
├── entities.py    # Installation, Facility, System, DependencyChain
└── enums.py       # UFCGrade, DependencyTier, EntityType
```

## Usage Example

```python
from src.domain import Installation, Facility, System, DependencyChain, DependencyTier, UFCGrade

# Create a facility with dependency chain
facility = Facility(
    facility_type_key=5,
    year_constructed=2010,
    dependency_chain=DependencyChain(
        tier=DependencyTier.PRIMARY,
        group_ids=[1, 2]
    ),
    resiliency_grade=UFCGrade.G3,
)

# Check dependency
print(facility.dependency_position)  # "P12"
print(facility.age_years)            # Computed from year_constructed
```
