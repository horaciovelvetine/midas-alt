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

On startup, MIDAS loads `src/config/midas_config_values.xlsx` (via `ApplicationState.initialize()`), builds an in-memory cache from the **Work Order Text** sheet for fast generation, prints load status, and **waits for Enter** before opening the main menu.

**Main menu** (first item is the primary entry path):

1. **Run Time Simulation** — load or generate one installation, then the live shell (**paused** at start). Steps and keys are under **Primary workflow** below.
2. **Simulation** — explore hierarchies and work orders in the terminal, tabular facility/system + work-order detail view, quick generate + stats (including work-order breakdown), full generate-and-export wizard.
3. **Configuration** — summaries for facility types, system types, installation locations, raw config values, reload from disk.

**Menu navigation:** enter a number to select an item. **`b`** goes back to the parent menu from Simulation or Configuration. **`q`** or **`quit`**, or **Ctrl-C**, quits MIDAS from any menu. Wizards and data browsers use the same **`b`** / **`q`** (and Ctrl-C where noted) to step back or leave the flow.

### Requirements

- Python >= 3.11
- Runtime (see `pyproject.toml`): `numpy>=2.4.0`, `pandas[excel]>=2.3.3`, `rich>=13.7.0`, `scikit-learn>=1.6.0`
- Dev: `pytest`, `pytest-cov`, `ruff`, `docformatter`

## Primary workflow: runtime simulation

1. Launch MIDAS and choose **Run Time Simulation**.
2. Either:
   - **Load** a normalized CSV **directory** or **XLSX** file produced by this project’s export pipeline (`src/simulation/export/`), or
   - **Generate** a single installation in memory.
3. If the loaded dataset has multiple installations, pick one (`installation_id` is required for multi-installation results).
4. Use the live dashboard (keyboard-driven).

