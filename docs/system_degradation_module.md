# System degradation module

Step-by-step description of [`src/simulation/modules/system_degradation.py`](../src/simulation/modules/system_degradation.py): passive condition-index (CI) degradation during runtime simulation.

For broader simulation architecture (session, `step()`, other modules), see [`simulation_system_internals.md`](simulation_system_internals.md).

## Purpose

`SystemDegradationModule` **passively lowers each system’s condition index** over simulated time. It models **wear relative to service life** using discrete **condition bands** (excellent → … → failed) and **randomized “time until the next drop”** within each band.

## Model inputs

The model is shaped by a couple of module-level constants plus four configurable settings.

### Module constants

| Piece | Role |
| --- | --- |
| `_STATE_ORDER` | Ordered bands from best to worst: excellent → good → fair → poor → critical → failed. |
| `_DEFAULT_AGE_RATIO_RATE_POINTS` | Documented baseline for the age-ratio → base annual transition rate curve. Used as a fallback when the `system_degradation_age_ratio_rate_curve` setting is missing or malformed (fewer than two valid points). The live module reads the setting; the constant is the safety net. |
| `_EPSILON` | Tiny float tolerance for “is this effectively zero?” comparisons. |

### Configurable settings

Module behavior is tuned through `MidasSettings`; `apply()` reads each setting once per tick via `session.settings.get_value(...)`.

| Setting | Type / Units | Role |
| --- | --- | --- |
| `system_degradation_age_ratio_rate_curve` | `MappingSettingState`, age-ratio (string key) → base annual rate (events/year) | Piecewise-linear curve mapping **normalized age** (current age / life expectancy) to a **base annual transition rate**. Keys are stringified age ratios (defaults: `0.00`, `0.25`, `0.50`, `0.75`, `1.00`, `1.25`, `1.50`); values are the per-year rates (defaults: 0.012, 0.02, 0.05, 0.09, 0.18, 0.32, 0.55), so older assets degrade faster on average. Per-value bounds 0.0–10.0. The module sorts the entries by age ratio, clamps queries to the smallest and largest configured keys, and falls back to `_DEFAULT_AGE_RATIO_RATE_POINTS` when fewer than two points parse cleanly. The interpolated value is the input to `_base_transition_rate` and is then multiplied by the per-band value from `system_degradation_state_rate_multipliers` to produce `_annual_transition_rate`. |
| `system_degradation_state_rate_multipliers` | `MappingSettingState`, dimensionless multiplier | Per-condition-band multipliers applied to the base age-driven hazard rate. Keys: `excellent`, `good`, `fair`, `poor`, `critical`. Defaults: 0.9, 1.0, 1.15, 1.3, 1.65. Bounds: 0.0–10.0. The `failed` band is intentionally not configurable; any band missing from the mapping (or non-positive) short-circuits `_annual_transition_rate` to `0.0`, terminating the age-driven loop cleanly for that system. |
| `random_system_degradation_chance` | `FloatSettingState`, percent per year | Independent random-degradation event probability over a 1-year tick (largest preset). Defaults to 35.0; bounds 0.0–100.0. The module scales it linearly to the active tick (`tick_chance = base_pct/100 * tick_years`) and caps the result at 1.0. |
| `random_system_degradation_ci_drop` | `FloatSettingState`, CI points | Magnitude of the CI drop applied when a random-degradation event fires. Defaults to 15.0; bounds 0.0–100.0. The drop is independent of state bands and the resulting CI is clamped at 0. |

## One tick: `apply(session)`

1. **Tick length in years**  
   `_tick_size_to_years(session.clock.tick_size)` converts days/weeks/months/years into a **fraction of a year**. If that is ≤ 0, nothing happens.

