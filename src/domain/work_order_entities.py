from dataclasses import dataclass
import datetime
from enum import Enum
from domain.enums import UFCGrade


class WorkOrderPriority(Enum):
    EMERGENCY = "Emergency"
    URGENT = "Urgent"
    ROUTINE = "Routine"
    MAINTENANCE = "Maintenance"

class WorkOrderTradeSkill(Enum):
    HVAC = "HVAC"
    ELECTRICAL = "Electrical"
    STRUCTURAL = "Structural"
    FIRE_PROTECTION = "Fire Protection"

class WorkOrderStatus(Enum):
    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"

@dataclass
class SimulatedWorkedOrderInput:
    infrastructure_type: str = "" # The either installation, facility, or system title (smallest target available)
    condition_index: float = 0.00 # - 100.00 check if already degraded and return text which matches this 1-100 scale
    age: int = 1 # in years
    mission_criticality: int # (value 1-3), should be a deciding factor on the mission_essential_function_affected outcome
    resiliency_grade: UFCGrade # 1-4,  1 is no redundancy, 4 is has completely contained redundancy built in. 2/3 are gray... used to also affect mission_essential outcome
    remaining_service_life: int # expected..


@dataclass
class CEWorkOrder:

    id: str = "CE Work Order Number" # system generated
    requested_timestamp: datetime = datetime.now()
    requesting_organization: str = "" # (MOC, CoM, Delta S4)
    work_order_number: str = "" # Work order number, diff id from CE Work Order number or id
    installation_id: str = "" # Location Install ID
    facilty_id: str = "" # Location Facility ID ... use empty to tgt an entire installation
    system_id: str = "" # Location System ID ... use empty to target a entire facility
    priority_type: WorkOrderPriority = WorkOrderPriority.MAINTENANCE
    trade_skills_rquired: list[WorkOrderTradeSkill] = []
    # ? shop_code: str => Skip for now

    description: str = "" # Text block describes problem
    # 1. Observable condition
    # 2. Measureable impace
    # 3. No operational details beyond needed 
    requested_action: str = "" # steps needed to resolve
    mission_essential_function_affected: bool = True
    # ? justification_statement : str => tbd
    completion_date: datetime | None = None
    actions_taken: str = "" # Text block describes problem resolution

@dataclass
class CEInspectionRecord:
    # Find a similar document or resource which details an inspection of a given.... System/Facility/Installation
    id: str = "CE Inspection Number"
    #... tbd