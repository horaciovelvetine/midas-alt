"""Integration tests for simulation session ticking and history."""

from datetime import date

import pytest

from src.config import MidasConfigData
from src.config.midas_settings import MidasSettings
from src.enums.entity_type import EntityType
from src.models import DataStore, Facility, Installation, System, SystemType
from src.simulation import DataGenerator, SimulationSession, TickSize, TickUnit
from src.simulation.modules.base import SimulationModuleBase
from src.simulation.modules.system_degradation import SystemDegradationModule


def _build_single_system_session(
    *,
    condition_index: float | None,
    year_constructed: int,
    system_type: SystemType | None,
    tick_size: TickSize,
    module_seed: int = 1,
) -> SimulationSession:
    """Create a single-system runtime session with deterministic degradation."""
    config_data = MidasConfigData()
    if system_type is not None:
        config_data.replace_reference_data(system_types={system_type.key: system_type})

    # Isolate the age-driven hazard model from the independent random-degradation
    # layer so these tests assert deterministic transitions only.
    settings = MidasSettings()
    settings.set_value("random_system_degradation_chance", 0.0)
    settings.set_value("random_system_degradation_ci_drop", 0.0)

    installation = Installation(id="installation-1", title="Test Installation", facility_ids=["facility-1"])
    facility = Facility(id="facility-1", installation_id=installation.id, system_ids=["system-1"])
    system = System(
        id="system-1",
        system_type_key=system_type.key if system_type is not None else None,
        year_constructed=year_constructed,
        condition_index=condition_index,
        facility_id=facility.id,
    )
    result = DataStore(
        installations=[installation],
        facilities=[facility],
        systems=[system],
        work_orders=[],
    )
    session = SimulationSession.from_data_store(
        data=result,
        start_date=date(2026, 1, 1),
        modules=[SystemDegradationModule(seed=module_seed)],
    )
    session.clock.set_tick_size(tick_size)
    return session


class ForceInoperableModule(SimulationModuleBase):
    """Test module that forces one system into an inoperable state once."""

    def __init__(self) -> None:
        """Track whether the critical transition has already been applied."""
        self._applied = False

    def apply(self, session: SimulationSession):
        """Force the first system to become inoperable."""
        if self._applied:
            return []
        session.systems[0].condition_index = 0.0
        self._applied = True
        return []


def test_session_records_history_and_advances_dates_without_ci_changes() -> None:
    """Ticking should advance dates and append stable CI snapshots when no modules run."""
    result = DataGenerator(seed=42).generate_installation()
    initial_installation_ci = result.installations[0].condition_index
    initial_facility_cis = {facility.id: facility.condition_index for facility in result.facilities}
    initial_system_cis = {system.id: system.condition_index for system in result.systems}

    session = SimulationSession.from_data_store(
        data=result,
        start_date=date(2026, 1, 1),
    )

    initial_snapshot_count = 1 + len(session.facilities) + len(session.systems)
    assert session.current_date == date(2026, 1, 1)
    assert len(session.history.snapshots) == initial_snapshot_count

    session.resume()
    session.step()
    session.step()

    assert session.current_date == date(2026, 1, 3)
    assert session.clock.tick_index == 2
    assert len(session.history.snapshots) == initial_snapshot_count * 3
    assert session.installation.condition_index == initial_installation_ci
    assert {facility.id: facility.condition_index for facility in session.facilities} == initial_facility_cis
    assert {system.id: system.condition_index for system in session.systems} == initial_system_cis

    tables = session.export_history_tables()
    assert tables["installation_time_series"] is not None
    assert tables["facility_time_series"] is not None
    assert tables["system_time_series"] is not None
    assert len(tables["installation_time_series"]) == 3
    assert len(tables["facility_time_series"]) == len(session.facilities) * 3
    assert len(tables["system_time_series"]) == len(session.systems) * 3


def test_session_pause_policy_emits_event_for_newly_inoperable_entity() -> None:
    """Pause policies should fire when a module pushes an entity into a critical state."""
    result = DataGenerator(seed=42).generate_installation()
    result.systems[0].condition_index = 50.0

    session = SimulationSession.from_data_store(
        data=result,
        start_date=date(2026, 1, 1),
        modules=[ForceInoperableModule()],
    )

    session.resume()
    events = session.step()

    assert session.paused is True
    assert session.stop_reason is not None
    assert any(event.should_pause for event in events)
    assert any(event.entity_type == EntityType.SYSTEM for event in events if event.should_pause)


