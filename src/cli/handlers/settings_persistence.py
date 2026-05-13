"""Helpers that persist ``MidasSettings`` state on edit return and on app exit."""

from __future__ import annotations

import logging

from src.cli.utils import DisplayHelper, InputHelper
from src.config import MidasSettings

logger = logging.getLogger(__name__)


def maybe_prompt_save() -> bool:
    """Prompt the user to save when ``MidasSettings`` has unsaved changes.

    Returns:
        ``True`` if the state was written to disk during this call.

    """
    settings = MidasSettings()
    if not settings.is_dirty():
        return False

    if not InputHelper.confirm(
        "You have unsaved settings changes. Save them to output/midas_settings.json now?",
        default=True,
    ):
        return False
    return _save_and_notify()


def force_save_on_exit() -> bool:
    """Unconditionally persist current ``MidasSettings`` state when dirty.

    Used as the final safety net on application shutdown so unsaved edits are
    not silently lost. No prompt is shown.

    Returns:
        ``True`` if the state was written to disk.

    """
    if not MidasSettings().is_dirty():
        return False
    return _save_and_notify(silent=True)


def _save_and_notify(silent: bool = False) -> bool:
    """Write ``MidasSettings`` state to disk and, unless silent, print a notice."""
    try:
        target = MidasSettings().save_state()
    except OSError as exc:
        DisplayHelper.print_error(f"Failed to save settings: {exc}", title="Settings")
        logger.exception("Failed to write MidasSettings state")
        return False
    if not silent:
        DisplayHelper.print_success(f"Saved current settings to: {target}", title="Settings")
    return True
