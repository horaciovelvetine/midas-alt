# MIDAS Simulation System Internals

Companion to [`README.md`](../README.md): user flows and file map stay there; this doc covers **runtime** shape—where data comes from, what **`SimulationSession`** owns, **`step()`** ordering, and how to add **`Base`** modules without fighting derived state.

**You will use this to decide:** what to mutate in `apply()`, what the session recomputes for you, and where UI ends (`simulation_shell.py`) vs simulation logic.

## One-Screen Mental Model

```mermaid
flowchart TD
    A["Workbook config (.xlsx)"]
    B["DataGenerator"]
    C["SimulationDataLoader"]
    D["GenerationResult -> installations, facilities, systems, work_orders"]
    E["SimulationSession.from_generation_result()"]
    F["Single active installation"]
    G["SimulationSession"]
    H["SimulationShell -> dashboard and controls"]
    I["Condition history export"]

    subgraph T["Per-tick flow inside SimulationSession.step()"]
        T1["Advance clock"]
        T2["Sync simulated ages"]
        T3["Run modules -> mutate systems and work orders"]
        T4["Recalculate parent CI -> facility from systems, installation from facilities"]
        T5["Record CI history snapshots"]
        T6["Run pause policies"]
        T1 --> T2 --> T3 --> T4 --> T5 --> T6
    end

    A --> B
    A --> C
    B --> D
    C --> D
    D --> E --> F --> G
    G --> T
    G --> H
    G --> I
```

One installation per session; **`SimulationSession`** owns mutable runtime state for that slice.

## The Main Pieces

### Configuration and reference data

`src/config/midas_config_values.xlsx` drives both generation behavior and several runtime rules.

Important runtime-relevant settings include:

- degradation thresholds
- facility and system age limits
- dependency-chain settings
- work-order distributions
- facility and system reference data

The settings loader builds a `MIDASSettings` object, which is passed into generators, loaders, exporters, and the runtime session.

### Generated or loaded data

Before anything can run in the live simulation, MIDAS needs a `GenerationResult`.

`GenerationResult` is a flat container with four lists:

- `installations`
- `facilities`
- `systems`
- `work_orders`

Relationships are stored by IDs on the models, not by a database or ORM layer. The session rebuilds lookup maps from those IDs when it starts.

### Runtime session

`src/simulation/runtime/session.py` is the heart of the runtime.

`SimulationSession` owns:

- the active installation subset
- the simulation clock
- module and pause-policy lists
- lookup indexes for facilities, systems, and work orders
- selection state used by the shell
- condition-index history
- critical-entity tracking used by pause policies

If you are adding runtime behavior, this is the file to understand first.

### Modules

`src/simulation/modules/base.py` defines the module contract:

```python
class Base(ABC):
    @abstractmethod
    def apply(self, session: SimulationSession) -> list[ModuleEvent]:
        ...
```

A module receives the active `SimulationSession`, mutates runtime state for the current tick, and can emit `ModuleEvent` records.

`ModuleEvent` carries:

- `code`
- `message`
- `entity_id`
- `entity_type`
- `should_pause`

Modules are run in list order during `SimulationSession.step()`.

### Built-in system degradation module

`src/simulation/modules/system_degradation.py` provides `SystemDegradationModule`, and the runtime CLI registers it by default when launching a live simulation session.

The module is intentionally narrow in scope:

- it mutates only system `condition_index`
- it resolves `SystemType` from `session.settings`
- it uses simulated system age and configured life expectancy to compute normalized age
- it scales deterioration to the active tick size
- it emits non-pausing events when a system drops into a worse condition band

The current model is passive only (no maintenance recovery, backlog penalties, or shock failures).

### Pause policies

Pause policies use the same `Base` contract, but conceptually they should evaluate state instead of advancing it.

The default policy is `CriticalStatePausePolicy`, which pauses the session when an entity newly becomes:

- inoperable
- mission blocked

It tracks prior critical entities so the same failure does not trigger a pause every tick.

### Shell and dashboard

`src/cli/simulation_shell.py` renders **`SimulationSession`** state only; keep business rules in modules or pause policies.

