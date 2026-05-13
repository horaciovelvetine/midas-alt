"""Unit tests for the simulation module registry and MidasSettings integration."""

from __future__ import annotations

import dataclasses

import pytest

from src.config import MidasSettings
from src.config.setting_state import BooleanMappingSettingState
from src.simulation.modules.base import SimulationModuleBase
from src.simulation.modules.registry import (
    ModuleSpec,
    _snake_case_key,
    discover_module_specs,
    get_module_specs,
    reset_cache,
)
from src.simulation.modules.system_degradation import SystemDegradationModule
from src.simulation.modules.work_order_progression import WorkOrderProgressionModule

# ! ==========================================================================================>
# ! REGISTRY DISCOVERY
# ! ==========================================================================================>


def test_snake_case_key_strips_module_suffix_and_lowercases() -> None:
    """The class-name-to-key helper drops the ``Module`` suffix and snake-cases the rest."""
    assert _snake_case_key("SystemDegradationModule") == "system_degradation"
    assert _snake_case_key("WorkOrderProgressionModule") == "work_order_progression"
    assert _snake_case_key("FooBar") == "foo_bar"


def test_discover_module_specs_finds_both_built_in_modules() -> None:
    """Discovery returns specs for the two built-in simulation modules."""
    specs = discover_module_specs()
    keys = [spec.key for spec in specs]

    assert "system_degradation" in keys
    assert "work_order_progression" in keys

    system_spec = next(s for s in specs if s.key == "system_degradation")
    wo_spec = next(s for s in specs if s.key == "work_order_progression")

    assert system_spec.factory is SystemDegradationModule
    assert wo_spec.factory is WorkOrderProgressionModule
    assert system_spec.default_enabled is True
    assert wo_spec.default_enabled is False
    assert system_spec.label == "System Degradation"
    assert wo_spec.label == "Work Order Progression"


def test_get_module_specs_returns_cached_value() -> None:
    """Repeated ``get_module_specs`` calls return the same cached list instance."""
    reset_cache()
    first = get_module_specs()
    second = get_module_specs()
    assert first is second


# ! ==========================================================================================>
# ! MIDAS SETTINGS INTEGRATION
# ! ==========================================================================================>


def test_enabled_simulation_modules_setting_is_synced_on_initialize() -> None:
    """``enabled_simulation_modules`` exposes the discovered registry on init."""
    settings = MidasSettings()
    state = settings.get_state("enabled_simulation_modules")
    assert isinstance(state, BooleanMappingSettingState)
    assert state.keys is not None
    assert "system_degradation" in state.value
    assert "work_order_progression" in state.value
    assert state.value["system_degradation"] is True
    assert state.value["work_order_progression"] is False
    assert state.labels["system_degradation"] == "System Degradation"


def test_iter_enabled_simulation_module_keys_reflects_settings() -> None:
    """The enabled-keys iterator returns only modules toggled on in settings."""
    settings = MidasSettings()
    assert settings.iter_enabled_simulation_module_keys() == ["system_degradation"]


def test_build_enabled_simulation_modules_instantiates_only_enabled() -> None:
    """Only modules toggled on in settings are instantiated by ``build_enabled_simulation_modules``."""
    settings = MidasSettings()
    instances = settings.build_enabled_simulation_modules()
    assert len(instances) == 1
    assert isinstance(instances[0], SystemDegradationModule)
    assert isinstance(instances[0], SimulationModuleBase)


def test_build_enabled_simulation_modules_after_enabling_work_order() -> None:
    """Toggling an additional module in settings includes it on the next build."""
    settings = MidasSettings()
    current = dict(settings.get_value("enabled_simulation_modules"))
    current["work_order_progression"] = True
    settings.set_value("enabled_simulation_modules", current)

    instances = settings.build_enabled_simulation_modules()
    class_names = {type(instance).__name__ for instance in instances}
    assert class_names == {"SystemDegradationModule", "WorkOrderProgressionModule"}


def test_set_value_rejects_unknown_module_key() -> None:
    """Writing a mapping with an unknown module key raises ``ValueError``."""
    settings = MidasSettings()
    current = dict(settings.get_value("enabled_simulation_modules"))
    current["fictional_module"] = True
    with pytest.raises(ValueError, match="unexpected"):
        settings.set_value("enabled_simulation_modules", current)


def test_sync_simulation_module_registry_preserves_user_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-syncing the registry preserves user-toggled module enable/disable state."""
    settings = MidasSettings()
    current = dict(settings.get_value("enabled_simulation_modules"))
    current["work_order_progression"] = True
    settings.set_value("enabled_simulation_modules", current)

    settings.sync_simulation_module_registry()
    refreshed = settings.get_value("enabled_simulation_modules")
    assert refreshed["work_order_progression"] is True
    assert refreshed["system_degradation"] is True


def test_sync_simulation_module_registry_prunes_unknown_keys() -> None:
    """Re-syncing the registry drops module keys not present in the discovered specs."""
    settings = MidasSettings()
    state = settings.get_state("enabled_simulation_modules")
    assert isinstance(state, BooleanMappingSettingState)
    state.value = {**state.value, "phantom_module": True}
    state.keys = tuple(state.value.keys())

    settings.sync_simulation_module_registry()
    refreshed = settings.get_value("enabled_simulation_modules")
    assert "phantom_module" not in refreshed


def test_module_spec_is_frozen_dataclass() -> None:
    """``ModuleSpec`` is frozen and rejects attribute mutation after construction."""
    spec = ModuleSpec(
        key="x",
        label="X",
        factory=SystemDegradationModule,
        default_enabled=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.key = "y"  # type: ignore[misc]
