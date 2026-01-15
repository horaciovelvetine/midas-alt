"""Domain module - core business entities and enums.

This module contains pure data containers with no business logic.
All computation is handled by services.
"""

from .entities import (
    DependencyChain,
    Facility,
    Installation,
    PredictableEntity,
    System,
)
from .enums import DependencyTier, EntityType, UFCGrade

__all__ = [
    # Entities
    "Installation",
    "Facility",
    "System",
    "DependencyChain",
    "PredictableEntity",
    # Enums
    "UFCGrade",
    "DependencyTier",
    "EntityType",
]
