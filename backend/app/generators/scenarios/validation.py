from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from app.domain.procurement import is_overdue
from app.generators.master_data.world import MasterWorld
from app.generators.procurement.world import ProcurementWorld
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.scenarios.mappings import (
    PATTERNS,
    PATTERN_CAUSE,
    PATTERN_DEMAND_CHANGE,
    PATTERN_EXPECTED_ACTION,
    PATTERN_LIFECYCLE,
    PATTERN_RESPONSIBILITY,
    PATTERN_SUBTYPE,
)
from app.generators.scenarios.world import ScenarioWorld
from app.models.platform import PoHeader, PoLine, PoLineSchedule


class ScenarioWorldValidationError(ValueError):
    pass


class ScenarioWorldValidator:
    def validate(
        self,
        world: ScenarioWorld,
        master: MasterWorld,
        procurement: ProcurementWorld,
        dataset_version_id: Any,
        snapshot_date: Any,
        config: ScenarioGenerationConfig,
    ) -> None:
        errors: list[str] = []
        lines = {row.po_line_id: row for row in procurement.po_lines}
        schedules = {
            row.po_line_schedule_id: row for row in procurement.po_line_schedules
        }
        headers = {row.po_header_id: row for row in procurement.po_headers}
        organizations = {row.organization_id: row for row in master.organizations}
        materials = {row.material_id: row for row in master.materials}
        material_projects: dict[Any, set[Any]] = defaultdict(set)
        for row in master.material_projects:
            material_projects[row.material_id].add(row.project_id)
        overdue_schedule_ids = {
            schedule.po_line_schedule_id
            for schedule in procurement.po_line_schedules
            if is_overdue(
                snapshot_date,
                lines[schedule.po_line_id].order_date,
                lines[schedule.po_line_id].material_lt_days_at_order,
            )
        }
        truth_schedule_ids = [row.po_line_schedule_id for row in world.scenario_truth_rows]
        if set(truth_schedule_ids) != overdue_schedule_ids:
            errors.append("Truth must exist exactly for overdue schedules")
        if len(truth_schedule_ids) != len(set(truth_schedule_ids)):
            errors.append("an overdue schedule has more than one Truth")

        project_states: dict[Any, set[str]] = defaultdict(set)
        material_truth_values: dict[Any, set[tuple[Any, ...]]] = defaultdict(set)
        nontrial_count = 0
        mismatch_count = 0
        for truth in world.scenario_truth_rows:
            if truth.dataset_version_id != dataset_version_id:
                errors.append("Truth contains a cross-dataset row")
            line = lines.get(truth.po_line_id)
            if line is None:
                errors.append("Truth parent line does not exist")
                continue
            schedule = schedules.get(truth.po_line_schedule_id)
            if schedule is None or schedule.po_line_id != truth.po_line_id:
                errors.append("Truth schedule lineage is invalid")
            if truth.causal_project_id not in material_projects[line.material_id]:
                errors.append("causal project is not related to material")
            header = headers[line.po_header_id]
            inventory_type = organizations[
                header.inventory_organization_id
            ].inventory_organization_type
            if inventory_type == "TRIAL" and truth.scenario_pattern != "TRIAL":
                errors.append("TRIAL inventory organization lost priority")
            if inventory_type == "MASS_PRODUCTION" and truth.scenario_pattern == "TRIAL":
                errors.append("mass-production Truth cannot use TRIAL pattern")
            if truth.scenario_pattern not in PATTERNS:
                errors.append("unknown scenario pattern")
            elif truth.true_cause != PATTERN_CAUSE[truth.scenario_pattern]:
                errors.append("Pattern to Cause mapping is invalid")
            if truth.true_cause_subtype != PATTERN_SUBTYPE[truth.scenario_pattern]:
                errors.append("Pattern subtype mapping is invalid")
            expected_demand = PATTERN_DEMAND_CHANGE.get(truth.scenario_pattern)
            if expected_demand is not None and truth.demand_change_type != expected_demand:
                errors.append("Demand Change mapping is invalid")
            expected_lifecycle = PATTERN_LIFECYCLE.get(truth.scenario_pattern)
            if expected_lifecycle and truth.lifecycle_state != expected_lifecycle:
                errors.append("Lifecycle mapping is invalid")
            if truth.responsibility_type != PATTERN_RESPONSIBILITY.get(truth.scenario_pattern):
                errors.append("Responsibility mapping is invalid")
            if truth.expected_action != PATTERN_EXPECTED_ACTION.get(truth.scenario_pattern):
                errors.append("Expected action mapping is invalid")
            if truth.scenario_pattern == "STOCKPILE" and not truth.stockpile_flag:
                errors.append("STOCKPILE requires stockpile_flag=true")
            if truth.scenario_pattern == "INTERNAL_SIDE_PROJECT_OBSOLESCENCE" and truth.stockpile_flag:
                errors.append("INTERNAL_SIDE requires stockpile_flag=false")
            project_states[truth.causal_project_id].add(truth.lifecycle_state)
            material_truth_values[line.material_id].add(
                (
                    truth.scenario_pattern,
                    truth.causal_project_id,
                    truth.demand_change_type,
                    truth.lifecycle_state,
                    truth.stockpile_flag,
                )
            )
            if truth.scenario_pattern != "TRIAL":
                nontrial_count += 1
                mismatch_count += line.po_reference_project_id != truth.causal_project_id

        if any(len(states) != 1 for states in project_states.values()):
            errors.append("a causal project has conflicting lifecycle requirements")
        if any(len(values) != 1 for values in material_truth_values.values()):
            errors.append("one material has inconsistent Scenario Plans")
        pattern_counts = Counter(row.scenario_pattern for row in world.scenario_truth_rows)
        if config.require_all_patterns and set(pattern_counts) != set(PATTERNS):
            errors.append("default scenario coverage does not include all eight patterns")
        if config.require_after_sales_stockpile_both:
            after_flags = {
                row.stockpile_flag
                for row in world.scenario_truth_rows
                if row.scenario_pattern == "AFTER_SALES"
            }
            if after_flags != {True, False}:
                errors.append("After-sales must cover stockpile true and false")
        if config.require_customer_demand_change_coverage:
            customer_changes = {
                row.demand_change_type
                for row in world.scenario_truth_rows
                if row.scenario_pattern == "CUSTOMER_SIDE_PROJECT_OBSOLESCENCE"
            }
            if customer_changes != {"REDUCTION", "DELAY", "MIXED"}:
                errors.append("customer-side scenario lacks demand-change coverage")
        if nontrial_count:
            ratio = Decimal(mismatch_count) / Decimal(nontrial_count)
            if ratio < config.reference_causal_mismatch_min_ratio:
                errors.append("reference/causal mismatch coverage is below configured minimum")

        platform_truth_fields = {
            "true_cause",
            "true_cause_subtype",
            "causal_project_id",
            "demand_change_type",
            "expected_action",
        }
        platform_columns = {
            column.key for model in (PoHeader, PoLine, PoLineSchedule) for column in model.__table__.columns
        }
        if platform_columns & platform_truth_fields:
            errors.append("hidden Truth fields leaked into platform procurement tables")
        if errors:
            raise ScenarioWorldValidationError("; ".join(dict.fromkeys(errors)))
