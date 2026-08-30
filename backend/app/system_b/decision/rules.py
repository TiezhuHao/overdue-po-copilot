"""Explicit mappings from confirmed business sources, not cause predicates."""
from dataclasses import dataclass

from app.system_b.diagnosis.business_models import DiagnosisCode as D
from app.system_b.diagnosis.models import EvidenceKind as K
from app.system_b.decision.models import ActionCode as A, OwnerRole as O


@dataclass(frozen=True)
class DecisionRule:
    rule_id: str
    diagnosis_code: D
    diagnosis_rule_id: str
    diagnosis_rule_version: str
    priority: int
    source: str
    required_evidence: tuple[K, ...] = ()
    action_code: A | None = None
    owner_role: O | None = None
    consumption_based: bool = False
    version: str = "1.0.0"


DECISION_RULES = (
    DecisionRule("decision_trial", D.TRIAL, "business_trial", "1.0.0", 10,
                 "SCENARIO_RULES §6; AT-011", (K.MPM,), A.REQUEST_MPM_CONFIRMATION, O.MPM),
    DecisionRule("decision_customer_obsolescence", D.PROJECT_OBSOLESCENCE,
                 "business_customer_obsolescence", "2.0.0", 20, "SCENARIO_RULES §10; AT-038",
                 action_code=A.COMMUNICATE_CUSTOMER_OBSOLESCENCE, owner_role=O.CUSTOMER),
    DecisionRule("decision_demand_adjustment", D.DEMAND_ADJUSTMENT, "business_demand_adjustment", "2.0.0", 30,
                 "SCENARIO_RULES §2/§7; AT-037", (K.PO_CONSUMPTION,), consumption_based=True),
    DecisionRule("decision_after_sales", D.AFTER_SALES, "business_after_sales", "2.0.0", 40,
                 "DATA_CONTRACT DC-16; SCENARIO_RULES §11"),
    DecisionRule("decision_stockpile", D.STOCKPILE, "business_stockpile", "2.0.0", 50,
                 "SCENARIO_RULES §12; AT-037", (K.PO_CONSUMPTION,), consumption_based=True),
    DecisionRule("decision_internal_obsolescence", D.PROJECT_OBSOLESCENCE,
                 "business_internal_obsolescence", "2.0.0", 60, "SCENARIO_RULES §13; AT-042",
                 action_code=A.COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE, owner_role=O.BUSINESS_UNIT),
)