**Stack (top to bottom):** three summary panels (installation, simulation overview, work orders) → optional **Mission alerts** strip (red border: narrative, category counts, thresholds; **`a`** pauses and opens explainer + snapshot + “why” table + numbered drill-down to metrics, rules, sample WOs) → **Installation Graph** beside **Inspect**. Systems in the tree stay hidden until **`f`** or until a facility is focused (focus always expands that facility’s systems).

**Where to add behavior:** usually a **module**, a **pause policy**, or **session** helpers—not the shell.

## How Data Enters the Runtime

There are two supported entry paths:

1. Generate data in memory with `DataGenerator`
2. Load normalized exported data with `SimulationDataLoader`

Both produce a `GenerationResult`.

When `SimulationSession.from_generation_result(...)` is called, the session:

1. selects exactly one installation from the result set
2. deep-copies that single-installation subset
3. builds indexes
4. syncs simulated ages
5. recalculates aggregate condition indices
6. records the initial history snapshot at tick `0`
7. runs pause policies once against the initial state

That deep copy matters: modules mutate the session-owned copy, not the caller's original result object.

## The Tick Lifecycle

This is the core runtime loop inside `SimulationSession.step()`:

1. Clear the old stop reason.
2. Advance the clock and increment the tick index.
3. Recompute cached ages from the simulated date.
4. Run each module in order.
5. Recalculate facility and installation aggregate condition indices.
6. Record condition-index history snapshots for the whole hierarchy.
7. Run pause policies.
8. If any returned event has `should_pause=True`, pause the session using the first such event message.

The subsections below spell out what that order implies for module authors.

### Modules see the new date

When `apply()` runs, the clock has already advanced. A module operates on the current tick's date, not the previous one.

### Ages are already synced

The session updates `_age_months` before modules run, so `facility.age_years`, `facility.age_months`, `system.age_years`, and `system.age_months` reflect the simulated date for the current tick.

For degradation work, that means a module can combine `system.age_months` with `session.settings.get_system_type(system.system_type_key)` to read `SystemType.life_expectancy_months` without reaching back into workbook-loading code.

### Parent condition indices are derived

Systems are the leaf-level entities with directly stored condition index values.

After modules run:

- facility CI is recomputed from child systems
- installation CI is recomputed from child facilities

This means a module should usually mutate system CI, not facility or installation CI. If you directly write a parent CI value, the session will overwrite it during aggregate recalculation unless you also change the underlying children.

### History captures post-module state

The recorded history reflects the state after modules run and after parent aggregates are recalculated.

### Pause logic runs after history capture

Pause policies evaluate the same post-module state that was just recorded in history. If something critical happens on a tick, the tick is still captured before the session pauses.

## What the Runtime Actually Tracks

### Condition index

Today, runtime history is CI-focused.

`ConditionHistoryStore` records snapshots for:

- installation CI
- facility CI
- system CI

It does not currently snapshot:

- work-order history
- resiliency-grade changes
- arbitrary module-specific state

If a future module needs historical tracking for something besides CI, that will require an additional history structure or an expanded snapshot model.

### Runtime status

`EntityRuntimeState` is the runtime summary object used by the dashboard and pause logic.

The session computes states with:

- `get_system_state(system_id)`
- `get_facility_state(facility_id)`
- `get_installation_state()`
- `iter_runtime_states()`

These methods determine whether an entity is:

- `degraded`
- `inoperable`
- `mission_blocked`

Current rules:

- degraded: `condition_index <= condition_index_degraded_threshold`
- inoperable: `condition_index <= 0`
- mission blocked for a system: inoperable and has open mission-impacting work orders
- facilities and installations inherit degraded, inoperable, and mission-blocked status from children

If you need runtime status logic in a module, prefer using these helpers instead of reimplementing the rules.

### Work orders

The session stores work orders in two ways:

- a flat list at `session.work_orders`
- a grouped lookup at `session.work_orders_by_system`

Each `System` also gets its `work_orders` list populated from that grouped lookup when indexes are rebuilt.

Open work-order statuses are:

- `Submitted`
- `Approved`
- `In Progress`

Completed work orders are not considered open.

## Authoring modules

**Leaf mutations:** change **system** `condition_index` and **work order** lifecycle fields yourself; **`session.step()`** recomputes facility/installation CI, history, and pause checks. Parent CI you set by hand is overwritten unless children change (see **Parent condition indices are derived** above).

