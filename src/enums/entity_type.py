from enum import Enum


class EntityType(Enum):
    """Type of domain entity"""

    INSTALLATION = "installation"
    FACILITY = "facility"
    SYSTEM = "system"
