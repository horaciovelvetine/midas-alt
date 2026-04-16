"""
Simulation runner for MIDAS condition index degradation.

Orchestrates the full per-installation degradation simulation:

    Installation + Facilities
        -> LocationProfile  (from base name to weather cluster)
        -> WeatherStressProvider (per-step 0-1 stress)
        -> WorkOrderReader  (per-facility deferred/completed per step)
        -> FacilityConditionModel (CI degradation per timestep)
        -> aggregated Installation CI

Each facility gets its own FacilityConditionModel instance. The runner
drives the shared TimeStepCounter and feeds each step's inputs into
every facility model, then aggregates results back to the installation.

Usage:
    runner = SimulationRunner(
        installation=installation,
        facilities=facilities,
        weather=WeatherStressProvider(),
        work_orders=WorkOrderReader(Path("CE_Work_Orders_200.xlsx")),
        interval="monthly",
        start_date=datetime(2026, 1, 1),
    )

    results = runner.run(n_steps=24)
    # results["installation_ci_history"] -> list of monthly CI values
    # results["facility_results"]        -> dict[facility_id, {...}]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..models import Facility, Installation
from .condition_index import ConditionModelConfig, FacilityConditionModel
from .location import LocationProfile
from .timestep import TimeStepCounter
from .weather import WeatherStressProvider
from .work_orders import WorkOrderReader


@dataclass
class FacilityRunResult:
    """Simulation output for a single facility."""

    facility_id: str
    facility_number: str
    condition_history: list[float]
    state_history: list[str]
    backlog_history: list[float]
    final_ci: float
    final_state: str


@dataclass
class SimulationResult:
    """Simulation output for a full installation."""

    installation_id: str
    installation_name: str
    n_steps: int
    interval: str
    start_date: datetime
    installation_ci_history: list[float]
    facility_results: dict[str, FacilityRunResult] = field(default_factory=dict)

    @property
    def final_installation_ci(self) -> float:
        """CI of the installation at the end of the simulation."""
        return self.installation_ci_history[-1] if self.installation_ci_history else 0.0

    @property
    def degraded_facilities(self) -> list[FacilityRunResult]:
        """Facilities in Moderate, Severe, or Failed state at end of run."""
        critical = {"Moderate", "Severe", "Failed"}
        return [r for r in self.facility_results.values() if r.final_state in critical]


class SimulationRunner:
    """Drives a multi-facility condition index simulation for one installation.

    Args:
        installation:  The Installation domain object to simulate.
        facilities:    List of Facility objects belonging to this installation.
        weather:       WeatherStressProvider instance (shared, loaded once).
        work_orders:   WorkOrderReader instance, or None to run without
                       work order data (stress/aging only).
        interval:      Timestep size ("hourly", "weekly", "monthly", "quarterly").
        start_date:    Simulation start date.
        model_config:  Optional ConditionModelConfig override. Applied to all
                       facilities. Per-facility config not yet supported.
        seed:          Optional RNG seed for reproducible noise.
    """

    def __init__(
        self,
        installation: Installation,
        facilities: list[Facility],
        weather: WeatherStressProvider,
        work_orders: WorkOrderReader | None = None,
        interval: str = "monthly",
        start_date: datetime | None = None,
        model_config: ConditionModelConfig | None = None,
        seed: int | None = None,
        wo_installation_name: str | None = None,
    ) -> None:
        self.installation = installation
        self.facilities = facilities
        self.weather = weather
        self.work_orders = work_orders
        self.interval = interval
        self.start_date = start_date or datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        self.model_config = model_config

        # Name used when querying the work order reader — may differ from
        # installation.title if the work order system uses abbreviated names
        # (e.g. "Peterson SFB" vs "Peterson Space Force Base")
        self._wo_installation_name = wo_installation_name or installation.title

        # Resolve location profile from installation name
        self._location = LocationProfile.from_base_name(installation.title or installation.location)

        # Build one condition model per facility - offset seed per facility so
        # noise trajectories diverge even when a shared base seed is provided
        self._facility_models: dict[str, FacilityConditionModel] = {}
        for i, facility in enumerate(facilities):
            cfg = model_config
            if cfg is None and facility.year_constructed:
                cfg = ConditionModelConfig()

            facility_seed = (seed + i) if seed is not None else None
            self._facility_models[facility.id] = FacilityConditionModel(
                config=cfg,
                location=self._location,
                interval=interval,
                seed=facility_seed,
            )

        self._clock = TimeStepCounter(start_date=self.start_date, interval=interval)

    def run(self, n_steps: int) -> SimulationResult:
        """Run the simulation for n_steps timesteps.

        Args:
            n_steps: Number of timesteps to simulate.

        Returns:
            SimulationResult with per-facility and installation-level histories.
        """
        # Collect per-step results as we go
        installation_ci_per_step: list[float] = []

        for _ in range(n_steps):
            step_start = self._clock.current_date
            self._clock.step()
            step_end = self._clock.current_date

            # Get weather stress for this base this step
            weather_stress = self.weather.get_stress(
                base_name=self.installation.location or self.installation.title,
                cluster_id=self._location.bucket.value if hasattr(self._location.bucket, "value") else None,
            )

            # Step each facility model
            step_cis: list[float] = []
            for facility in self.facilities:
                deferred, completed = self._get_work_orders(facility, step_start, step_end)

                model = self._facility_models[facility.id]
                new_ci = model.step(
                    weather_stress=weather_stress,
                    deferred_reports=deferred,
                    completed_reports=completed,
                )
                step_cis.append(new_ci)

            # TODO: weight by FacilityType.mission_criticality once mission hierarchy is implemented
            installation_ci = round(sum(step_cis) / len(step_cis), 4) if step_cis else 0.0
            installation_ci_per_step.append(installation_ci)

        # Build result objects
        facility_results: dict[str, FacilityRunResult] = {}
        for facility in self.facilities:
            model = self._facility_models[facility.id]
            facility_results[facility.id] = FacilityRunResult(
                facility_id=facility.id,
                facility_number=str(getattr(facility, "facility_type_key", "")),
                condition_history=model.condition_history,
                state_history=model.state_history,
                backlog_history=model.backlog_history,
                final_ci=model.condition,
                final_state=model.current_state,
            )

        return SimulationResult(
            installation_id=self.installation.id,
            installation_name=self.installation.title,
            n_steps=n_steps,
            interval=self.interval,
            start_date=self.start_date,
            installation_ci_history=installation_ci_per_step,
            facility_results=facility_results,
        )

    def _get_work_orders(
        self,
        facility: Facility,
        step_start: datetime,
        step_end: datetime,
    ) -> tuple[list[int], list[int]]:
        """Fetch work orders for a facility this timestep, if a reader is set."""
        if self.work_orders is None:
            return [], []

        return self.work_orders.get_for_timestep(
            installation=self._wo_installation_name,
            facility_number=str(getattr(facility, "facility_type_key", "")),
            step_start=step_start,
            step_end=step_end,
        )