**Layout:** top row = installation summary, simulation clock/state, work-order counts; optional **Mission alerts** strip when rules fire (**`a`** opens detail); below = dependency graph + inspect (**`f`** or focusing a facility reveals systems); **`h`** toggles the key reference panel. UI specifics and alert rules live in [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md#shell-and-dashboard).

**Keys** (see in-app help with `h`):

| Keys | Action |
|------|--------|
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

**Each tick (summary):** clock and ages advance, **modules** run (the interactive CLI includes **`SystemDegradationModule`** for passive system CI loss), parent CIs roll up from systems, **history** records snapshots, then **pause policies** run. Status labels and pauses follow config thresholds; precise order and rules are in the internals doc.

## Architecture

### `src/functions`

- `generate_id.py`: UUID-style IDs for model dataclasses.

### `src/config`

- `functions/configure_logging.py`: root logging setup (`LOG_LEVEL` env, quieter pandas/openpyxl loggers).
- `settings.py`: `MIDASSettings` and nested groups (`DegradationSettings`, `SimulationSettings`, `OutputSettings`, `SimulationDistributions`).
- `loader.py`: Excel parsing into settings and reference data; builds **`work_order_text_cache`** at load time.
- `distributions.py`: weighted **Probability** distributions, **EventRate** curves (normal, bathtub, piecewise), `DistributionContext`, Poisson-style event counts.
- `app_state.py`: `ApplicationState`, `LoadResult`, `get_app_state` / `set_app_state` singleton helpers.
- `display.py`: Rich tables/panels for config summaries.
- `reference_data.py`: `FacilityType`, `SystemType`, `InstallationLocation`, `WorkOrderText`.

### `src/cli`

- `cli.py`: welcome, config initialization, main menu loop.
- `menu/`: `MenuBuilder`, `MenuHandler`, `MenuItem`, `menu_factory` (main / simulation / configuration menus).
- `handlers/config_handlers.py`: view summaries, view config values, reload workbook.
- `handlers/simulate_handlers.py`: runtime sim entry (load/generate), hierarchy browser, quick generate, export wizard, facility+system table view.
- `simulation_shell.py`: Rich **Live** dashboard, raw terminal key polling.
- `utils/`: `DisplayHelper`, `InputHelper`, `NavigationHelper`.

### `src/models`

- `installation.py`, `facility.py`, `system.py`, `work_order.py`, `dependency_position.py` (`vertical_position` + `group_ids` for dependency graph semantics).

### `src/enums`

- `entity_type.py`, `ufc_grade.py`, `work_order.py` (`WO_Status`, `WO_Priority`, `WO_TradeSkill`).

### `src/simulation`

- `generator.py`: `DataGenerator` facade over install/facility/system/work-order generators.
- `generation_result.py`: `GenerationResult` parallel lists (`installations`, `facilities`, `systems`, `work_orders`).
- `loader.py`: `SimulationDataLoader` — CSV directory or XLSX → `GenerationResult`.
- `modules/base.py`: `Base.apply(session) -> list[ModuleEvent]`; `ModuleEvent` can set `should_pause`.
- `modules/system_degradation.py`: passive system CI degradation using discrete condition states, normalized age, and `SystemType.life_expectancy`.
- `runtime/`: `SimulationClock` / `TickSize` / `TickUnit`, `ConditionHistoryStore`, `ConditionHistoryExportAdapter`, `SimulationSession`, `EntityRuntimeState`, `CriticalStatePausePolicy`.
- `data_generation/`: `InstallGenerator` → `FacilityGenerator` → `SystemGenerator` → `WorkOrderGenerator`; shared sampling in `data_generator_base.py`.
- `export/`: `DataExporter`, `ExportConfig`, `DataTransformer`, `OutputFormat` / `OutputLayout`, `CSVFormatter`, `ExcelFormatter`. Optional **`{file_name}_metadata.json`** sidecar when `generate_metadata=True`.

Public re-exports: `src/simulation/__init__.py` (e.g. `DataGenerator`, `SimulationSession`, `ProbabilityDistribution` for API convenience; distribution **implementations** live in `src/config/distributions.py`).

## Generation flow

```text
InstallGenerator
  -> FacilityGenerator
    -> SystemGenerator
      -> WorkOrderGenerator
        -> GenerationResult
```

Notable rules: installation and facility CI are **aggregates** of children; dependency positions are **validated** so non-root facilities have a supporting upstream sharer of a group id; resiliency grades combine **random leaf grades** with **threshold-based roll-up** from dependents; work orders sample status, priority, trade, organization, and text from config/cache.

## Runtime simulation flow

```text
DataGenerator or SimulationDataLoader
  -> GenerationResult
  -> SimulationSession.from_generation_result(...)   # one installation, deep-copied slice
  -> SimulationShell (step loop: modules, CI rollup, history, pause policies)
```

See [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md#the-tick-lifecycle) for the exact **`step()`** order and initialization (tick `0` snapshot, first pause-policy pass).

## Configuration workbook

Path: `src/config/midas_config_values.xlsx` (override via `ApplicationState.initialize(config_path=...)` in code; CLI uses the default path).

Sheets used by the loader (when present): **Facilities**, **Systems**, **Installation Locations**, **Config**, **Distributions**, **Work Order Text**. Missing or invalid values fall back to defaults in `settings.py`.

Configurable areas include: facility/system counts and ages, dependency chain depth and groups, degradation thresholds, output sheet names and CSV table naming, all **Distributions** rows, and work-order text keyed by system type (plus `_fallback` behavior in code).

## Export

- **Formats:** `csv`, `xlsx`
- **Layouts:** `normalized` (per-entity tables/sheets), `denormalized` (one row per work order)
- **Options:** optional synthetic facility/system **time series** in the transformer (derived from current CI and age — not the same as runtime `ConditionHistoryStore` data); optional **metadata JSON** next to the export file.

Exports are written under `{output_directory}/{file_name}/` (see `ExportConfig`).

## Example usage

```python
from pathlib import Path

from src.config import MIDASSettings
from src.simulation import DataExporter, DataGenerator, SimulationSession

settings = MIDASSettings.from_excel(Path("src/config/midas_config_values.xlsx"))
generator = DataGenerator(settings=settings, seed=42)

result = generator.generate_installation()
print(len(result.installations), len(result.facilities), len(result.systems), len(result.work_orders))

session = SimulationSession.from_generation_result(result, settings=settings)
session.step()
history_tables = session.export_history_tables()
print(history_tables["facility_time_series"].head())

exporter = DataExporter(
    file_name="sample_data",
    output_format="xlsx",  # or "csv"
    output_directory="./output",
    layout="normalized",
    include_time_series=False,
    generate_metadata=True,
    settings=settings,
)
path = exporter.generate_and_export(method="default")
print(path)
```

Load a prior export (directory created by the wizard, named after `file_name`):

```python
from pathlib import Path

from src.config import MIDASSettings
from src.simulation import SimulationDataLoader, SimulationSession

settings = MIDASSettings.from_excel(Path("src/config/midas_config_values.xlsx"))
loader = SimulationDataLoader(settings=settings)
result = loader.load(Path("./output/sample_data"))

session = SimulationSession.from_generation_result(
    result,
    settings=settings,
    installation_id=result.installations[0].id,
)
print(session.current_date, session.installation.condition_index)
```

`DataExporter.generate_and_export` also supports `method="installations"` and `method="facilities"` with a required `target_count`.

## Extending runtime simulation

Implement **`Base`** in `src/simulation/modules/` and pass **`modules=[...]`** into **`SimulationSession`**. In **`apply()`**, change **systems** (CI, work orders, etc.); the session updates facility/installation CI, history, and pause evaluation. Use **`session.current_date`** and **`session.clock.tick_size`** to scale work per tick; call **`session.rebuild_indexes()`** if you change hierarchy membership. The interactive CLI already adds **`SystemDegradationModule`** (bands, age vs life expectancy, tick-scaled hazard—see `src/simulation/modules/system_degradation.py`). Module contract, pause behavior, and limitations: [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md).

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

- [`docs/simulation_system_internals.md`](docs/simulation_system_internals.md) — runtime tick order, session ownership, module authoring, shell behavior, and gotchas (companion to this file; avoids duplicating that detail here).
