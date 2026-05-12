"""Enumerations for work-order priority, trade skill, and status.

- WorkOrderPriority: Work category levels (Emergency, Urgent, Routine, Preventive Maintenance).
- WorkOrderTradeSkill: Skilled trades required to perform work orders
  (HVAC, Electrical, Structural, Fire Protection, Plumbing, ESS, Power Production).
- WorkOrderStatus: Workflow states for work orders (Submitted, Approved, In Progress, Completed).

Work-order values are aligned to HQ SPOC/S4W guidance:
https://static.e-publishing.af.mil/production/1/spoc/publication/spoci21-108/spoci21-108.pdf

The key classification attributes used in work order tracking and processing across the application.
"""

from enum import Enum


class WO_Priority(Enum):
    """Work category / priority bucket for a work order.

    Values mirror the ``Work Category`` column in the MIDAS config workbook's
    ``Work Orders`` sheet so that generated entries can copy the categorical
    label directly from a sampled template row.
    """

    EMERGENCY = "Emergency"
    URGENT = "Urgent"
    ROUTINE = "Routine"
    MAINTENANCE = "Preventive Maintenance"


class WO_TradeSkill(Enum):
    """Skilled trades associated with work-order execution."""

    HVAC = "HVAC"
    ELECTRICAL = "Electrical"
    STRUCTURAL = "Structural"
    FIRE_PROTECTION = "Fire Protection"
    PLUMBING = "Plumbing"
    ESS = "ESS"
    POWER_PRODUCTION = "Power Production"


class WO_Status(Enum):
    """Lifecycle states for work-order processing."""

    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
