"""Unit tests for the interactive ``MidasSettings`` editor and dirty tracking."""

from __future__ import annotations

import pytest

from src.cli.handlers import settings_editor
from src.cli.handlers.settings_editor import (
    _edit_distribution,
    _edit_float,
    _edit_integer,
    _edit_range,
    _edit_string,
)
from src.cli.utils.input import InputHelper
from src.config import MidasSettings
from src.config.setting_state import (
    DistributionSettingState,
    FloatSettingState,
    IntegerSettingState,
    RangeSettingState,
    StringSettingState,
)
from src.models.distributions import (
    WeightedProbabilityDistribution,
    WeightedProbabilitySegment,
)

# ! ==========================================================================================>
# ! DIRTY-FLAG TRACKING
# ! ==========================================================================================>


def test_settings_start_clean_after_initialization() -> None:
    """A fresh ``MidasSettings`` instance has no pending changes."""
    assert MidasSettings().is_dirty() is False


def test_set_value_marks_dirty() -> None:
    """Writing any setting flips the dirty flag from clean to dirty."""
    settings = MidasSettings()
    assert settings.is_dirty() is False
    settings.set_value("condition_index_degraded_threshold", 30.0)
    assert settings.is_dirty() is True


def test_save_state_clears_dirty_flag(tmp_path) -> None:
    """Saving state to disk clears the dirty flag."""
    settings = MidasSettings()
    settings.set_value("condition_index_degraded_threshold", 30.0)
    assert settings.is_dirty() is True

    target = tmp_path / "midas_settings.json"
    settings.save_state(target)
    assert settings.is_dirty() is False


def test_load_state_clears_dirty_flag(tmp_path) -> None:
    """Loading state from disk clears any in-memory dirty flag."""
    settings = MidasSettings()
    target = tmp_path / "midas_settings.json"
    settings.save_state(target)

    settings.set_value("condition_index_degraded_threshold", 50.0)
    assert settings.is_dirty() is True

    settings.load_state(target)
    assert settings.is_dirty() is False


def test_mark_clean_resets_flag() -> None:
    """``mark_clean`` clears the dirty flag without writing to disk."""
    settings = MidasSettings()
    settings.set_value("condition_index_degraded_threshold", 40.0)
    settings.mark_clean()
    assert settings.is_dirty() is False


# ! ==========================================================================================>
# ! PROMPT MOCK HELPERS
# ! ==========================================================================================>


class _PromptScript:
    """Test double that pops queued responses for each ``InputHelper`` call."""

    def __init__(self, *, numbers: list = None, strings: list = None, choices: list = None) -> None:
        self.numbers = list(numbers or [])
        self.strings = list(strings or [])
        self.choices = list(choices or [])

    def ask_number(self, *args, **kwargs):
        return self.numbers.pop(0)

    def get_input_with_backspace(self, *args, **kwargs):
        return self.strings.pop(0)

    def ask_choice(self, *args, **kwargs):
        return self.choices.pop(0)


def _install_prompt_script(monkeypatch: pytest.MonkeyPatch, script: _PromptScript) -> None:
    monkeypatch.setattr(InputHelper, "ask_number", staticmethod(script.ask_number))
    monkeypatch.setattr(
        InputHelper,
        "get_input_with_backspace",
        staticmethod(script.get_input_with_backspace),
    )
    monkeypatch.setattr(InputHelper, "ask_choice", staticmethod(script.ask_choice))
    monkeypatch.setattr(InputHelper, "wait_for_continue", staticmethod(lambda message="": None))


# ! ==========================================================================================>
# ! PER-TYPE EDITORS
# ! ==========================================================================================>


def test_edit_float_updates_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_edit_float`` writes the new value and reports a change."""
    settings = MidasSettings()
    state: FloatSettingState = settings.get_state("condition_index_degraded_threshold")  # type: ignore[assignment]
    _install_prompt_script(monkeypatch, _PromptScript(strings=["42.5"]))

    changed = _edit_float("condition_index_degraded_threshold", state)

    assert changed is True
    assert settings.get_value("condition_index_degraded_threshold") == 42.5
    assert settings.is_dirty() is True


def test_edit_float_blank_input_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank input on a float editor cancels and leaves state untouched."""
    settings = MidasSettings()
    original = settings.get_value("condition_index_degraded_threshold")
    state: FloatSettingState = settings.get_state("condition_index_degraded_threshold")  # type: ignore[assignment]
    _install_prompt_script(monkeypatch, _PromptScript(strings=[""]))

    changed = _edit_float("condition_index_degraded_threshold", state)

    assert changed is False
    assert settings.get_value("condition_index_degraded_threshold") == original
    assert settings.is_dirty() is False


