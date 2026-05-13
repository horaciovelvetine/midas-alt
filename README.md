# MIDAS

MIDAS (**M**ission **I**nfrastructure **D**egradation **A**nalysis **S**imulation) generates synthetic military-style installation data: facilities, systems, condition indices, dependency hierarchies, UFC-style resiliency grades, and maintenance work orders. Configuration comes from an Excel workbook; the app is operated through an interactive **Rich** terminal menu and an optional live time-stepped simulation shell.

**Entity model:** `Installation -> Facility -> System -> WorkOrder`.

## Quick Start

```bash
uv venv
source .venv/bin/activate
uv sync --group dev   # optional; installs pytest, ruff, docformatter, etc.
uv run python main.py
```

On startup, MIDAS loads `docs/midas_config_data.xlsx` for reference data (facilities, systems, installations, work-order text) and, if present, applies persisted runtime settings from `output/midas_settings.json`. It then prints load status and **waits for Enter** before opening the main menu.

**Main menu** (first item is the primary entry path):

1. **Run Time Simulation** — load or generate one installation, then the live shell (**paused** at start). Steps and keys are under **Primary workflow** below.
2. **Simulation** — explore hierarchies and work orders in the terminal, tabular facility/system + work-order detail view, quick generate + stats (including work-order breakdown), full generate-and-export wizard.
3. **Configuration** — browse loaded reference data (facility types, system types, installation locations, and work-order templates) in one place, view or edit current setting values, reload from disk, and save current settings to JSON.

**Menu navigation:** enter a number to select an item. **`b`** goes back to the parent menu from Simulation or Configuration. **`q`** or **`quit`**, or **Ctrl-C**, quits MIDAS from any menu. Wizards and data browsers use the same **`b`** / **`q`** (and Ctrl-C where noted) to step back or leave the flow.

### Requirements

- Python >= 3.11
- Runtime (see `pyproject.toml`): `numpy>=2.4.0`, `pandas[excel]>=2.3.3`, `rich>=13.7.0`, `scikit-learn>=1.6.0`
- Dev: `pytest`, `pytest-cov`, `ruff`, `docformatter`

## Primary workflow: runtime simulation

1. Launch MIDAS and choose **Run Time Simulation**.
2. Either:
   - **Load** a normalized CSV **directory** or **XLSX** file produced by this project’s IO/export pipeline (`src/io/`), or
   - **Generate** a single installation in memory.
3. If the loaded dataset has multiple installations, pick one (`installation_id` is required for multi-installation results).
4. Use the live dashboard (keyboard-driven).

