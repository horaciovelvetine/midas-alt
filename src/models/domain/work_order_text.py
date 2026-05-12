"""Cached template row from the workbook ``Work Orders`` sheet."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkOrderText:
    """One ``Work Orders`` sheet row used to seed generated work orders.

    Carries both the categorical attributes copied onto each generated
    :class:`~src.models.domain.work_order.WorkOrder` (``trade``,
    ``work_category``, optional ``priority_code``) and the three narrative
    fields (``problem_description``, ``requested_action``, ``action_taken``).
    """

    system_title: str
    trade: str
    work_category: str
    priority_code: int | None
    problem_description: str
    requested_action: str
    action_taken: str
