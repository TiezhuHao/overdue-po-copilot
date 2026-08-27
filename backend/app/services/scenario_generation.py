from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.procurement import is_overdue
from app.generators.master_data.world import MasterWorld
from app.generators.procurement.world import ProcurementWorld
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.scenarios.planner import ScenarioPlanner
from app.generators.scenarios.signature import scenario_generation_signature
from app.generators.scenarios.validation import ScenarioWorldValidator
from app.generators.scenarios.world import MaterialScenarioPlan, ScenarioWorld
from app.models.evaluation import ScenarioTruth
from app.models.platform import DatasetVersion, PoHeader, PoLine, PoLineSchedule
from app.services.dataset_generation import COLLECTION_MODELS


class ScenarioGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScenarioGenerationResult:
    dataset_version_id: UUID
    dataset_version_name: str
    scenario_signature: str
    scenario_content_hash: str
    overdue_schedule_count: int
    validation_status: str
    reused: bool
    world: ScenarioWorld
    master: MasterWorld
    procurement: ProcurementWorld
    snapshot_date: Any


class ScenarioGenerationService:
    def __init__(
        self,
        session: Session,
        planner: ScenarioPlanner | None = None,
        validator: ScenarioWorldValidator | None = None,
    ) -> None:
        self.session = session
        self.planner = planner or ScenarioPlanner()
        self.validator = validator or ScenarioWorldValidator()

    def _load_master(self, dataset_version_id: UUID) -> MasterWorld:
        return MasterWorld(
            **{
                name: list(
                    self.session.scalars(
                        select(model).where(model.dataset_version_id == dataset_version_id)
                    )
                )
                for name, model in COLLECTION_MODELS
            }
        )

    def _load_procurement(self, dataset_version_id: UUID) -> ProcurementWorld:
        return ProcurementWorld(
            po_headers=list(self.session.scalars(select(PoHeader).where(PoHeader.dataset_version_id == dataset_version_id))),
            po_lines=list(self.session.scalars(select(PoLine).where(PoLine.dataset_version_id == dataset_version_id))),
            po_line_schedules=list(self.session.scalars(select(PoLineSchedule).where(PoLineSchedule.dataset_version_id == dataset_version_id))),
        )

    @staticmethod
    def _reconstruct_world(
        truth_rows: list[ScenarioTruth], procurement: ProcurementWorld
    ) -> ScenarioWorld:
        lines = {row.po_line_id: row for row in procurement.po_lines}
        plans: dict[UUID, MaterialScenarioPlan] = {}
        requirements: dict[UUID, str] = {}
        for truth in truth_rows:
            material_id = lines[truth.po_line_id].material_id
            plans[material_id] = MaterialScenarioPlan(
                material_id=material_id,
                scenario_pattern=truth.scenario_pattern,
                true_cause=truth.true_cause,
                true_cause_subtype=truth.true_cause_subtype,
                causal_project_id=truth.causal_project_id,
                demand_change_type=truth.demand_change_type,
                lifecycle_state=truth.lifecycle_state,
                stockpile_flag=truth.stockpile_flag,
                responsibility_type=truth.responsibility_type,
                expected_action=truth.expected_action,
            )
            requirements[truth.causal_project_id] = truth.lifecycle_state
        return ScenarioWorld(truth_rows, plans, requirements)

    def generate(
        self,
        dataset_version_id: UUID,
        config: ScenarioGenerationConfig,
    ) -> ScenarioGenerationResult:
        reused = False
        with self.session.begin():
            dataset = self.session.scalar(
                select(DatasetVersion)
                .where(DatasetVersion.dataset_version_id == dataset_version_id)
                .with_for_update()
            )
            if dataset is None:
                raise ScenarioGenerationError("DATASET_NOT_FOUND")
            if dataset.status != "GENERATING":
                raise ScenarioGenerationError("DATASET_NOT_GENERATING")
            master = self._load_master(dataset_version_id)
            if any(not getattr(master, name) for name in MasterWorld.COLLECTION_NAMES):
                raise ScenarioGenerationError("INCOMPLETE_MASTER_WORLD")
            procurement = self._load_procurement(dataset_version_id)
            if any(not getattr(procurement, name) for name in ProcurementWorld.COLLECTION_NAMES):
                raise ScenarioGenerationError("INCOMPLETE_PROCUREMENT_WORLD")
            lines = {row.po_line_id: row for row in procurement.po_lines}
            overdue_count = sum(
                is_overdue(
                    dataset.snapshot_date,
                    lines[row.po_line_id].order_date,
                    lines[row.po_line_id].material_lt_days_at_order,
                )
                for row in procurement.po_line_schedules
            )
            signature = scenario_generation_signature(
                dataset.generation_signature,
                procurement.procurement_facts_hash(),
                config,
            )
            existing_count = self.session.scalar(
                select(func.count()).select_from(ScenarioTruth).where(
                    ScenarioTruth.dataset_version_id == dataset_version_id
                )
            )
            if existing_count == 0:
                world = self.planner.plan(
                    dataset_version_id,
                    dataset.snapshot_date,
                    signature,
                    config,
                    master,
                    procurement,
                )
                self.validator.validate(
                    world,
                    master,
                    procurement,
                    dataset_version_id,
                    dataset.snapshot_date,
                    config,
                )
                self.session.add_all(world.scenario_truth_rows)
                self.session.flush()
            elif existing_count != overdue_count:
                raise ScenarioGenerationError("INCOMPLETE_SCENARIO_WORLD")
            else:
                truth_rows = list(
                    self.session.scalars(
                        select(ScenarioTruth).where(
                            ScenarioTruth.dataset_version_id == dataset_version_id
                        )
                    )
                )
                world = self._reconstruct_world(truth_rows, procurement)
                self.validator.validate(
                    world,
                    master,
                    procurement,
                    dataset_version_id,
                    dataset.snapshot_date,
                    config,
                )
                expected = self.planner.plan(
                    dataset_version_id,
                    dataset.snapshot_date,
                    signature,
                    config,
                    master,
                    procurement,
                )
                if world.scenario_content_hash(signature) != expected.scenario_content_hash(
                    signature
                ):
                    raise ScenarioGenerationError("SCENARIO_CONFIG_CONFLICT")
                reused = True
            return ScenarioGenerationResult(
                dataset_version_id=dataset_version_id,
                dataset_version_name=dataset.version_name,
                scenario_signature=signature,
                scenario_content_hash=world.scenario_content_hash(signature),
                overdue_schedule_count=overdue_count,
                validation_status="PASS",
                reused=reused,
                world=world,
                master=master,
                procurement=procurement,
                snapshot_date=dataset.snapshot_date,
            )
