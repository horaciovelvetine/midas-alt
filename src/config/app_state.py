"""Application state management for CLI.

Provides a central state container that holds the loaded configuration
and tracks initialization status, errors, and warnings.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .settings import MIDASSettings

logger = logging.getLogger(__name__)


@dataclass
class LoadResult:
    """Result of a configuration load operation."""
    
    success: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    facility_types_loaded: int = 0
    system_types_loaded: int = 0
    
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
    
    This class holds the loaded configuration settings and tracks
    the status of initialization. It provides a clean interface
    for the CLI to access configuration without global mutable state.
    """
    
    settings: MIDASSettings
    load_result: LoadResult = field(default_factory=LoadResult)
    
    @classmethod
    def initialize(cls, config_path: Path | None = None) -> "ApplicationState":
        """Load configuration and create application state.
        
        Args:
            config_path: Path to configuration file. If None, uses default.
            
        Returns:
            Initialized ApplicationState instance.
        """
        load_result = LoadResult()
        
        # Determine config path
        if config_path is None:
            config_path = MIDASSettings.default_config_path()
        
        # Try to load settings
        try:
            if not config_path.exists():
                load_result.add_warning(
                    f"Configuration file not found: {config_path}\n"
                    "Using default settings."
                )
                settings = MIDASSettings.with_defaults()
            else:
                settings = MIDASSettings.from_excel(config_path)
                load_result.facility_types_loaded = len(settings.facility_types)
                load_result.system_types_loaded = len(settings.system_types)
                
                # Add success info
                if load_result.facility_types_loaded == 0:
                    load_result.add_warning("No facility types loaded from configuration.")
                if load_result.system_types_loaded == 0:
                    load_result.add_warning("No system types loaded from configuration.")
                    
        except Exception as e:
            logger.exception("Failed to load configuration")
            load_result.add_error(f"Failed to load configuration: {e}")
            settings = MIDASSettings.with_defaults()
        
        return cls(settings=settings, load_result=load_result)
    
    @classmethod
    def with_defaults(cls) -> "ApplicationState":
        """Create application state with default settings (no file load)."""
        return cls(
            settings=MIDASSettings.with_defaults(),
            load_result=LoadResult(
                success=True,
                warnings=["Using default settings (no configuration file loaded)."]
            )
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
    
    def reload(self, config_path: Path | None = None) -> "ApplicationState":
        """Reload configuration from file.
        
        Args:
            config_path: Path to configuration file. If None, uses default.
            
        Returns:
            New ApplicationState with reloaded configuration.
        """
        return ApplicationState.initialize(config_path)


# Global application state singleton for CLI
_app_state: ApplicationState | None = None


def get_app_state() -> ApplicationState:
    """Get or create the global application state.
    
    Returns:
        The global ApplicationState instance.
    """
    global _app_state
    if _app_state is None:
        _app_state = ApplicationState.initialize()
    return _app_state


def set_app_state(state: ApplicationState) -> None:
    """Set the global application state.
    
    Args:
        state: The ApplicationState to set as global.
    """
    global _app_state
    _app_state = state


def reset_app_state() -> None:
    """Reset the global application state (forces re-initialization on next access)."""
    global _app_state
    _app_state = None
