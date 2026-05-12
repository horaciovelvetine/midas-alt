"""Public facade for simulation data generation."""

from src.models import DataStore

from .install_generator import InstallGenerator


class DataGenerator:
    """Facade that coordinates installation-level data generation."""

    def __init__(self, seed: int | None = None) -> None:
        """Initialize generation facade with an optional seed."""
        self.seed = seed
        self._install_generator = InstallGenerator(seed=seed)

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