def test_system_degradation_updates_aggregates_and_history_before_pause_policies() -> None:
    """A degradation tick should flow through aggregates and history before pause handling."""
    session = _build_single_system_session(
        condition_index=10.0,
        year_constructed=1980,
        system_type=SystemType(key=1, title="Generator", life_expectancy=10, facility_keys=(1,)),
        tick_size=TickSize(amount=1, unit=TickUnit.YEAR),
        module_seed=1,
    )

    session.resume()
    events = session.step()

    assert any(event.code == "system_condition_state_declined" for event in events)
    assert session.systems[0].condition_index == 0.0
    assert session.facilities[0].condition_index == 0.0
    assert session.installation.condition_index == 0.0

    latest_snapshot = session.history.latest_snapshot(session.systems[0].id)
    assert latest_snapshot is not None
    assert latest_snapshot.tick_index == 1
    assert latest_snapshot.condition_index == 0.0
    assert any(event.should_pause for event in events)


def test_system_degradation_scales_similarly_across_tick_sizes() -> None:
    """Monthly and yearly ticks should land on the same state for the same simulated span."""
    annual_session = _build_single_system_session(
        condition_index=80.0,
        year_constructed=1985,
        system_type=SystemType(key=1, title="HVAC", life_expectancy=25, facility_keys=(1,)),
        tick_size=TickSize(amount=1, unit=TickUnit.YEAR),
        module_seed=1,
    )
    monthly_session = _build_single_system_session(
        condition_index=80.0,
        year_constructed=1985,
        system_type=SystemType(key=1, title="HVAC", life_expectancy=25, facility_keys=(1,)),
        tick_size=TickSize(amount=1, unit=TickUnit.MONTH),
        module_seed=1,
    )

    for _ in range(4):
        annual_session.step()
    for _ in range(48):
        monthly_session.step()

    assert annual_session.current_date == monthly_session.current_date
    assert annual_session.systems[0].condition_index == monthly_session.systems[0].condition_index
    assert annual_session.installation.condition_index == monthly_session.installation.condition_index


def test_shorter_life_expectancy_system_degrades_faster() -> None:
    """The same asset age should degrade faster when service life is shorter."""
    short_life_session = _build_single_system_session(
        condition_index=80.0,
        year_constructed=2001,
        system_type=SystemType(key=1, title="Cooling Plant", life_expectancy=20, facility_keys=(1,)),
        tick_size=TickSize(amount=1, unit=TickUnit.YEAR),
        module_seed=1,
    )
    short_life_session.step()
    short_life_ci = short_life_session.systems[0].condition_index
    short_life_install_ci = short_life_session.installation.condition_index

    long_life_session = _build_single_system_session(
        condition_index=80.0,
        year_constructed=2001,
        system_type=SystemType(key=1, title="Cooling Plant", life_expectancy=40, facility_keys=(1,)),
        tick_size=TickSize(amount=1, unit=TickUnit.YEAR),
        module_seed=1,
    )
    long_life_session.step()
    long_life_ci = long_life_session.systems[0].condition_index
    long_life_install_ci = long_life_session.installation.condition_index

    assert short_life_ci < long_life_ci
    assert short_life_install_ci < long_life_install_ci


@pytest.mark.parametrize(
    ("condition_index", "system_type"),
    [
        (
            None,
            SystemType(key=1, title="Power", life_expectancy=25, facility_keys=(1,)),
        ),
        (80.0, None),
    ],
)
def test_system_degradation_noops_when_required_inputs_are_missing(
    condition_index: float | None,
    system_type: SystemType | None,
) -> None:
    """Missing CI or system-type data should leave the system untouched."""
    session = _build_single_system_session(
        condition_index=condition_index,
        year_constructed=2000,
        system_type=system_type,
        tick_size=TickSize(amount=1, unit=TickUnit.YEAR),
        module_seed=1,
    )
    initial_system_ci = session.systems[0].condition_index
    initial_installation_ci = session.installation.condition_index

    events = session.step()

    assert not any(event.code == "system_condition_state_declined" for event in events)
    assert session.systems[0].condition_index == initial_system_ci
    assert session.installation.condition_index == initial_installation_ci
