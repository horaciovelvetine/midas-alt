"""Generate work orders by sampling rows from the workbook ``Work Orders`` sheet."""

import random
from datetime import datetime, timedelta

from src.enums import WO_Priority, WO_Status, WO_TradeSkill
from src.models import System, WorkOrder, WorkOrderText

from .data_generator_base import DataGeneratorBase


class WorkOrderGenerator(DataGeneratorBase):
    """Generate work orders by copying categorical attributes and text from sampled templates."""

    def __init__(self, seed: int | None = None) -> None:
        """Initialize work-order generator with optional seed."""
        super().__init__(seed=seed)

    def generate_by_system(self, system: System) -> list[WorkOrder]:
        """Generate work orders for ``system`` from workbook-driven templates."""
        system_type = (
            self.config_data.get_system_type(system.system_type_key)
            if system.system_type_key
            else None
        )
        system_title = getattr(system_type, "title", None)

        context = self.build_system_distribution_context(
            system=system, system_type=system_type
        )
        horizon_years = max(1.0, float(system.age_years or 1))

        wo_count_distribution = self.settings.get_value(
            "generated_work_order_count_distribution"
        )
        wo_count = self.sample_event_count(
            wo_count_distribution,
            context=context,
            horizon_years=horizon_years,
        )

        work_orders: list[WorkOrder] = []
        for _ in range(wo_count):
            template = self.config_data.sample_work_order_template(system_title)
            status = self._sample_work_order_status()
            request_datetime = self._sample_request_datetime(system, status)
            completion_datetime = self._sample_completion_datetime(
                status, request_datetime
            )
            problem_description, requested_action, actions_taken = (
                self._text_fields_from_template(template, status)
            )

            work_orders.append(
                WorkOrder(
                    system_id=system.id,
                    facility_id=system.facility_id,
                    requesting_organization=self._sample_requesting_organization(),
                    work_category=template.work_category if template else None,
                    status=status,
                    priority=self._priority_from_template(template),
                    trade=self._trade_from_template(template),
                    request_datetime=request_datetime,
                    completion_datetime=completion_datetime,
                    problem_description=problem_description,
                    requested_action=requested_action,
                    actions_taken=actions_taken,
                    impacts_mission=bool(random.getrandbits(1)),
                )
            )

        return work_orders

    def _sample_work_order_status(self) -> WO_Status:
        distribution = self.settings.get_value(
            "generated_work_order_status_distribution"
        )
        sampled = distribution.sample()
        return self._to_enum_value(WO_Status, sampled, fallback=WO_Status.SUBMITTED)

    def _sample_requesting_organization(self) -> str | None:
        return self.config_data.get_random_work_order_requesting_organization()

    def _trade_from_template(self, template: WorkOrderText | None) -> WO_TradeSkill:
        """Resolve the sampled template's trade to a :class:`WO_TradeSkill` value."""
        if template is None:
            return random.choice(list(WO_TradeSkill))
        resolved = self._to_enum_value(WO_TradeSkill, template.trade, fallback=None)
        return resolved if resolved is not None else random.choice(list(WO_TradeSkill))

    def _priority_from_template(self, template: WorkOrderText | None) -> WO_Priority:
        """Resolve the sampled template's Work Category to a :class:`WO_Priority`."""
        if template is None:
            return WO_Priority.ROUTINE
        return self._to_enum_value(
            WO_Priority, template.work_category, fallback=WO_Priority.ROUTINE
        )

    def _text_fields_from_template(
        self, template: WorkOrderText | None, status: WO_Status
    ) -> tuple[str | None, str | None, str | None]:
        """Pull problem/requested/actions text from ``template``, gated by ``status``."""
        if template is None:
            base_problem = "example text"
            base_requested = "example text"
            base_actions = "example text"
        else:
            base_problem = template.problem_description or "example text"
            base_requested = template.requested_action or "example text"
            base_actions = template.action_taken or "example text"

        if status == WO_Status.COMPLETED:
            actions_taken: str | None = base_actions
        elif status == WO_Status.IN_PROGRESS:
            actions_taken = base_actions if random.random() < 0.5 else None
        else:
            actions_taken = None

        return base_problem, base_requested, actions_taken

    def _sample_request_datetime(self, system: System, status: WO_Status) -> datetime:
        now = datetime.now()
        start_year = system.year_constructed or max(
            now.year - int(system.age_years or 1), 1900
        )
        start = datetime(start_year, 1, 1)
        if start > now:
            start = now - timedelta(days=1)

        if status == WO_Status.SUBMITTED:
            lower = max(start, now - timedelta(days=60))
        elif status == WO_Status.APPROVED:
            lower = max(start, now - timedelta(days=120))
        elif status == WO_Status.IN_PROGRESS:
            lower = max(start, now - timedelta(days=180))
        else:
            lower = start

        if lower > now:
            return now
        total_seconds = int((now - lower).total_seconds())
        if total_seconds <= 0:
            return now
        return lower + timedelta(seconds=random.randint(0, total_seconds))

    def _sample_completion_datetime(
        self, status: WO_Status, request_datetime: datetime
    ) -> datetime | None:
        if status != WO_Status.COMPLETED:
            return None
        now = datetime.now()
        if request_datetime >= now:
            return now
        max_days = max(1, min(365, (now - request_datetime).days))
        completion_days = random.randint(1, max_days)
        completion_dt = request_datetime + timedelta(days=completion_days)
        return completion_dt if completion_dt <= now else now

    def _to_enum_value(self, enum_cls, sampled: object, fallback):
        if sampled is None:
            return fallback
        text = str(sampled).strip()
        if not text:
            return fallback
        normalized = text.lower()
        for enum_value in enum_cls:
            if normalized in {enum_value.name.lower(), str(enum_value.value).lower()}:
                return enum_value
        return fallback