2. **Settings**  
   `degraded_threshold` comes from `session.settings.get_value("condition_index_degraded_threshold")`. It splits the low end of the CI scale into **critical vs poor** (see `_state_from_ci`).  
   `state_multipliers` comes from `session.settings.get_value("system_degradation_state_rate_multipliers")` and is the per-band hazard multiplier mapping fed into `_annual_transition_rate`.  
   `curve_points` comes from `session.settings.get_value("system_degradation_age_ratio_rate_curve")` and is normalized via `_curve_points_from_setting(...)` into a sorted tuple of `(age_ratio, base_rate)` breakpoints; this is the curve that `_base_transition_rate` interpolates. It is also the source of the upper age-ratio clamp in `_effective_age_ratio`.  
   `random_annual_chance` and `random_ci_drop` come from `random_system_degradation_chance` and `random_system_degradation_ci_drop`, then collapse into a single `random_tick_chance = clamp(0.0, 1.0, (random_annual_chance/100) * tick_years)` used by the random-event layer below.

3. **Per system**  
   For each `system` in `session.systems`:

   - Resolve `system_type` via `system.system_type_key` and `session.settings.get_system_type(...)`.
   - If **no CI** or **no type**, clear internal tracking and skip.
   - Run the **independent random-degradation roll** (see "Random degradation events" below). This may lower CI before the age-driven loop starts.
   - Map current CI to a **discrete state** with `_state_from_ci`.
   - If already **failed**, clear tracking and skip.
   - Need **age** (`age_months`) and **positive** `life_expectancy_months`; otherwise skip and clear tracking.

4. **Age ratio for this tick**  
   `_effective_age_ratio` uses the **middle of the tick** as the representative age:  
   `effective_age_months ≈ age_months - (tick_months / 2)`, then divides by `life_expectancy_months` and clamps to the largest age ratio in `curve_points` (the upper end of the configured `system_degradation_age_ratio_rate_curve`). A long tick uses an average age **slightly younger** than the tick’s end—smoother than jumping only at period end.

5. **Sync hazard tracking**  
   `_sync_tracking(system.id, current_state)` ensures:

   - If the **state band changed** (e.g. something else repaired or damaged the system), or exposure was never set, **resample** a new “remaining exposure” for the exponential waiting-time model.
   - If we’re still in the same band and already have exposure, **leave it**.

6. **Run degradation**  
   `_apply_system_degradation(...)` may emit one or more `ModuleEvent`s with code `system_condition_state_declined`.

## Random degradation events

`_maybe_apply_random_degradation(...)` runs **before** the age-driven loop, once per system per tick:

1. **Skip cheap cases:** if `random_tick_chance <= 0`, `random_ci_drop <= 0`, or the system already has CI of `None` / `0` (failed), do nothing.
2. **Roll:** draw `self._rng.random()`. If the draw is **≥** `random_tick_chance`, do nothing.
3. **Apply drop:** subtract `random_ci_drop` from `system.condition_index`, clamp at `0.0`, and round to 2 decimals. The age-driven loop then sees the post-drop CI in the same tick.
4. **Resync exposure tracker:** if the resulting band changed, either `_clear_tracking(...)` (when the new band is `failed`) or resample `_remaining_transition_exposure` so the exponential waiting-time threshold reflects the new band. If the band did not change, exposure is left alone.
5. **Emit event:** return a `ModuleEvent` with code `system_random_degradation_event`, the system / type title, the drop amount, the old and new CI, and the old → new state names.

Why **before** the age-driven loop: keeping it first means the rest of the per-system pipeline (`_state_from_ci`, age-ratio lookup, exposure consumption) runs against the same CI that history and aggregates will record at the end of the tick, with no risk of the age-driven loop firing on stale CI.

The configured chance is annualized, so smaller ticks scale down linearly: a 1-year tick uses the full configured percentage, a 1-month tick uses ~1/12, a 1-day tick uses ~1/365. Larger ticks above one year are clipped at 100% so the per-tick probability stays a valid Bernoulli parameter.

## Core loop: `_apply_system_degradation`

This implements **multiple state drops within a single tick** if the tick is long enough and random thresholds align.

**State variables:**

