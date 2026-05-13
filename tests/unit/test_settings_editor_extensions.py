"""Extended coverage for the interactive ``MidasSettings`` editor."""

from __future__ import annotations

import pytest

from src.cli.handlers import settings_editor
from src.cli.handlers.settings_editor import (
    _edit_bathtub_distribution,
    _edit_distribution,
    _edit_event_rate_distribution,
    _edit_mapping,
    _edit_normal_distribution,
    _edit_piecewise_distribution,
    _edit_range,
    _edit_string,
    _prompt_add_segment,
    _prompt_edit_segment,
    _prompt_remove_segment,
    edit_setting,
)
from src.cli.utils.input import InputHelper
from src.config import MidasSettings
from src.config.setting_state import (
    DistributionSettingState,
    MappingSettingState,
    RangeSettingState,
    StringSettingState,
)
from src.models.distributions import (
    BathtubCurveDistribution,
    NormalCurveDistribution,
    PiecewiseCurveDistribution,
    WeightedProbabilityDistribution,
    WeightedProbabilitySegment,
)


@pytest.fixture(autouse=True)
def _silence_display(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace display helpers with no-ops so tests don't print boilerplate."""
    monkeypatch.setattr(
        settings_editor.DisplayHelper, "print_info", staticmethod(lambda *a, **k: None)
    )
    monkeypatch.setattr(
        settings_editor.DisplayHelper,
        "print_success",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        settings_editor.DisplayHelper,
        "print_warning",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        settings_editor.DisplayHelper,
        "print_error",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        settings_editor.DisplayHelper,
        "print_table",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        InputHelper, "wait_for_continue", staticmethod(lambda message="": None)
    )


def _script(monkeypatch: pytest.MonkeyPatch, **answers) -> None:
    """Install scripted responses for the various ``InputHelper`` methods."""
    queues = {key: list(values) for key, values in answers.items()}

    def _make_fake(name):
        def _inner(*args, **kwargs):
            queue = queues[name]
            return queue.pop(0)

        return _inner

    if "ask_number" in queues:
        monkeypatch.setattr(
            InputHelper, "ask_number", staticmethod(_make_fake("ask_number"))
        )
    if "ask_choice" in queues:
        monkeypatch.setattr(
            InputHelper, "ask_choice", staticmethod(_make_fake("ask_choice"))
        )
    if "get_input_with_backspace" in queues:
        monkeypatch.setattr(
            InputHelper,
            "get_input_with_backspace",
            staticmethod(_make_fake("get_input_with_backspace")),
        )


# ! ==========================================================================================>
# ! _edit_range
# ! ==========================================================================================>


def test_edit_range_cancels_when_low_value_is_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``None`` from the first prompt cancels the range edit."""
    state: RangeSettingState = MidasSettings().get_state(
        "facilities_per_installation"
    )  # type: ignore[assignment]
    original = state.value
    _script(monkeypatch, ask_number=[None])

    changed = _edit_range("facilities_per_installation", state)

    assert changed is False
    assert state.value == original


def test_edit_range_cancels_when_high_value_is_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``None`` from the second prompt also cancels (low captured first)."""
    state: RangeSettingState = MidasSettings().get_state(
        "facilities_per_installation"
    )  # type: ignore[assignment]
    original = state.value
    _script(monkeypatch, ask_number=[5, None])

    changed = _edit_range("facilities_per_installation", state)
    assert changed is False
    assert state.value == original


def test_edit_range_returns_false_when_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-entering the same low/high pair does not mark the value changed."""
    state: RangeSettingState = MidasSettings().get_state(
        "facilities_per_installation"
    )  # type: ignore[assignment]
    low, high = state.value
    _script(monkeypatch, ask_number=[low, high])

    assert _edit_range("facilities_per_installation", state) is False


# ! ==========================================================================================>
# ! _edit_string
# ! ==========================================================================================>


def test_edit_string_choices_cancel_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A back response on a choice-bound string editor cancels without changes."""
    settings = MidasSettings()
    settings._states["test_choice"] = StringSettingState(
        label="Test", description="-", value="alpha", choices=("alpha", "beta")
    )
    settings.mark_clean()
    state = settings.get_state("test_choice")
    _script(monkeypatch, ask_choice=[None])

    assert _edit_string("test_choice", state) is False
    assert settings.get_value("test_choice") == "alpha"


def test_edit_string_free_text_blank_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank free-text response is treated as cancel."""
    settings = MidasSettings()
    state: StringSettingState = settings.get_state("excel_sheet_main")  # type: ignore[assignment]
    original = state.value
    _script(monkeypatch, get_input_with_backspace=[""])

    assert _edit_string("excel_sheet_main", state) is False
    assert settings.get_value("excel_sheet_main") == original


def test_edit_string_returns_false_when_value_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-entering the current free-text value is a no-op."""
    settings = MidasSettings()
    state: StringSettingState = settings.get_state("excel_sheet_main")  # type: ignore[assignment]
    _script(monkeypatch, get_input_with_backspace=[state.value])

    assert _edit_string("excel_sheet_main", state) is False


# ! ==========================================================================================>
# ! _edit_mapping
# ! ==========================================================================================>


def test_edit_mapping_keeping_current_values_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mapping editor whose user keeps every entry blank reports no change."""
    settings = MidasSettings()
    state: MappingSettingState = settings.get_state(
        "system_degradation_state_rate_multipliers"
    )  # type: ignore[assignment]
    keys = list(state.value.keys())
    _script(monkeypatch, get_input_with_backspace=[""] * len(keys))

    assert _edit_mapping("system_degradation_state_rate_multipliers", state) is False


# ! ==========================================================================================>
# ! WEIGHTED DISTRIBUTION SEGMENT MUTATIONS
# ! ==========================================================================================>


def test_prompt_add_segment_appends_segment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A successful add prompt appends to the working segment list."""
    segments: list[WeightedProbabilitySegment] = []
    _script(monkeypatch, ask_number=[25], get_input_with_backspace=["new"])

    assert _prompt_add_segment(segments) is True
    assert len(segments) == 1
    assert segments[0].weight_percent == 25
    assert segments[0].value == "new"


def test_prompt_add_segment_cancel_on_blank_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank value during add cancels and leaves the segment list intact."""
    segments: list[WeightedProbabilitySegment] = []
    _script(monkeypatch, ask_number=[25], get_input_with_backspace=[""])

    assert _prompt_add_segment(segments) is False
    assert segments == []


def test_prompt_edit_segment_replaces_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An edit prompt replaces the targeted segment with the new values."""
    segments = [WeightedProbabilitySegment(50, "alpha")]
    _script(monkeypatch, ask_number=[1, 80], get_input_with_backspace=["beta"])

    assert _prompt_edit_segment(segments) is True
    assert segments[0].weight_percent == 80
    assert segments[0].value == "beta"


def test_prompt_remove_segment_drops_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid remove index drops that segment from the list."""
    segments = [
        WeightedProbabilitySegment(50, "alpha"),
        WeightedProbabilitySegment(50, "beta"),
    ]
    _script(monkeypatch, ask_number=[1])

    assert _prompt_remove_segment(segments) is True
    assert len(segments) == 1
    assert segments[0].value == "beta"


def test_prompt_remove_segment_short_circuits_on_empty_list() -> None:
    """Removing from an empty list returns ``False`` without prompting."""
    assert _prompt_remove_segment([]) is False


def test_prompt_edit_segment_short_circuits_on_empty_list() -> None:
    """Editing an empty list returns ``False`` without prompting."""
    assert _prompt_edit_segment([]) is False


# ! ==========================================================================================>
# ! NORMAL / BATHTUB / PIECEWISE / EVENT_RATE EDITORS
# ! ==========================================================================================>


def test_edit_normal_distribution_updates_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_edit_normal_distribution`` rebuilds the distribution with new floats."""
    settings = MidasSettings()
    distribution = NormalCurveDistribution(
        baseline_rate=0.1, amplitude=0.5, mean=0.5, stddev=0.2
    )
    settings._states["test_normal"] = DistributionSettingState(
        label="Test Normal", description="-", value=distribution
    )
    settings.mark_clean()

    _script(
        monkeypatch,
        get_input_with_backspace=["0.2", "0.6", "0.4", "0.25"],
    )

    assert _edit_normal_distribution("test_normal", distribution) is True
    new_value: NormalCurveDistribution = settings.get_value("test_normal")  # type: ignore[assignment]
    assert new_value.baseline_rate == 0.2
    assert new_value.stddev == 0.25


def test_edit_bathtub_distribution_returns_false_when_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keeping every value yields ``False`` and leaves settings clean."""
    distribution = BathtubCurveDistribution()
    settings = MidasSettings()
    settings._states["test_bathtub"] = DistributionSettingState(
        label="Test Bathtub", description="-", value=distribution
    )
    settings.mark_clean()

    _script(monkeypatch, get_input_with_backspace=[""] * 6)
    assert _edit_bathtub_distribution("test_bathtub", distribution) is False


def test_edit_piecewise_distribution_adds_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``add`` then ``done`` appends one point and persists the new distribution."""
    settings = MidasSettings()
    distribution = PiecewiseCurveDistribution([(0.0, 0.0), (1.0, 1.0)])
    settings._states["test_pw"] = DistributionSettingState(
        label="Test PW", description="-", value=distribution
    )
    settings.mark_clean()

    _script(
        monkeypatch,
        ask_choice=["a", "d"],
        get_input_with_backspace=["0.5", "0.7"],
    )

    assert _edit_piecewise_distribution("test_pw", distribution) is True
    new_value: PiecewiseCurveDistribution = settings.get_value("test_pw")  # type: ignore[assignment]
    assert (0.5, 0.7) in new_value.points


def test_edit_piecewise_distribution_done_immediately_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pressing ``done`` immediately leaves the curve unchanged."""
    distribution = PiecewiseCurveDistribution([(0.0, 0.0), (1.0, 1.0)])
    settings = MidasSettings()
    settings._states["test_pw"] = DistributionSettingState(
        label="Test PW", description="-", value=distribution
    )
    settings.mark_clean()

    _script(monkeypatch, ask_choice=["d"])
    assert _edit_piecewise_distribution("test_pw", distribution) is False


def test_edit_event_rate_distribution_handles_subclass_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls through to ``_edit_event_rate_distribution`` for unknown rate distributions."""
    settings = MidasSettings()

    class _CustomRate(NormalCurveDistribution):
        pass

    distribution = _CustomRate()
    settings._states["test_event"] = DistributionSettingState(
        label="Test Event", description="-", value=distribution
    )
    settings.mark_clean()

    _script(monkeypatch, get_input_with_backspace=[""] * 4)
    assert _edit_event_rate_distribution("test_event", distribution) is False


def test_edit_distribution_on_none_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """A distribution slot with ``None`` value prints a warning and returns ``False``."""
    settings = MidasSettings()
    settings._states["test_none"] = DistributionSettingState(
        label="Test None", description="-", value=None
    )
    state = settings.get_state("test_none")
    assert _edit_distribution("test_none", state) is False


# ! ==========================================================================================>
# ! edit_setting dispatcher
# ! ==========================================================================================>


def test_edit_setting_warns_for_unknown_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """``edit_setting`` returns ``False`` for setting types it doesn't recognise."""

    class _Unknown:
        label = "X"
        description = "-"

    state = _Unknown()
    assert edit_setting("anything", state) is False


def test_run_settings_editor_invalid_input_loops_then_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-numeric / out-of-range responses are ignored until ``q`` is entered."""
    responses = iter(["x", "999", "q"])
    monkeypatch.setattr(
        InputHelper,
        "safe_prompt_ask",
        staticmethod(lambda *a, **k: next(responses)),
    )

    assert settings_editor.run_settings_editor() is False
