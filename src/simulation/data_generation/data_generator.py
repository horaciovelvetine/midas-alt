"""Public facade for simulation data generation."""

from src.config.app_state import get_app_state
from src.config.settings import MIDASSettings
from src.models import DataStore

from .install_generator import InstallGenerator


class DataGenerator:
    """Facade that coordinates installation-level data generation."""

    def __init__(self, settings: MIDASSettings | None = None, seed: int | None = None):
        """Initialize generation facade with optional settings and seed."""
        self.settings = settings or get_app_state().settings
        self.seed = seed
        self._install_generator = InstallGenerator(settings=self.settings, seed=seed)

    def generate_installation(self) -> DataStore:
        """Generate a single installation hierarchy."""
        installation, facilities, systems, work_orders = (
            self._install_generator.generate()
        )
        return DataStore.from_single_installation(
            installation=installation,
            facilities=facilities,
            systems=systems,
            work_orders=work_orders,
        )

    def generate_installations(self, count: int) -> DataStore:
        """Generate multiple installations and return a merged result."""
        return self._install_generator.generate_by_count(count)
