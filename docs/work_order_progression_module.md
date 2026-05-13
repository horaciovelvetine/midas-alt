# Work order progression module

Step-by-step description of [`src/simulation/modules/work_order_progression.py`](../src/simulation/modules/work_order_progression.py): runtime module that advances open work orders through their lifecycle and repairs the underlying system on completion.

For broader simulation architecture (session, `step()`, registry, other modules), see [`simulation_system_internals.md`](simulation_system_internals.md). The companion module reference is [`system_degradation_module.md`](system_degradation_module.md).

## Purpose

`WorkOrderProgressionModule` walks **every non-completed work order** forward one lifecycle step per tick using a per-priority schedule, and **bumps the parent system's condition index** when a work order finishes. It is intentionally the **counterpart** to `SystemDegradationModule`: degradation lowers CI passively, progression raises CI as repairs land.

The module is **default-disabled** in the registry. Enable it by toggling `work_order_progression` in the `enabled_simulation_modules` setting (Configuration menu → settings editor → boolean-mapping editor for the module toggle map).

## Model inputs

The module owns a small amount of internal state and reads two fields off each work order. There are **no `MidasSettings` knobs** for it yet; the priority schedule and repair amounts are hard-coded.

### Internal state

| Piece | Role |
| --- | --- |
| `self._rng` | `random.Random` instance seeded by the optional `seed` ctor argument. Reserved for future stochastic behavior; the current logic is fully deterministic. |
| `self._work_order_ages` | `dict[str, int]` of `{work_order_id: ticks_since_first_seen}`. Incremented every tick a work order is non-completed; popped when the work order completes. Not persisted across sessions — restarting the simulation resets the ages. |

### Per-work-order inputs

| Field | Role |
| --- | --- |
| `wo.status` | One of `Submitted`, `Approved`, `In Progress`, `Completed`. Completed orders are skipped immediately. |
| `wo.priority` | One of `Emergency`, `Urgent`, `Routine`, `Maintenance`. Selects the per-priority age thresholds in `_advance_work_order_status`. |
| `wo.system_id` | Foreign key used by `_find_system_for_work_order` to locate the system to repair on completion. Work orders without a system FK never trigger a repair. |
| `wo.work_category` | Used by `_calculate_repair_amount` to single out `"Preventive Maintenance"` for a larger repair bonus. |

## One tick: `apply(session)`

For every work order in `session.work_orders`:

1. **Skip completed.** If `wo.status == WO_Status.COMPLETED`, move on.
2. **Bump age.** `self._work_order_ages[wo.id] += 1` (initialized to 0 if unseen). The first tick a work order is processed it ends with age `1`.
3. **Compute the next status** with `_advance_work_order_status(wo, session)` (see below).
4. **If the status changed**, write it back onto the work order and emit a non-pausing `ModuleEvent` with code `work_order_status_changed`.
5. **If the new status is `Completed`**, call `_repair_system(wo, session)`:
   - Look up the system via `wo.system_id` against `session.systems`.
   - Apply `_calculate_repair_amount(wo)` to `system.condition_index`, clamping at `100.0` and rounding to two decimals.
   - Emit a non-pausing `ModuleEvent` with code `system_repaired` describing the CI delta.
   - Pop the entry from `self._work_order_ages` so memory does not grow unboundedly.

Both events are **non-pausing**; the module never directly pauses the session. If a repair pushes a previously inoperable system back above the degraded threshold, `CriticalStatePausePolicy` clears its prior critical-entity tracking on the next pause-policy pass without firing a new pause.

## Status progression schedule

`_advance_work_order_status(wo, session)` applies a fixed per-priority schedule keyed off the tracked age (in ticks). At most one transition happens per tick; if no threshold is crossed the current status is returned unchanged.

| Priority | Submitted → Approved | Approved → In Progress | In Progress → Completed |
| --- | --- | --- | --- |
| Emergency | age ≥ 1 | age ≥ 2 | age ≥ 3 |
| Urgent | age ≥ 2 | age ≥ 4 | age ≥ 6 |
| Routine | age ≥ 5 | age ≥ 10 | age ≥ 15 |
| Maintenance (default) | age ≥ 10 | age ≥ 20 | age ≥ 30 |

The thresholds are interpreted in **ticks**, not calendar days, so changing the active tick size from the shell rescales the wall-clock duration of every transition. (A 30-day Maintenance lifecycle is 30 days at a daily tick, but ~30 months at a monthly tick.)

## Repair amount on completion

`_calculate_repair_amount(wo)` returns a flat CI delta based on priority, with one work-category override:

| Match | CI delta |
| --- | --- |
| `wo.priority == Emergency` | `+25.0` |
| `wo.priority == Urgent` | `+20.0` |
| `wo.work_category == "Preventive Maintenance"` (and not Emergency/Urgent) | `+30.0` |
| Anything else (e.g. Routine corrective work) | `+15.0` |

`_repair_system` clamps the new CI at `100.0` and rounds to two decimals. Systems with `condition_index is None` are left alone and no repair event is emitted.

## Events emitted

| Code | Trigger | Pauses? |
| --- | --- | --- |
| `work_order_status_changed` | Status transitioned this tick (any of the four lifecycle steps). | No |
| `system_repaired` | A work order completed this tick and the parent system's CI moved up. | No |

Both events carry `entity_type=EntityType.SYSTEM`; `entity_id` is the work order id for `work_order_status_changed` and the system id for `system_repaired`. The mission-alert and inspect panels surface these via the standard `session.last_events` plumbing.

## Helpers (short)

| Function | What it does |
| --- | --- |
| `_advance_work_order_status` | Returns the next `WO_Status` (or unchanged status) using the per-priority age table above. |
| `_repair_system` | Resolves the system for `wo.system_id`, applies the repair, clamps at 100, and returns the `system_repaired` event (or `None` if no system / `None` CI). |
| `_find_system_for_work_order` | Linear scan of `session.systems` for `wo.system_id`. Returns `None` for work orders without a system FK. |
| `_calculate_repair_amount` | Flat CI delta keyed off priority, with the `Preventive Maintenance` work-category override. |

## Limitations

- **Hard-coded thresholds and repair amounts.** No `MidasSettings` knobs yet; tuning requires editing the module. A future iteration is expected to surface both as settings.
- **Tracking is in-memory only.** `self._work_order_ages` is rebuilt from scratch each session, so reloading a dataset and resuming from disk does not preserve partial progress on existing open work orders.
- **No new work orders.** The module never opens, cancels, or reschedules work orders; it only advances ones already on the system.
- **Repairs require `wo.system_id`.** Orphan work orders (system FK missing or stale) progress through statuses normally but do not affect any CI.
- **Linear system lookup.** `_find_system_for_work_order` walks `session.systems` per completion. Fine for one-installation sessions; a session-level index would be needed before scaling to many installations.
- **No interaction with degradation.** The module does not read `system_degradation_*` settings; a system can be repaired and immediately re-degraded on the same tick because module order is degradation → progression in the default registry-discovery order.

## Mental model (one sentence)

**Per work order, every tick: skip completed, bump an in-memory age counter, take the single status step its priority allows once enough ticks have elapsed, and on completion add a flat priority/category-keyed CI bump to the parent system (clamped at 100).**
