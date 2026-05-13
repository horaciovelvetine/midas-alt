"""Unit tests for ``MappingSettingState`` and the configurable degradation multipliers."""

from __future__ import annotations

import pytest

from src.cli.handlers.settings_editor import _edit_mapping
from src.cli.utils.input import InputHelper
from src.config import MidasSettings
from src.config.setting_state import MappingSettingState, SettingState
from src.simulation.modules.system_degradation import _annual_transition_rate

# ! ==========================================================================================>
# ! ROUND-TRIP SERIALIZATION
# ! ==========================================================================================>


def test_mapping_state_serialize_round_trip() -> None:
    """Mapping state survives a serialize/deserialize round trip."""
    state = MappingSettingState(
        label="Test Mapping",
        description="Round-trip test fixture.",
        value={"a": 1.0, "b": 2.5, "c": 3.0},
        keys=("a", "b", "c"),
        min=0.0,
        max=10.0,
        key_label="Letter",
        value_label="Score",
    )

    payload = state.serialize()
    restored = SettingState.deserialize(payload)

    assert isinstance(restored, MappingSettingState)
    assert restored.label == state.label
    assert restored.description == state.description
    assert restored.value == state.value
    assert restored.keys == state.keys
    assert restored.min == state.min
    assert restored.max == state.max
    assert restored.key_label == state.key_label
    assert restored.value_label == state.value_label


def test_mapping_state_preserves_declared_key_order_after_deserialize() -> None:
    """Deserialized mapping iterates in the declared ``keys`` order."""
    state = MappingSettingState(
        label="Ordered",
        description="-",
        value={"second": 2.0, "first": 1.0, "third": 3.0},
        keys=("first", "second", "third"),
    )

    restored = SettingState.deserialize(state.serialize())

    assert isinstance(restored, MappingSettingState)
    assert list(restored.value.keys()) == ["first", "second", "third"]


def test_mapping_state_constructor_rejects_missing_required_keys() -> None:
    """Constructor rejects ``value`` dicts missing keys declared in ``keys``."""
    with pytest.raises(ValueError, match="missing required keys"):
        MappingSettingState(
            label="Missing",
            description="-",
            value={"a": 1.0},
            keys=("a", "b"),
        )


# ! ==========================================================================================>
# ! MIDAS SETTINGS SET_VALUE VALIDATION
# ! ==========================================================================================>


def test_set_value_accepts_valid_mapping_and_marks_dirty() -> None:
    """A valid mapping is stored verbatim and flips the dirty flag."""
    settings = MidasSettings()
    new_values = {
        "excellent": 1.0,
        "good": 1.1,
        "fair": 1.2,
        "poor": 1.3,
        "critical": 1.4,
    }
    settings.set_value("system_degradation_state_rate_multipliers", new_values)

    stored = settings.get_value("system_degradation_state_rate_multipliers")
    assert stored == new_values
    assert list(stored.keys()) == ["excellent", "good", "fair", "poor", "critical"]
    assert settings.is_dirty() is True


def test_set_value_rejects_unknown_keys() -> None:
    """``set_value`` rejects mappings with keys outside the declared set."""
    settings = MidasSettings()
    bogus = {
        "excellent": 1.0,
        "good": 1.0,
        "fair": 1.0,
        "poor": 1.0,
        "critical": 1.0,
        "ultraviolet": 1.0,
    }
    with pytest.raises(ValueError, match="unexpected"):
        settings.set_value("system_degradation_state_rate_multipliers", bogus)


def test_set_value_rejects_missing_keys() -> None:
    """``set_value`` rejects partial mappings that drop required keys."""
    settings = MidasSettings()
    incomplete = {"excellent": 1.0, "good": 1.0}
    with pytest.raises(ValueError, match="missing"):
        settings.set_value("system_degradation_state_rate_multipliers", incomplete)


def test_set_value_rejects_out_of_bounds_value() -> None:
    """Values above the declared ``max`` raise a clear out-of-bounds error."""
    settings = MidasSettings()
    out_of_range = {
        "excellent": 1.0,
        "good": 1.0,
        "fair": 1.0,
        "poor": 1.0,
        "critical": 99.0,
    }
    with pytest.raises(ValueError, match="above maximum"):
        settings.set_value("system_degradation_state_rate_multipliers", out_of_range)


