"""Shared pytest setup for repository-local imports.

Also resets the ``MidasSettings`` and ``MidasConfigData`` singletons between
tests and runs :meth:`ApplicationState.initialize` once per test so each test
sees freshly loaded workbook reference data and default runtime settings.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def _reset_midas_singletons():
    """Reset configuration singletons and load workbook data before each test."""
    from src.config import ApplicationState, reset_app_state

    reset_app_state()
    ApplicationState.initialize()
    yield
    reset_app_state()
