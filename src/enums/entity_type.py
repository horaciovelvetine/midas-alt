"""Domain entity kinds used in runtime summaries and hierarchy traversal."""

from enum import Enum


class EntityType(Enum):
    """Installation, facility, or system entity discriminator."""

    INSTALLATION = "installation"
    FACILITY = "facility"
    SYSTEM = "system"