def test_edit_integer_updates_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_edit_integer`` writes the new value and reports a change."""
    settings = MidasSettings()
    state: IntegerSettingState = settings.get_state("maximum_vertical_dependency_depth")  # type: ignore[assignment]
    _install_prompt_script(monkeypatch, _PromptScript(numbers=[5]))

    changed = _edit_integer("maximum_vertical_dependency_depth", state)

    assert changed is True
    assert settings.get_value("maximum_vertical_dependency_depth") == 5
    assert settings.is_dirty() is True


def test_edit_integer_back_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``None`` reply (back) cancels the integer editor."""
    settings = MidasSettings()
    state: IntegerSettingState = settings.get_state("maximum_vertical_dependency_depth")  # type: ignore[assignment]
    original = state.value
    _install_prompt_script(monkeypatch, _PromptScript(numbers=[None]))

    changed = _edit_integer("maximum_vertical_dependency_depth", state)

    assert changed is False
    assert settings.get_value("maximum_vertical_dependency_depth") == original
    assert settings.is_dirty() is False


def test_edit_range_swaps_reversed_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_edit_range`` normalizes ``(high, low)`` input into ``(low, high)``."""
    settings = MidasSettings()
    state: RangeSettingState = settings.get_state("facilities_per_installation")  # type: ignore[assignment]
    _install_prompt_script(monkeypatch, _PromptScript(numbers=[20, 10]))

    changed = _edit_range("facilities_per_installation", state)

    assert changed is True
    assert settings.get_value("facilities_per_installation") == (10, 20)
    assert settings.is_dirty() is True


def test_edit_string_with_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    """A constrained string setting writes the chosen option."""
    settings = MidasSettings()
    settings._states["test_choice_setting"] = StringSettingState(
        label="Test Choice",
        description="-",
        value="alpha",
        choices=("alpha", "beta", "gamma"),
    )
    settings.mark_clean()
    state = settings.get_state("test_choice_setting")
    _install_prompt_script(monkeypatch, _PromptScript(choices=["beta"]))

    changed = _edit_string("test_choice_setting", state)

    assert changed is True
    assert settings.get_value("test_choice_setting") == "beta"
    assert settings.is_dirty() is True


def test_edit_string_free_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A free-text string setting accepts arbitrary user input."""
    settings = MidasSettings()
    state: StringSettingState = settings.get_state("excel_sheet_main")  # type: ignore[assignment]
    _install_prompt_script(monkeypatch, _PromptScript(strings=["My Custom Sheet"]))

    changed = _edit_string("excel_sheet_main", state)

    assert changed is True
    assert settings.get_value("excel_sheet_main") == "My Custom Sheet"


def test_edit_weighted_distribution_updates_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Editing a weighted distribution segment persists the new weight and value."""
    settings = MidasSettings()
    settings._states["test_weighted_setting"] = DistributionSettingState(
        label="Test Weighted",
        description="-",
        value=WeightedProbabilityDistribution(
            [
                WeightedProbabilitySegment(50, "low"),
                WeightedProbabilitySegment(50, "high"),
            ]
        ),
    )
    settings.mark_clean()
    state = settings.get_state("test_weighted_setting")

    # Edit segment 1: change percentage to 70 and value to "edited", then done.
    script = _PromptScript(
        numbers=[1, 70],
        strings=["edited"],
        choices=["e", "d"],
    )
    _install_prompt_script(monkeypatch, script)

    changed = _edit_distribution("test_weighted_setting", state)

    assert changed is True
    new_dist = settings.get_value("test_weighted_setting")
    assert isinstance(new_dist, WeightedProbabilityDistribution)
    assert new_dist.segments[0].weight_percent == 70
    assert new_dist.segments[0].value == "edited"
    assert new_dist.segments[1].weight_percent == 50
    assert new_dist.segments[1].value == "high"
    assert settings.is_dirty() is True


def test_edit_weighted_distribution_done_without_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Choosing ``done`` without edits leaves the distribution unchanged."""
    settings = MidasSettings()
    state = settings.get_state("generated_resiliency_grade_distribution")
    _install_prompt_script(monkeypatch, _PromptScript(choices=["d"]))

    changed = _edit_distribution("generated_resiliency_grade_distribution", state)

    assert changed is False
    assert settings.is_dirty() is False


# ! ==========================================================================================>
# ! TOP-LEVEL PICKER
# ! ==========================================================================================>


def test_run_settings_editor_back_returns_no_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Picking ``back`` from the top-level editor reports no changes."""
    monkeypatch.setattr(InputHelper, "safe_prompt_ask", staticmethod(lambda *a, **k: "b"))
    assert settings_editor.run_settings_editor() is False
    assert MidasSettings().is_dirty() is False
