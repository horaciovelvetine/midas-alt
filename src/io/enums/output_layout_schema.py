"""How exported tables are split across files (normalized vs denormalized)."""

from enum import Enum


class OutputLayoutSchema(Enum):
    """Normalized (per-entity tables) or denormalized (single flat table)."""

    NORMALIZED = "normalized"  # Separate tables for installations, facilities, systems
    DENORMALIZED = "denormalized"  # Single flattened table