**Layout:** top row = installation summary, simulation clock/state, work-order counts; optional **Mission alerts** strip when rules fire (**`a`** opens detail); below = dependency graph + inspect (**`f`** or focusing a facility reveals systems); **`h`** toggles the key reference panel. UI specifics and alert rules live in [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md#shell-and-dashboard).

**Keys** (see in-app help with `h`):

| Keys | Action |
| --- | --- |
| `space` / `p` | Pause or resume |
| `n` | Single-step one tick (then pause) |
| `t` | Cycle tick size: day → week → month → year |
| `+` or `]` | Faster playback (shorter delay between ticks) |
| `-` or `[` | Slower playback |
| `i` | Inspect: facility list first (number, **s** system, **c** clear, **b** back to sim); **b** also exits system picker |
| `a` | Mission impact view (red strip visible): rules + snapshot + table; pick # for drill-down (metrics, why, sample WOs), **0** to close |
| `f` | Show or hide systems under facilities in the tree |
| `h` | Toggle controls help panel |
| `q` / Ctrl-C | Quit back to the menu |

**Each tick (summary):** clock advances, ages sync, enabled **simulation modules** run, parent CIs roll up from systems, **history** records snapshots, **pause policies** evaluate. Exact order and rules live in [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md#the-tick-lifecycle).

## Architecture

Each subsection lists the files that actually live in the directory today. Deeper, behavior-level detail is intentionally left to the linked companion docs.

### `src/functions`

Small, dependency-light helpers shared across the app.

- `generate_id.py`: UUID-style IDs for model dataclasses.
- `create_distribution_from_spec.py`: declarative distribution factory used by `MidasSettings` and workbook loaders.

### `src/config`

Owns runtime settings, reference-data lookup, logging bootstrap, and config display. Workbook IO lives under `src/io`; domain and distribution types live under `src/models`.

- `midas_settings.py`: `MidasSettings` metaclass-singleton with typed `SettingState`s and JSON save/load.
- `midas_config_data.py`: `MidasConfigData` singleton holding facility/system types, installation locations, and the work-order text cache plus distribution-driven samplers.
- `setting_state.py`: `SettingState` base + `FloatSettingState`, `IntegerSettingState`, `RangeSettingState`, `StringSettingState`, `MappingSettingState`, `BooleanMappingSettingState`, `DistributionSettingState`.
- `app_state.py`: `ApplicationState` facade over the two singletons; `LoadResult`; `get_app_state` / `set_app_state` / `reset_app_state`.
- `configure_logging.py`: root logger setup (`LOG_LEVEL` env, quieter pandas/openpyxl loggers).
- `display.py`: Rich tables/panels for config summaries.
- `_singleton.py`: `SingletonMeta` metaclass shared by both singletons.

### `src/cli`

Rich-based interactive entry points and the live simulation shell.

- `cli.py`: welcome banner, app-state initialization, main menu loop.
- `simulation_shell.py` / `simulation_shell_panels.py`: live-shell `Live` loop + dashboard panels and prompts.
- `menu/`: `MenuBuilder`, `MenuConfig`, `MenuHandler`, `MenuItem`, `menu_factory` (main / simulation / configuration menus).
- `handlers/config_handlers.py`: reference-data browser, settings entry, save/reload.
- `handlers/simulate_handlers.py`: runtime sim entry (load/generate), hierarchy browser, quick generate, export wizard, facility+system table view.
- `handlers/settings_editor.py`: type-aware editors for every `SettingState` (scalars, ranges, mappings, distributions, the module toggle map).
- `handlers/settings_persistence.py`: prompts for saving dirty `MidasSettings` state on exit / on returning from edits.
- `utils/`: `DisplayHelper`, `InputHelper`, `NavigationHelper`.

### `src/models`

Plain-dataclass domain and reference-data models plus the distribution library. `src/models/__init__.py` re-exports the common types so callers can usually import from `src.models`.

- `domain/`: `Installation`, `Facility`, `System`, `WorkOrder`, `DependencyPosition`, `FacilityType`, `SystemType`, `InstallationLocation`, `WorkOrderText`, `DataStore`.
- `distributions/`: `DistributionBase`, `DistributionContext`, `EventRateDistribution`, `WeightedProbabilityDistribution`, `WeightedProbabilitySegment`, `NormalCurveDistribution`, `BathtubCurveDistribution`, `PiecewiseCurveDistribution`.

### `src/enums`

- `entity_type.py`: `EntityType` enum used by runtime events and panels.
- `ufc_grade.py`: UFC resiliency grade enum.
- `work_order.py`: `WO_Status`, `WO_Priority`, `WO_TradeSkill`.
- `infrastructure_condition_state.py`: `InfrastructureConditionState` band enum (excellent → failed) used by `SystemDegradationModule` and display helpers.

### `src/io`

Workbook loading, dataset import/export, file formatting, and the export enum surface.

- `loaders/midas_config_data_loader.py`: `MidasConfigDataLoader` — reads `docs/midas_config_data.xlsx` into the `MidasConfigData` singleton.
- `loaders/config_data/`: per-sheet helpers used by the loader — `load_facility_types_config_data.py`, `load_system_types_config_data.py`, `load_installation_locations_config_data.py`, `load_work_order_text_config_data.py`.
- `loaders/simulation_data_loader.py`: `SimulationDataLoader` — normalized CSV directory or XLSX → `DataStore`.
- `models/data_exporter.py`: `DataExporter` for generated/existing datasets.
- `models/export_config.py`: `ExportConfig` for output format, layout, and paths.
- `models/data_transformer.py`: `DataTransformer` for normalized/denormalized export tables.
- `file_formatting/`: `BaseFormatter`, `CSVFormatter`, `ExcelFormatter`.
- `enums/`: `OutputFileType`, `OutputLayoutSchema`.

### `src/simulation`

Generation pipeline, runtime modules, and the per-tick session.

- `data_generation/`: `DataGenerator` facade plus `DataGeneratorBase`, `InstallGenerator`, `FacilityGenerator`, `SystemGenerator`, `WorkOrderGenerator`.
- `modules/base.py`: `SimulationModuleBase.apply(session) -> list[ModuleEvent]`; `ModuleEvent` can set `should_pause`.
- `modules/registry.py`: auto-discovers concrete `SimulationModuleBase` subclasses and exposes them as `ModuleSpec` records consumed by the `enabled_simulation_modules` setting.
- `modules/system_degradation.py`: default-enabled passive degradation (age/band-driven transitions plus an independent per-tick random CI drop) — see [`docs/system_degradation_module.md`](docs/system_degradation_module.md).
- `modules/work_order_progression.py`: default-disabled lifecycle progression that advances open work orders and repairs systems on completion — see [`docs/work_order_progression_module.md`](docs/work_order_progression_module.md).
- `runtime/`: `SimulationClock` / `TickSize` / `TickUnit`, `ConditionHistoryStore`, `ConditionHistoryExportAdapter`, `SimulationSession`, `EntityRuntimeState`, `CriticalStatePausePolicy`.

Public re-exports: `src/io/__init__.py` exposes workbook/data IO helpers, `src/simulation/__init__.py` exposes generation/runtime helpers. Build a runtime session with `SimulationSession.from_data_store(...)` (input is a `DataStore`; `from_generation_result` is a deprecated alias).

## Generation flow

```text
InstallGenerator
  -> FacilityGenerator
    -> SystemGenerator
      -> WorkOrderGenerator
        -> DataStore
```

Notable rules: installation and facility CI are **aggregates** of children; dependency positions are **validated** so non-root facilities have a supporting upstream sharer of a group id; resiliency grades combine **random leaf grades** with **threshold-based roll-up** from dependents; work orders sample status, priority, trade, organization, and text from config/cache.

## Runtime simulation flow

```text
DataGenerator or SimulationDataLoader
  -> DataStore
  -> SimulationSession.from_data_store(...)   # one installation, deep-copied slice
  -> SimulationShell (step loop: modules, CI rollup, history, pause policies)
```

See [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md#the-tick-lifecycle) for the exact **`step()`** order and initialization (tick `0` snapshot, first pause-policy pass).

## Configuration sources

Reference data is loaded from `docs/midas_config_data.xlsx` (override via `ApplicationState.initialize(config_path=...)`). Sheets used by the loader (when present): **Facilities**, **Systems**, **Installations** (legacy name: **Installation Locations**), **Work Order Text**. Missing data falls back to empty caches and a warning in the load summary.

Runtime settings (degradation thresholds, generation ranges, distributions, output sheet names and CSV table naming, the `enabled_simulation_modules` toggle map, etc.) live on the `MidasSettings` singleton as typed `SettingState`s. Persisted state is read from `output/midas_settings.json` on startup (override via `ApplicationState.initialize(state_path=...)`). Missing files fall back to documented defaults in `src/config/midas_settings.py`.

The Configuration menu's settings editor exposes scalar, range, mapping, distribution, and module-toggle editors; pick which simulation modules run via the `enabled_simulation_modules` boolean-mapping editor (with quick `a` enable-all / `n` disable-all shortcuts). Use the **Configuration** menu's _Save Current Settings to JSON_ item, or call `MidasSettings().save_state()` from code, to persist the current values for the next startup.

## Export

- **Formats:** `csv`, `xlsx`
- **Layouts:** `normalized` (per-entity tables/sheets), `denormalized` (one row per work order)
- **Options:** optional **metadata JSON** next to CSV exports, or a metadata sheet in Excel exports.

Condition-index time series are produced by runtime simulations through `ConditionHistoryStore` and `SimulationSession.export_history_tables()`, not by generated dataset exports.

Exports are written under `{output_directory}/{file_name}/` (see `ExportConfig`).

## Example usage

```python
from src.config import ApplicationState
from src.io import DataExporter
from src.simulation import DataGenerator, SimulationSession

ApplicationState.initialize()

generator = DataGenerator(seed=42)
result = generator.generate_installation()
print(len(result.installations), len(result.facilities), len(result.systems), len(result.work_orders))

session = SimulationSession.from_data_store(result)
session.step()
history_tables = session.export_history_tables()
print(history_tables["facility_time_series"].head())

exporter = DataExporter(
    file_name="sample_data",
    output_format="xlsx",  # or "csv"
    output_directory="./output",
    layout="normalized",
    generate_metadata=True,
)
path = exporter.generate_and_export(method="default")
print(path)
```

Load a prior export (directory created by the wizard, named after `file_name`):

```python
from pathlib import Path

from src.config import ApplicationState
from src.io import SimulationDataLoader
from src.simulation import SimulationSession

ApplicationState.initialize()

result = SimulationDataLoader().load(Path("./output/sample_data"))

session = SimulationSession.from_data_store(
    result,
    installation_id=result.installations[0].id,
)
print(session.current_date, session.installation.condition_index)
```

`DataExporter.generate_and_export` also supports `method="installations"` and `method="facilities"` with a required `target_count`.

## Extending runtime simulation

Drop a new `SimulationModuleBase` subclass into `src/simulation/modules/`; the registry will discover it on next startup and surface it in the `enabled_simulation_modules` toggle map. The session handles aggregate CI rollup, history, and pause evaluation — your `apply()` should mutate systems and work orders only. Module contract, pause behavior, and gotchas: [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md). Worked examples: [`docs/system_degradation_module.md`](docs/system_degradation_module.md), [`docs/work_order_progression_module.md`](docs/work_order_progression_module.md).

## Tests

- `tests/conftest.py`: shared fixtures
- `tests/unit/test_cli_interrupts.py`: menu/wizard interrupt handling, startup continue prompt
- `tests/unit/test_simulation_shell_panels.py`: dashboard panel text and mission-alert rules (no Live loop)
- `tests/integration/test_config_loading_integration.py`: Excel config load
- `tests/integration/test_generation_and_export_integration.py`: generation + export
- `tests/integration/test_simulation_loader_integration.py`: CSV/XLSX load
- `tests/integration/test_simulation_runtime_integration.py`: session, history, pause policy, `SystemDegradationModule`
- `tests/integration/test_simulation_cli_integration.py`: CLI/menu/shell behaviors

## Development

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

Focused simulation tests:

```bash
uv run pytest tests/unit/test_simulation_shell_panels.py tests/unit/test_cli_interrupts.py
uv run pytest tests/integration/test_simulation_loader_integration.py
uv run pytest tests/integration/test_simulation_runtime_integration.py
uv run pytest tests/integration/test_simulation_cli_integration.py
```

## Further reading

- [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md) — runtime tick order, session ownership, module-authoring contract, shell behavior, and gotchas.
- [`docs/system_degradation_module.md`](docs/system_degradation_module.md) — full reference for the default-enabled `SystemDegradationModule` (age-band hazard model + random per-tick CI drop layer).
- [`docs/work_order_progression_module.md`](docs/work_order_progression_module.md) — reference for the optional `WorkOrderProgressionModule` (work-order lifecycle progression + system repair on completion).
- [`docs/simulation_planning_further_work.md`](docs/simulation_planning_further_work.md) — modules and simulation features that were scoped but not yet implemented.