- `remaining_years`: how much of the tick’s time is left to “spend.”
- `annual_rate`: hazard for leaving the **current** band, from `_annual_transition_rate` = base rate × state multiplier. The base rate is interpolated by `_base_transition_rate` from the `system_degradation_age_ratio_rate_curve` setting (the active `curve_points`); the multiplier comes from the `system_degradation_state_rate_multipliers` setting.
- `remaining_exposure`: random threshold (in **exposure units** where **1 year × annual_rate** adds `annual_rate` exposure). Same idea as: exposure accumulates at rate `annual_rate`; when cumulative exposure reaches the sampled threshold, a transition fires.

**Loop while** there is meaningful time left and state is not failed:

1. If `annual_rate <= 0`, stop (e.g. failed).

2. Compute **available_exposure** = `annual_rate * remaining_years` (max exposure you could add this iteration).

3. Compare to **remaining_exposure** (the sampled threshold still needed):

   - If **available_exposure < remaining_exposure**: not enough “budget” this iteration to trigger a transition. Subtract exposure from the threshold and **exit** (transition happens in a later tick).
   - Else: a transition **occurs within** this tick. **Time used** = `remaining_exposure / annual_rate`. Subtract that from `remaining_years`.

4. **Apply transition:**

   - `previous_state` = current band.
   - `next_state` = `_next_state_name` → one step worse on `_STATE_ORDER` (cannot skip bands).
   - Set `system.condition_index` with `_next_ci_value`: moves CI **down** toward a **representative value** for the new band (capped by `min(current_ci, target)` so CI never jumps up).
   - Re-read `state` from CI via `_state_from_ci` (keeps logic consistent with thresholds).

5. **Tracking after transition:**

   - If new state is **failed**: `_clear_tracking` (no more exposure bookkeeping).
   - Else: **resample** `remaining_transition_exposure` for the next drop.

6. Append a `ModuleEvent` describing the decline (system id, type title, old/new state, CI).

Return the list of events.

## Helpers (short)

| Function | What it does |
| --- | --- |
| `_state_from_ci` | Maps numeric CI to a band using fixed breakpoints (50, 70, 85) and `degraded_threshold` for critical vs poor; CI ≤ 0 → failed. |
| `_tick_size_to_years` | Calendar conversion to years (365.25-day year; 12 months/year). |
| `_effective_age_ratio` | Average age over the tick window for the hazard curve; clamped to the largest age ratio in the active `curve_points`. |
| `_base_transition_rate` | Linear interpolation on the supplied `curve_points` (built from the `system_degradation_age_ratio_rate_curve` setting; defaults to `_DEFAULT_AGE_RATIO_RATE_POINTS`). |
| `_annual_transition_rate` | Base × `state_multipliers[current_state]` from the `system_degradation_state_rate_multipliers` setting; returns `0.0` when the band is absent or non-positive (e.g. `failed`). |
| `_curve_points_from_setting` | Converts the `system_degradation_age_ratio_rate_curve` mapping into a sorted tuple of `(age_ratio, base_rate)` pairs. Skips entries with non-numeric keys, clamps rates at `0.0`, and falls back to `_DEFAULT_AGE_RATIO_RATE_POINTS` when fewer than two valid breakpoints survive. |
| `_next_state_name` | Next worse label in `_STATE_ORDER`. |
| `_next_ci_value` | Target CI per band (e.g. excellent 92.5, …, failed 0); **rounds** to 2 decimals. |
| `_sample_transition_exposure` | `-log(U)` for U uniform in (0,1], i.e. **Exponential(1)** threshold—memoryless waiting time in exposure space. |
| `_maybe_apply_random_degradation` | Independent per-tick Bernoulli roll using `random_system_degradation_chance` (annualized) and `random_system_degradation_ci_drop`; emits `system_random_degradation_event` when triggered and resyncs the exposure tracker if the band changes. |

## Mental model (one sentence)

**Per system, every tick first rolls an independent annualized "shock" chance that may chop a configurable chunk of CI in one go, then the age-driven layer—per system and band, with its own "patience" threshold in exposure units—keeps consuming time at age-driven base hazard × band multiplier and steps the CI one band worse whenever exposure crosses the threshold, possibly several times in one long tick.**
