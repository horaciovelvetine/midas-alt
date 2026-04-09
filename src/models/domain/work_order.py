"""Maintenance work order linked to installation, facility, and system."""

from dataclasses import dataclass, field
from datetime import datetime

from src.enums import WO_Priority, WO_Status, WO_TradeSkill
from src.functions import generate_id


@dataclass
class WorkOrder:
    """Represents a maintenance work order linked to system hierarchy."""

    # Identification/Related Infra
    id: str = field(default_factory=generate_id)
    installation_id: str | None = None
    facility_id: str | None = None
    system_id: str | None = None

    # W/O Setup
    requesting_organization: str | None = None
    work_category: str | None = None
    room_area: str | None = None

    # Date/Time(s)
    request_datetime: datetime | None = None
    completion_datetime: datetime | None = None

    # Enumerated status
    status: WO_Status | None = None
    trade: WO_TradeSkill | None = None
    priority: WO_Priority | None = None

    # Text Details
    problem_description: str | None = None
    requested_action: str | None = None
    actions_taken: str | None = None

    impacts_mission: bool = False