def test_set_value_rejects_non_dict() -> None:
    """Non-dict payloads (e.g. lists) raise a clear error."""
    settings = MidasSettings()
    with pytest.raises(ValueError, match="requires a dict"):
        settings.set_value("system_degradation_state_rate_multipliers", [1, 2, 3])


# ! ==========================================================================================>
# ! REGISTERED DEFAULT MATCHES LEGACY CONSTANT
# ! ==========================================================================================>


def test_default_multipliers_match_legacy_values() -> None:
    """Registered default mapping matches the previously hard-coded multipliers."""
    settings = MidasSettings()
    assert settings.get_value("system_degradation_state_rate_multipliers") == {
        "excellent": 0.9,
        "good": 1.0,
        "fair": 1.15,
        "poor": 1.3,
        "critical": 1.65,
    }


# ! ==========================================================================================>
# ! DEGRADATION MODULE READS THE MAPPING
# ! ==========================================================================================>


def test_annual_transition_rate_uses_supplied_multiplier() -> None:
    """Annual transition rate scales with the supplied state multiplier."""
    multipliers = {"good": 2.0, "poor": 0.5}

    fast = _annual_transition_rate(age_ratio=0.5, current_state="good", state_multipliers=multipliers)
    slow = _annual_transition_rate(age_ratio=0.5, current_state="poor", state_multipliers=multipliers)

    assert fast == pytest.approx(slow * 4.0)


def test_annual_transition_rate_returns_zero_for_missing_state() -> None:
    """Unknown current states yield a zero transition rate."""
    rate = _annual_transition_rate(
        age_ratio=0.5,
        current_state="failed",
        state_multipliers={"excellent": 1.0},
    )
    assert rate == 0.0


def test_annual_transition_rate_returns_zero_for_non_positive_multiplier() -> None:
    """A non-positive multiplier disables transitions for that state."""
    rate = _annual_transition_rate(
        age_ratio=0.75,
        current_state="critical",
        state_multipliers={"critical": 0.0},
    )
    assert rate == 0.0


# ! ==========================================================================================>
# ! CLI MAPPING EDITOR
# ! ==========================================================================================>


class _MappingPromptScript:
    """Pop pre-canned float strings to drive ``_prompt_float`` calls."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    def get_input_with_backspace(self, *_args, **_kwargs) -> str:
        return self.responses.pop(0)


def _install_mapping_prompt(monkeypatch: pytest.MonkeyPatch, script: _MappingPromptScript) -> None:
    monkeypatch.setattr(
        InputHelper,
        "get_input_with_backspace",
        staticmethod(script.get_input_with_backspace),
    )
    monkeypatch.setattr(InputHelper, "wait_for_continue", staticmethod(lambda message="": None))


def test_edit_mapping_updates_only_changed_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_edit_mapping`` writes only the entries the user actually changed."""
    settings = MidasSettings()
    state = settings.get_state("system_degradation_state_rate_multipliers")
    # Keep excellent, edit good->1.5, edit fair->1.2, keep poor, keep critical.
    script = _MappingPromptScript(["", "1.5", "1.2", "", ""])
    _install_mapping_prompt(monkeypatch, script)

    changed = _edit_mapping("system_degradation_state_rate_multipliers", state)

    assert changed is True
    updated = settings.get_value("system_degradation_state_rate_multipliers")
    assert updated["excellent"] == 0.9
    assert updated["good"] == 1.5
    assert updated["fair"] == 1.2
    assert updated["poor"] == 1.3
    assert updated["critical"] == 1.65


def test_edit_mapping_returns_false_when_all_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All-blank user input leaves the mapping untouched and reports no change."""
    settings = MidasSettings()
    state = settings.get_state("system_degradation_state_rate_multipliers")
    original = dict(settings.get_value("system_degradation_state_rate_multipliers"))
    script = _MappingPromptScript(["", "", "", "", ""])
    _install_mapping_prompt(monkeypatch, script)

    changed = _edit_mapping("system_degradation_state_rate_multipliers", state)

    assert changed is False
    assert settings.get_value("system_degradation_state_rate_multipliers") == original
    assert settings.is_dirty() is False
