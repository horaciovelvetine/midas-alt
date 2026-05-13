"""Unit tests for ``BooleanMappingSettingState`` and its ``MidasSettings`` usage."""

from __future__ import annotations

import pytest

from src.config import MidasSettings
from src.config.setting_state import BooleanMappingSettingState, SettingState

# ! ==========================================================================================>
# ! ROUND-TRIP SERIALIZATION
# ! ==========================================================================================>


def test_boolean_mapping_state_round_trip() -> None:
    """Boolean mapping state survives a serialize/deserialize round trip."""
    state = BooleanMappingSettingState(
        label="Test Toggles",
        description="Round-trip fixture.",
        value={"a": True, "b": False, "c": True},
        keys=("a", "b", "c"),
        labels={"a": "Alpha", "b": "Beta", "c": "Gamma"},
        key_label="Switch",
        value_label="On",
    )

    payload = state.serialize()
    restored = SettingState.deserialize(payload)

    assert isinstance(restored, BooleanMappingSettingState)
    assert restored.label == state.label
    assert restored.description == state.description
    assert restored.value == state.value
    assert restored.keys == state.keys
    assert restored.labels == state.labels
    assert restored.key_label == state.key_label
    assert restored.value_label == state.value_label


def test_boolean_mapping_preserves_declared_key_order() -> None:
    """Stored value follows the declared ``keys`` ordering, not insertion order."""
    state = BooleanMappingSettingState(
        label="Ordered",
        description="-",
        value={"second": False, "first": True, "third": True},
        keys=("first", "second", "third"),
    )
    assert list(state.value.keys()) == ["first", "second", "third"]


def test_boolean_mapping_rejects_missing_required_keys() -> None:
    """Construction fails when ``value`` is missing keys declared in ``keys``."""
    with pytest.raises(ValueError, match="missing required keys"):
        BooleanMappingSettingState(
            label="Missing",
            description="-",
            value={"a": True},
            keys=("a", "b"),
        )


def test_boolean_mapping_display_label_humanizes_unknown_keys() -> None:
    """Unmapped keys fall back to a Title-Cased version of the snake_case key."""
    state = BooleanMappingSettingState(
        label="Labels",
        description="-",
        value={"snake_case_key": True},
    )
    assert state.display_label_for("snake_case_key") == "Snake Case Key"


# ! ==========================================================================================>
# ! MIDAS SETTINGS SET_VALUE VALIDATION
# ! ==========================================================================================>


def test_set_value_accepts_valid_boolean_mapping_and_marks_dirty() -> None:
    """Writing a complete mapping updates state and flags settings as dirty."""
    settings = MidasSettings()
    state = settings.get_state("enabled_simulation_modules")
    assert isinstance(state, BooleanMappingSettingState)

    new_value = {key: not bool(value) for key, value in state.value.items()}
    settings.set_value("enabled_simulation_modules", new_value)

    stored = settings.get_value("enabled_simulation_modules")
    assert stored == new_value
    assert settings.is_dirty() is True


def test_set_value_rejects_missing_keys() -> None:
    """``set_value`` rejects partial mappings that drop required keys."""
    settings = MidasSettings()
    state = settings.get_state("enabled_simulation_modules")
    assert isinstance(state, BooleanMappingSettingState)
    assert state.keys is not None
    incomplete = {next(iter(state.keys)): True}
    with pytest.raises(ValueError, match="missing"):
        settings.set_value("enabled_simulation_modules", incomplete)


def test_set_value_rejects_non_dict() -> None:
    """Non-dict payloads (e.g. lists) raise a clear error."""
    settings = MidasSettings()
    with pytest.raises(ValueError, match="requires a dict"):
        settings.set_value("enabled_simulation_modules", ["system_degradation"])


def test_set_value_coerces_truthy_values_to_bool() -> None:
    """Truthy non-bool values (e.g. ``1``) are coerced to real booleans."""
    settings = MidasSettings()
    state = settings.get_state("enabled_simulation_modules")
    assert isinstance(state, BooleanMappingSettingState)
    coerced = dict.fromkeys(state.value, 1)
    settings.set_value("enabled_simulation_modules", coerced)
    stored = settings.get_value("enabled_simulation_modules")
    assert all(isinstance(value, bool) for value in stored.values())
    assert all(stored.values())
