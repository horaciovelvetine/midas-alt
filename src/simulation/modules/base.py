"""Base abstractions for simulation modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.enums.entity_type import EntityType

if TYPE_CHECKING:
    from src.simulation.runtime.session import SimulationSession


@dataclass(frozen=True)
class ModuleEvent:
    """Structured message emitted by a simulation module."""

    code: str
    message: str
    entity_id: str | None = None
    entity_type: EntityType | None = None
    should_pause: bool = False


class SimulationModuleBase(ABC):
    """Base class for tick-time simulation modules and pause policies."""

    @abstractmethod
    def apply(self, session: SimulationSession) -> list[ModuleEvent]:
        """Apply module logic to the current session tick."""
