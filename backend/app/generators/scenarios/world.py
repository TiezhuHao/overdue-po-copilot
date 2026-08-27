from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.inspection import inspect

from app.generators.signature import canonical_json, content_hash
from app.models.evaluation import ScenarioTruth


@dataclass(frozen=True)
class MaterialScenarioPlan:
    material_id: UUID
    scenario_pattern: str
    true_cause: str
    true_cause_subtype: str
    causal_project_id: UUID
    demand_change_type: str
    lifecycle_state: str
    stockpile_flag: bool
    responsibility_type: str | None
    expected_action: str | None


@dataclass
class ScenarioWorld:
    scenario_truth_rows: list[ScenarioTruth] = field(default_factory=list)
    material_scenario_plans: dict[UUID, MaterialScenarioPlan] = field(default_factory=dict)
    project_lifecycle_requirements: dict[UUID, str] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        return {
            "scenario_truth_rows": len(self.scenario_truth_rows),
            "material_scenario_plans": len(self.material_scenario_plans),
            "project_lifecycle_requirements": len(self.project_lifecycle_requirements),
        }

    @staticmethod
    def _truth_payload(row: ScenarioTruth) -> dict[str, Any]:
        mapper = inspect(type(row))
        return {
            column.key: getattr(row, column.key)
            for column in mapper.columns
            if column.key != "created_at"
        }

    def scenario_content_hash(self, scenario_signature: str) -> str:
        return content_hash(
            {
                "scenario_signature": scenario_signature,
                "scenario_truth_rows": sorted(
                    [self._truth_payload(row) for row in self.scenario_truth_rows],
                    key=canonical_json,
                ),
                "material_scenario_plans": sorted(
                    [asdict(plan) for plan in self.material_scenario_plans.values()],
                    key=canonical_json,
                ),
                "project_lifecycle_requirements": {
                    str(key): value
                    for key, value in sorted(
                        self.project_lifecycle_requirements.items(), key=lambda item: str(item[0])
                    )
                },
            }
        )
