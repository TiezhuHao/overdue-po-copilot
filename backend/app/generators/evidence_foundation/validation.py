import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

from app.generators.evidence_foundation.calendar import active, add_months, days, demand_horizon, material_anchors, source_cycles
from app.generators.evidence_foundation.world import DemandObservationIndex
from app.models.platform.evidence_foundation import EVIDENCE_MODELS


class EvidenceFoundationValidationError(ValueError):
    pass


def shape_metrics(before, after, start, scenario_config):
    near_end = add_months(start, scenario_config.delay_near_term_months)
    end = add_months(start, scenario_config.comparison_months)
    near_before = sum((qty for day, qty in before.items() if start <= day < near_end), Decimal(0))
    far_before = sum((qty for day, qty in before.items() if near_end <= day < end), Decimal(0))
    near_after = sum((qty for day, qty in after.items() if start <= day < near_end), Decimal(0))
    far_after = sum((qty for day, qty in after.items() if near_end <= day < end), Decimal(0))
    total = near_before + far_before
    retention = (near_after + far_after) / total if total else Decimal(1)
    near_drop = 1 - near_after / near_before if near_before else Decimal(0)
    shift = max(far_after - far_before, Decimal(0)) / near_before if near_before else Decimal(0)
    return {"drop": 1 - retention, "retention": retention, "near_drop": near_drop, "shift": shift,
            "strength": max(1 - retention, Decimal(0)) + max(near_drop, Decimal(0)) + shift}


def future_statistics(values, snapshot, reference):
    week_start = snapshot + timedelta(days=(-snapshot.weekday()) % 7)
    week_totals = [sum((values[week_start + timedelta(days=index * 7 + day)] for day in range(7)), Decimal(0)) for index in range(13)]
    month_start = add_months(snapshot.replace(day=1), 1)
    month_totals = [sum((qty for day, qty in values.items() if add_months(month_start, index) <= day < add_months(month_start, index + 1)), Decimal(0)) for index in range(6)]
    return {"weeks": sum(qty > 0 for qty in week_totals), "months": sum(qty > 0 for qty in month_totals),
            "level_ratio": sum(week_totals) / (Decimal(91) * reference)}


def has_after_sales_quantities(stats, config):
    return (stats["weeks"] >= config.after_sales_min_nonzero_weeks
            and stats["months"] >= config.after_sales_min_nonzero_months
            and config.after_sales_level_ratio_min <= stats["level_ratio"] <= config.after_sales_level_ratio_max)


