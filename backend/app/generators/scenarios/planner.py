from __future__ import annotations

from collections import defaultdict
from random import Random
from typing import Any
from uuid import UUID

from app.core.ids import deterministic_uuid
from app.domain.procurement import is_overdue
from app.generators.master_data.world import MasterWorld
from app.generators.procurement.world import ProcurementWorld
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.scenarios.mappings import (
    MASS_PATTERNS,
    PATTERN_CAUSE,
    PATTERN_DEMAND_CHANGE,
    PATTERN_EXPECTED_ACTION,
    PATTERN_LIFECYCLE,
    PATTERN_RESPONSIBILITY,
    PATTERN_SUBTYPE,
)
from app.generators.scenarios.world import MaterialScenarioPlan, ScenarioWorld
from app.models.evaluation import ScenarioTruth


class ScenarioPlanningConflict(RuntimeError):
    pass


class ScenarioPlanner:
    def plan(
        self,
        dataset_version_id: UUID,
        snapshot_date: Any,
        scenario_signature: str,
        config: ScenarioGenerationConfig,
        master: MasterWorld,
        procurement: ProcurementWorld,
    ) -> ScenarioWorld:
        rng = Random(config.scenario_seed)
        lines = {row.po_line_id: row for row in procurement.po_lines}
        headers = {row.po_header_id: row for row in procurement.po_headers}
        organizations = {row.organization_id: row for row in master.organizations}
        materials = {row.material_id: row for row in master.materials}
        project_code = {row.project_id: row.project_code for row in master.projects}
        projects_by_material: dict[UUID, list[UUID]] = defaultdict(list)
        for row in master.material_projects:
            projects_by_material[row.material_id].append(row.project_id)
        for values in projects_by_material.values():
            values.sort(key=lambda value: project_code[value])

        overdue_schedules = [
            schedule
            for schedule in procurement.po_line_schedules
            if is_overdue(
                snapshot_date,
                lines[schedule.po_line_id].order_date,
                lines[schedule.po_line_id].material_lt_days_at_order,
            )
        ]
        schedules_by_material: dict[UUID, list[Any]] = defaultdict(list)
        for schedule in overdue_schedules:
            schedules_by_material[lines[schedule.po_line_id].material_id].append(schedule)

        sorted_projects = sorted(master.projects, key=lambda row: row.project_code)
        planned_project_state = {
            row.project_id: "MASS_PRODUCTION" if index % 2 == 0 else "EOL"
            for index, row in enumerate(sorted_projects)
        }
        trial_materials: list[UUID] = []
        mass_materials: list[UUID] = []
        for material_id in schedules_by_material:
            material = materials[material_id]
            organization = organizations[material.primary_inventory_organization_id]
            target = trial_materials if organization.inventory_organization_type == "TRIAL" else mass_materials
            target.append(material_id)
        trial_materials.sort(key=lambda value: materials[value].material_code)
        mass_materials.sort(key=lambda value: materials[value].material_code)
        rng.shuffle(mass_materials)

        assignments: dict[UUID, tuple[str, str | None, bool | None]] = {}
        mandatory: list[tuple[str, str | None, bool | None]] = []
        if config.require_all_patterns:
            mandatory.extend(
                [
                    ("DEMAND_REDUCTION", None, None),
                    ("DEMAND_DELAY", None, None),
                    ("DEMAND_MIXED", None, None),
                    ("CUSTOMER_SIDE_PROJECT_OBSOLESCENCE", "REDUCTION", None),
                    ("AFTER_SALES", None, False),
                    ("STOCKPILE", None, True),
                    ("INTERNAL_SIDE_PROJECT_OBSOLESCENCE", None, False),
                ]
            )
        if config.require_after_sales_stockpile_both:
            mandatory.append(("AFTER_SALES", None, True))
        if config.require_customer_demand_change_coverage:
            mandatory.extend(
                [
                    ("CUSTOMER_SIDE_PROJECT_OBSOLESCENCE", "DELAY", None),
                    ("CUSTOMER_SIDE_PROJECT_OBSOLESCENCE", "MIXED", None),
                ]
            )

        def supports(material_id: UUID, pattern: str) -> bool:
            required = PATTERN_LIFECYCLE.get(pattern)
            if required is None:
                return bool(projects_by_material[material_id])
            return any(
                planned_project_state[project_id] == required
                for project_id in projects_by_material[material_id]
            )

        remaining = list(mass_materials)
        for specification in mandatory:
            pattern = specification[0]
            material_id = next(
                (candidate for candidate in remaining if supports(candidate, pattern)),
                None,
            )
            if material_id is None:
                raise ScenarioPlanningConflict(
                    f"SCENARIO_PLANNING_CONFLICT: no material supports {pattern}"
                )
            assignments[material_id] = specification
            remaining.remove(material_id)

        patterns = list(MASS_PATTERNS)
        weights = [float(config.mass_pattern_weights[pattern]) for pattern in patterns]
        for material_id in remaining:
            compatible = [pattern for pattern in patterns if supports(material_id, pattern)]
            if not compatible:
                raise ScenarioPlanningConflict(
                    "SCENARIO_PLANNING_CONFLICT: no compatible pattern"
                )
            compatible_weights = [weights[patterns.index(pattern)] for pattern in compatible]
            # Coverage and lifecycle compatibility are hard constraints; weights are
            # preferences. Use a seeded uniform fallback if all eligible weights are zero.
            if not any(compatible_weights):
                compatible_weights = [1.0] * len(compatible)
            pattern = rng.choices(compatible, weights=compatible_weights, k=1)[0]
            assignments[material_id] = (pattern, None, None)

        plans: dict[UUID, MaterialScenarioPlan] = {}
        requirements: dict[UUID, str] = {}

        def choose_causal(material_id: UUID, lifecycle: str | None) -> tuple[UUID, str]:
            candidates = list(projects_by_material[material_id])
            rng.shuffle(candidates)
            if lifecycle is not None:
                candidates = [
                    project_id
                    for project_id in candidates
                    if planned_project_state[project_id] == lifecycle
                ]
            if not candidates:
                raise ScenarioPlanningConflict("SCENARIO_PLANNING_CONFLICT: no causal project")
            references = [
                lines[schedule.po_line_id].po_reference_project_id
                for schedule in schedules_by_material[material_id]
            ]
            candidates.sort(
                key=lambda project_id: -sum(reference != project_id for reference in references)
            )
            causal_project_id = candidates[0]
            return causal_project_id, planned_project_state[causal_project_id]

        for material_id in trial_materials:
            causal_project_id, lifecycle = choose_causal(material_id, None)
            requirements[causal_project_id] = lifecycle
            plans[material_id] = MaterialScenarioPlan(
                material_id=material_id,
                scenario_pattern="TRIAL",
                true_cause="TRIAL",
                true_cause_subtype="NONE",
                causal_project_id=causal_project_id,
                demand_change_type="NONE",
                lifecycle_state=lifecycle,
                stockpile_flag=bool(rng.getrandbits(1)),
                responsibility_type="MPM",
                expected_action="待MPM确认处理",
            )

        for material_id in mass_materials:
            pattern, demand_override, stockpile_override = assignments[material_id]
            lifecycle_requirement = PATTERN_LIFECYCLE.get(pattern)
            causal_project_id, lifecycle = choose_causal(material_id, lifecycle_requirement)
            if causal_project_id in requirements and requirements[causal_project_id] != lifecycle:
                raise ScenarioPlanningConflict("SCENARIO_PLANNING_CONFLICT: lifecycle conflict")
            requirements[causal_project_id] = lifecycle
            if pattern == "CUSTOMER_SIDE_PROJECT_OBSOLESCENCE":
                demand_change = demand_override or rng.choice(("REDUCTION", "DELAY", "MIXED"))
            else:
                demand_change = PATTERN_DEMAND_CHANGE[pattern]
            if pattern == "STOCKPILE":
                stockpile_flag = True
            elif pattern == "INTERNAL_SIDE_PROJECT_OBSOLESCENCE":
                stockpile_flag = False
            elif pattern == "AFTER_SALES" and stockpile_override is not None:
                stockpile_flag = stockpile_override
            else:
                stockpile_flag = bool(rng.getrandbits(1))
            plans[material_id] = MaterialScenarioPlan(
                material_id=material_id,
                scenario_pattern=pattern,
                true_cause=PATTERN_CAUSE[pattern],
                true_cause_subtype=PATTERN_SUBTYPE[pattern],
                causal_project_id=causal_project_id,
                demand_change_type=demand_change,
                lifecycle_state=lifecycle,
                stockpile_flag=stockpile_flag,
                responsibility_type=PATTERN_RESPONSIBILITY.get(pattern),
                expected_action=PATTERN_EXPECTED_ACTION.get(pattern),
            )

        truth_rows: list[ScenarioTruth] = []
        for schedule in overdue_schedules:
            line = lines[schedule.po_line_id]
            plan = plans[line.material_id]
            truth_rows.append(
                ScenarioTruth(
                    dataset_version_id=dataset_version_id,
                    scenario_truth_id=deterministic_uuid(
                        scenario_signature, "scenario_truth", schedule.po_line_schedule_id
                    ),
                    po_line_schedule_id=schedule.po_line_schedule_id,
                    po_line_id=line.po_line_id,
                    scenario_pattern=plan.scenario_pattern,
                    true_cause=plan.true_cause,
                    true_cause_subtype=plan.true_cause_subtype,
                    causal_project_id=plan.causal_project_id,
                    demand_change_type=plan.demand_change_type,
                    lifecycle_state=plan.lifecycle_state,
                    stockpile_flag=plan.stockpile_flag,
                    responsibility_type=plan.responsibility_type,
                    expected_action=plan.expected_action,
                )
            )
        return ScenarioWorld(truth_rows, plans, requirements)
