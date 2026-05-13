"""Thin facade exposing the MidasSettings + MidasConfigData singletons.

``ApplicationState`` orchestrates startup loading (JSON state then workbook
reference data) and reports a :class:`LoadResult` for CLI status messages.
The actual configuration lives on the ``MidasSettings`` and ``MidasConfigData``
singletons; this class only owns the load-status bookkeeping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.config.midas_config_data import MidasConfigData
from src.config.midas_settings import MidasSettings
from src.io.loaders import ConfigWorkbookLoadError, MidasConfigDataLoader

logger = logging.getLogger(__name__)


@dataclass
class LoadResult:
    """Result of a configuration load operation."""

    success: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facility_types_loaded: int = 0
    system_types_loaded: int = 0
    installation_locations_loaded: int = 0
    state_file_applied: bool = False

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        self.success = False

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)


@dataclass
class ApplicationState:
    """Mutable application state for CLI and runtime.

    Holds the load-status report and convenience handles for the singletons.
    Use :meth:`initialize` to load JSON state then workbook reference data.
    """

    settings: MidasSettings
    config_data: MidasConfigData
    load_result: LoadResult = field(default_factory=LoadResult)

    @classmethod
    def initialize(
        cls,
        config_path: Path | None = None,
        state_path: Path | None = None,
    ) -> ApplicationState:
        """Load JSON state and workbook reference data, returning the new state."""
        load_result = LoadResult()

        settings = MidasSettings()

        resolved_state_path = state_path or MidasSettings.default_state_path()
        try:
            applied = settings.load_state(resolved_state_path)
            load_result.state_file_applied = applied
            if not applied:
                load_result.add_warning(f"No state file at {resolved_state_path}; using default settings.")
        except (OSError, ValueError) as exc:
            logger.exception("Failed to load MidasSettings state file")
            load_result.add_warning(f"State file load error at {resolved_state_path}: {exc}")

        try:
            settings.sync_simulation_module_registry()
        except Exception as exc:
            logger.exception("Failed to sync simulation module registry")
            load_result.add_warning(f"Simulation module registry sync error: {exc}")

        resolved_config_path = config_path if config_path is not None else MidasSettings.DEFAULT_CONFIG_DATA_PATH
        config_data = MidasConfigData()

        try:
            if not Path(resolved_config_path).exists():
                load_result.add_warning(f"Configuration file not found: {resolved_config_path}\nUsing empty reference data.")
                config_data.clear()
            else:
                summary = MidasConfigDataLoader().load(resolved_config_path)
                load_result.facility_types_loaded = summary.facility_types_loaded
                load_result.system_types_loaded = summary.system_types_loaded
                load_result.installation_locations_loaded = summary.installation_locations_loaded
                for warning in summary.warnings:
                    load_result.add_warning(warning)

                if load_result.facility_types_loaded == 0:
                    load_result.add_warning("No facility types loaded from configuration.")
                if load_result.system_types_loaded == 0:
                    load_result.add_warning("No system types loaded from configuration.")
                if load_result.installation_locations_loaded == 0:
                    load_result.add_warning("No installation locations loaded from configuration.")

        except (ConfigWorkbookLoadError, OSError, TypeError, ValueError) as exc:
            logger.exception("Failed to load configuration")
            load_result.add_error(f"Configuration load error: expected readable workbook (got {exc})")
            config_data.clear()

        return cls(settings=settings, config_data=config_data, load_result=load_result)

    @classmethod
    def with_defaults(cls) -> ApplicationState:
        """Create application state without loading workbook or state file."""
        MidasSettings.reset()
        MidasConfigData.reset()
        settings = MidasSettings()
        try:
            settings.sync_simulation_module_registry()
        except Exception:
            logger.exception("Failed to sync simulation module registry")
        return cls(
            settings=settings,
            config_data=MidasConfigData(),
            load_result=LoadResult(
                success=True,
                warnings=["Using default settings (no configuration file loaded)."],
            ),
        )

    @property
    def initialized_successfully(self) -> bool:
        """Check if configuration was loaded successfully."""
        return self.load_result.success

    @property
    def has_warnings(self) -> bool:
        """Check if there were any warnings during load."""
        return len(self.load_result.warnings) > 0

    @property
    def has_errors(self) -> bool:
        """Check if there were any errors during load."""
        return len(self.load_result.errors) > 0

    def get_status_message(self) -> str:
        """Get a formatted status message for display."""
        lines = []
        if self.load_result.success:
            lines.append("[green]Configuration loaded successfully![/green]")
            lines.append(f"  Facility types: {self.load_result.facility_types_loaded}")
            lines.append(f"  System types: {self.load_result.system_types_loaded}")
            lines.append(f"  Installation locations: {self.load_result.installation_locations_loaded}")
            if self.load_result.state_file_applied:
                lines.append(f"  State file: {MidasSettings.default_state_path()} (loaded)")
        else:
            lines.append("[red]Configuration load failed![/red]")

        if self.load_result.errors:
            lines.append("")
            lines.append("[red]Errors:[/red]")
            for error in self.load_result.errors:
                lines.append(f"  - {error}")

        if self.load_result.warnings:
            lines.append("")
            lines.append("[yellow]Warnings:[/yellow]")
            for warning in self.load_result.warnings:
                lines.append(f"  - {warning}")

        return "\n".join(lines)

    def reload(
        self,
        config_path: Path | None = None,
        state_path: Path | None = None,
    ) -> ApplicationState:
        """Reload by re-running :meth:`initialize`."""
        return ApplicationState.initialize(config_path=config_path, state_path=state_path)


# Global application state singleton for CLI
_app_state: ApplicationState | None = None


def get_app_state() -> ApplicationState:
    """Return the process-wide singleton, creating it with ``initialize()`` if needed."""
    global _app_state
    if _app_state is None:
        _app_state = ApplicationState.initialize()
    return _app_state


def set_app_state(state: ApplicationState) -> None:
    """Replace the process-wide singleton (tests and advanced CLI flows)."""
    global _app_state
    _app_state = state


def reset_app_state() -> None:
    """Reset the global application state and clear singletons (tests)."""
    global _app_state
    _app_state = None
    MidasSettings.reset()
    MidasConfigData.reset()