**Structural edits:** adding/removing/relinking work orders, systems, facilities, or parent/child IDs requires consistent FK fields plus **`session.rebuild_indexes()`** so maps and **`system.work_orders`** stay aligned. Scalar-only edits do not.

**Design:** one concern per module, no UI, no direct history writes—orchestration stays in **`session.step()`**. Scale effects with **`session.current_date`** and **`session.clock.tick_size`** ( **`SystemDegradationModule`** converts tick size to a year fraction). Return **`ModuleEvent(..., should_pause=True)`** for an immediate stop; module events are processed before pause-policy events, so ordering affects which message becomes **`stop_reason`**. Prefer **`get_system_state` / `get_facility_state` / `get_installation_state`**, **`work_orders_by_system`**, and the entity lists over re-deriving status rules.

## Example Module Skeleton

This is the intended shape for a runtime module:

```python
from src.enums.entity_type import EntityType
from src.simulation.modules.base import Base, ModuleEvent
from src.simulation.runtime import SimulationSession


class ExampleSystemDecayModule(Base):
    def apply(self, session: SimulationSession) -> list[ModuleEvent]:
        events: list[ModuleEvent] = []

        for system in session.systems:
            if system.condition_index is None:
                continue

            system.condition_index = max(0.0, round(system.condition_index - 0.1, 2))

            if system.condition_index == 0.0:
                events.append(
                    ModuleEvent(
                        code="system_became_inoperable",
                        message=f"System {system.id} became inoperable.",
                        entity_id=system.id,
                        entity_type=EntityType.SYSTEM,
                        should_pause=False,
                    )
                )

        return events
```

The key point is that the module only mutates system state. It does not recalculate facility or installation CIs, record history, or pause the session directly.

## Generation Concepts That Still Matter at Runtime

Even if you are only working on runtime modules, it helps to know what generation creates up front.

### Dependency positions

Facilities are assigned `DependencyPosition` values such as `A1` or `B23`.

Those positions:

- define dependency depth
- carry shared group IDs
- are validated during generation so deeper facilities have valid upstream support

The shell uses those positions to build the dependency tree shown to the user.

Important nuance: the display parent shown in the shell is computed for visualization. It is not stored as a permanent parent pointer on the model.

### Resiliency grades

Facility `resiliency_grade` values are assigned during generation based on dependency relationships and configured thresholds.

At the moment, resiliency grade is useful context, but the core runtime degraded/inoperable/mission-blocked logic is driven by condition index and work-order state, not by resiliency grade.

### Lifecycle-aware work-order counts

Generated work-order volume is influenced by system age and life expectancy through the configured distributions. That gives the runtime a more realistic initial state even before any runtime modules start changing data.

## Current limitations

- **`SystemDegradationModule`** is passive and monotonic (no recovery, shocks, or work-order-driven CI yet); see **Built-in system degradation module** above.
- **History** snapshots CI only; work-order state is live-only.
- **One installation** per session; initial snapshot at tick **`0`**; **`CriticalStatePausePolicy`** ignores newly critical entities on that tick so load-generated crises do not auto-pause before playback.
- **Generation vs runtime:** work-order timestamps may use wall-clock **`datetime.now()`** at generation time, while ages follow the simulated clock during **`step()`**.
- **Stale indexes** if you change hierarchy membership without **`rebuild_indexes()`**.

## Where To Read Code First

If you are new to this part of the codebase, read these files in this order:

1. `src/simulation/runtime/session.py`
2. `src/simulation/modules/base.py`
3. `src/simulation/modules/system_degradation.py`
4. `src/simulation/runtime/clock.py`
5. `src/simulation/runtime/history.py`
6. `src/cli/simulation_shell.py`
7. `tests/integration/test_simulation_runtime_integration.py`
8. `tests/unit/test_simulation_shell_panels.py` (panel strings and mission-alert thresholds without a Live terminal loop)
9. `tests/unit/test_cli_interrupts.py` (menu and wizard behavior on Ctrl-C / EOF)

The runtime integration test is especially useful because it includes both the minimal `ForceInoperableModule` example and seeded coverage for `SystemDegradationModule`, showing how a module can mutate a system and let the rest of the runtime react automatically.

## Sensible next features

Stay in **modules** / **pause policies** / **session**, not the shell:

1. Tune or externalize **`SystemDegradationModule`**
2. Work-order progression rules
3. Repair effects on CI
4. Richer mission-impact logic