class EvidenceFoundationValidator:
    def validate(self, world, master, procurement, scenario, dataset_id, snapshot, config, scenario_config):
        errors = []

        def require(condition, message):
            if not condition:
                errors.append(message)

        all_rows = list(master.all_records())
        for name in world.COLLECTION_NAMES:
            all_rows.extend(getattr(world, name))
        reference_keys = defaultdict(set)
        for row in all_rows:
            table = row.__table__
            reference_keys[table.fullname].add(tuple(getattr(row, column.key) for column in table.primary_key))
        point_keys = {(row.dataset_version_id, row.demand_signal_id, row.demand_date) for row in world.demand_signal_points}
        for model in EVIDENCE_MODELS:
            rows = getattr(world, model.__tablename__)
            for row in rows:
                require(row.dataset_version_id == dataset_id, "cross-dataset evidence row")
                for constraint in model.__table__.constraints:
                    if not isinstance(constraint, ForeignKeyConstraint):
                        continue
                    target = constraint.elements[0].column.table.fullname
                    local = tuple(getattr(row, element.parent.key) for element in constraint.elements)
                    if any(value is None for value in local):
                        continue
                    valid = ({(dataset_id,)} if target == "platform.dataset_versions" else
                             point_keys if target == "platform.demand_signal_points" else reference_keys[target])
                    require(local in valid, "invalid dataset-scoped evidence FK")
            unique_sets = [model.__table__.primary_key] + [c for c in model.__table__.constraints if isinstance(c, UniqueConstraint)]
            for constraint in unique_sets:
                keys = [tuple(getattr(row, column.key) for column in constraint.columns) for row in rows]
                require(len(keys) == len(set(keys)), "duplicate evidence key")
        if errors:
            raise EvidenceFoundationValidationError("; ".join(sorted(set(errors))))

        histories = defaultdict(list)
        snapshot_states = {}
        for row in world.project_lifecycle_history:
            histories[row.project_id].append(row)
            require(row.lifecycle_stage in {"NPI", "MASS_PRODUCTION", "EOL"}, "invalid lifecycle stage")
            require(row.effective_to is None or row.effective_from < row.effective_to, "invalid lifecycle period")
        rank = {"NPI": 0, "MASS_PRODUCTION": 1, "EOL": 2}
        for project in master.projects:
            records = sorted(histories[project.project_id], key=lambda row: row.effective_from)
            current = [row for row in records if active(row, snapshot)]
            require(len(current) == 1, "project must have exactly one snapshot lifecycle")
            if current:
                snapshot_states[project.project_id] = current[0].lifecycle_stage
            for first, second in zip(records, records[1:]):
                require(first.effective_to == second.effective_from, "lifecycle overlap or gap")
                require(rank.get(first.lifecycle_stage, -1) < rank.get(second.lifecycle_stage, -1), "lifecycle chronology reversed")
        for project_id, required in scenario.project_lifecycle_requirements.items():
            require(snapshot_states.get(project_id) == required, "scenario lifecycle requirement violated")

        organizations = {row.organization_id: row for row in master.organizations}
        materials = {row.material_id: row for row in master.materials}
        pairs = {(row.material_id, row.project_id) for row in master.material_projects}
        configs = {row.product_config_id: row for row in world.product_configs}
        config_projects = {row.project_id for row in world.product_configs if row.product_config_status == "ACTIVE" and active(row, snapshot)}
        require(config_projects == {row.project_id for row in master.projects}, "project configuration missing")
        covered = set()
        for row in world.product_config_materials:
            pair = (row.material_id, configs[row.product_config_id].project_id)
            require(pair in pairs, "config material does not belong to project")
            if active(configs[row.product_config_id], snapshot):
                covered.add(pair)
        require(covered == pairs, "material-project configuration evidence missing")
        for row in world.product_configs:
            unit = organizations[row.business_unit_id]
            department = organizations[row.planning_department_id]
            require(unit.organization_type == "BUSINESS_UNIT" and active(unit, snapshot), "invalid business unit")
            require(department.organization_type == "PLANNING_DEPARTMENT" and department.parent_organization_id == row.business_unit_id and active(department, snapshot), "inconsistent planning department")
            units = Counter(organizations[materials[mid].primary_inventory_organization_id].parent_organization_id for mid, pid in pairs if pid == row.project_id)
            expected_unit = sorted(units, key=lambda key: (-units[key], str(key)))[0]
            require(row.business_unit_id == expected_unit, "config organization inconsistent with project materials")
            customers = [rel for rel in master.project_customers if rel.project_id == row.project_id and active(rel, snapshot)]
            primary = {rel.customer_id for rel in customers if rel.relationship_type == "PRIMARY"}
            require(row.customer_id in (primary or {rel.customer_id for rel in customers}), "config customer inconsistent with project")
            require(any(rel.employee_id == row.research_representative_employee_id and rel.role_type == "RESEARCH_REPRESENTATIVE" and active(rel, snapshot) for rel in master.employee_role_assignments), "invalid research representative")
            require(row.effective_to is None or row.effective_to > row.effective_from, "invalid product config period")

        start, end = demand_horizon(snapshot, scenario, procurement, config)
        expected_dates = set(days(start, end))
        signals = {(row.material_id, row.project_id): row for row in world.demand_signals}
        require(set(signals) == pairs, "material-project demand signal missing")
        for row in world.demand_signals:
            require(row.organization_id == materials[row.material_id].primary_inventory_organization_id, "demand primary organization mismatch")
            require(row.observed_from == start and row.signal_kind == "PLANNED_DEMAND", "invalid demand observation header")
            require(bool(re.fullmatch(r"[a-f0-9]{64}", row.scenario_generation_key)), "generation lineage key is not opaque")
            require(row.reference_daily_qty > 0, "invalid reference quantity")
        require(all(row.demand_qty >= 0 for row in world.demand_signal_points + world.demand_signal_revisions), "negative demand quantity")
        observation = DemandObservationIndex(world)
        for row in world.demand_signals:
            require(set(observation.initial[row.demand_signal_id]) == expected_dates, "demand daily horizon incomplete")
        require(all(start <= row.observed_on <= snapshot for row in world.demand_signal_revisions), "revision observation outside history")
        forbidden = {"true_cause", "scenario_pattern", "causal_project_id", "demand_change_type", "responsibility_type", "expected_action", "true_cause_subtype"}
        require(not any(forbidden.intersection(model.__table__.columns.keys()) for model in EVIDENCE_MODELS), "platform truth leakage")
        if errors:
            raise EvidenceFoundationValidationError("; ".join(sorted(set(errors))))

        anchors = material_anchors(scenario, procurement)
        for material_id, plan in scenario.material_scenario_plans.items():
            target = signals[(material_id, plan.causal_project_id)]
            competitors = [row for (mid, pid), row in signals.items() if mid == material_id and pid != plan.causal_project_id]
            for before_date, after_date, window_start in source_cycles(anchors[material_id]):
                before = observation.observe(target.demand_signal_id, before_date)
                after = observation.observe(target.demand_signal_id, after_date)
                metrics = shape_metrics(before, after, window_start, scenario_config)
                if plan.demand_change_type == "REDUCTION":
                    require(metrics["drop"] >= scenario_config.reduction_total_drop_ratio and metrics["shift"] < scenario_config.delay_shift_share_min, "reduction evidence invalid")
                elif plan.demand_change_type == "DELAY":
                    require(metrics["near_drop"] >= scenario_config.delay_near_term_drop_ratio and metrics["shift"] >= scenario_config.delay_shift_share_min and scenario_config.delay_total_retention_lower <= metrics["retention"] <= scenario_config.delay_total_retention_upper, "delay evidence invalid")
                elif plan.demand_change_type == "MIXED":
                    require(metrics["drop"] >= scenario_config.mixed_total_drop_ratio and metrics["shift"] >= scenario_config.mixed_shift_share_min, "mixed evidence invalid")
                else:
                    require(before == after, "unexpected demand adjustment in stable scenario")
                if plan.demand_change_type != "NONE":
                    for other in competitors:
                        noise = shape_metrics(observation.observe(other.demand_signal_id, before_date), observation.observe(other.demand_signal_id, after_date), window_start, scenario_config)
                        require(metrics["strength"] > noise["strength"], "causal evidence not stronger than noise")
            stats = future_statistics(observation.observe(target.demand_signal_id, snapshot), snapshot, target.reference_daily_qty)
            if plan.scenario_pattern == "AFTER_SALES":
                require(snapshot_states[target.project_id] == "EOL" and has_after_sales_quantities(stats, scenario_config), "after-sales quantities or lifecycle invalid")
            elif plan.scenario_pattern in {"STOCKPILE", "INTERNAL_SIDE_PROJECT_OBSOLESCENCE", "CUSTOMER_SIDE_PROJECT_OBSOLESCENCE"}:
                require(not has_after_sales_quantities(stats, scenario_config), "after-sales negative evidence missing")
            if plan.scenario_pattern in {"AFTER_SALES", "STOCKPILE", "INTERNAL_SIDE_PROJECT_OBSOLESCENCE"}:
                for other in competitors:
                    other_stats = future_statistics(observation.observe(other.demand_signal_id, snapshot), snapshot, other.reference_daily_qty)
                    require(stats["level_ratio"] < other_stats["level_ratio"], "stable target evidence not distinct from other projects")
        if errors:
            raise EvidenceFoundationValidationError("; ".join(sorted(set(errors))))
