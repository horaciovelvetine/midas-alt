"""Unit tests for :mod:`src.cli.handlers.settings_persistence`."""

from __future__ import annotations

import pytest

from src.cli.handlers import settings_persistence
from src.cli.utils.input import InputHelper
from src.config import MidasSettings


@pytest.fixture(autouse=True)
def _capture_display_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Replace ``DisplayHelper`` print calls with no-ops and record their use."""
    calls: dict[str, list] = {"success": [], "error": []}

    def _record(kind: str):
        def _inner(message: str, title: str = "") -> None:
            calls[kind].append((message, title))

        return _inner

    monkeypatch.setattr(
        settings_persistence.DisplayHelper, "print_success", _record("success")
    )
    monkeypatch.setattr(
        settings_persistence.DisplayHelper, "print_error", _record("error")
    )
    return calls


def test_maybe_prompt_save_skips_when_settings_are_clean() -> None:
    """A clean settings singleton returns immediately without confirming."""
    assert settings_persistence.maybe_prompt_save() is False


def test_maybe_prompt_save_writes_when_user_confirms(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    _capture_display_calls: dict[str, list],
) -> None:
    """A dirty settings singleton plus a confirmed prompt persists to disk."""
    settings = MidasSettings()
    settings.set_value("condition_index_degraded_threshold", 35.0)
    assert settings.is_dirty() is True

    target = tmp_path / "midas_settings.json"
    monkeypatch.setattr(
        settings, "save_state", lambda *args, **kwargs: target.touch() or target
    )
    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: True))

    assert settings_persistence.maybe_prompt_save() is True
    assert _capture_display_calls["success"]
    assert _capture_display_calls["success"][0][0].startswith(
        "Saved current settings to:"
    )


def test_maybe_prompt_save_skips_when_user_declines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A declined confirm leaves the dirty state untouched and returns ``False``."""
    settings = MidasSettings()
    settings.set_value("condition_index_degraded_threshold", 35.0)
    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: False))

    saved: list[bool] = []
    monkeypatch.setattr(
        settings, "save_state", lambda *args, **kwargs: saved.append(True)
    )

    assert settings_persistence.maybe_prompt_save() is False
    assert saved == []


def test_force_save_on_exit_writes_silently_when_dirty(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    _capture_display_calls: dict[str, list],
) -> None:
    """``force_save_on_exit`` never prompts and never prints success on save."""
    settings = MidasSettings()
    settings.set_value("condition_index_degraded_threshold", 28.0)

    target = tmp_path / "midas_settings.json"
    monkeypatch.setattr(
        settings, "save_state", lambda *args, **kwargs: target.touch() or target
    )

    assert settings_persistence.force_save_on_exit() is True
    assert _capture_display_calls["success"] == []


def test_force_save_on_exit_short_circuits_when_clean() -> None:
    """``force_save_on_exit`` is a no-op when no edits are pending."""
    assert settings_persistence.force_save_on_exit() is False


def test_save_failure_reports_error(
    monkeypatch: pytest.MonkeyPatch,
    _capture_display_calls: dict[str, list],
) -> None:
    """An OSError during ``save_state`` is surfaced via ``print_error``."""
    settings = MidasSettings()
    settings.set_value("condition_index_degraded_threshold", 33.0)
    monkeypatch.setattr(InputHelper, "confirm", staticmethod(lambda *a, **k: True))

    def _raise(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(settings, "save_state", _raise)

    assert settings_persistence.maybe_prompt_save() is False
    assert _capture_display_calls["error"]
    assert "disk full" in _capture_display_calls["error"][0][0]
