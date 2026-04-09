"""Top-level installation aggregate and facility index."""

from dataclasses import dataclass, field

from src.functions import generate_id


@dataclass
class Installation:
    """Root of the hierarchy; holds facility IDs and rolled-up condition."""

    id: str = field(default_factory=generate_id)
    title: str = ""
    location: str = ""
    region: str = ""
    coordinates: str = ""

    # Child references (IDs only)
    facility_ids: list[str] = field(default_factory=list)

    # Computed/aggregate values (set by services)
    condition_index: float | None = None
