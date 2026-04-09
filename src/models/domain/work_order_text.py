"""Cached template triple for synthetic work order narrative fields."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkOrderText:
    """Problem, requested action, and action-taken strings for one template row."""

    problem_description: str
    requested_action: str
    action_taken: str
