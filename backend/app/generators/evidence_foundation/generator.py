from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from random import Random

from app.core.ids import deterministic_uuid
from app.generators.evidence_foundation.calendar import active, add_months, days, demand_horizon, material_anchors, source_cycles
from app.generators.evidence_foundation.world import EvidenceFoundationWorld
from app.generators.signature import content_hash
from app.models.platform.evidence_foundation import (
    DemandSignal, DemandSignalPoint, DemandSignalRevision, ProductConfig,
    ProductConfigMaterial, ProjectLifecycleHistory,
)

Q = Decimal("0.0001")


def quantize(value):
    return value.quantize(Q, rounding=ROUND_HALF_UP)


class EvidenceFoundationGenerationError(ValueError):
    pass


def changed_quantities(baseline, window_start, change, scenario_config, config):
    """Create numeric revision observations; classification labels stay generator-only."""
    revised = dict(baseline)
    near_end = add_months(window_start, scenario_config.delay_near_term_months)
    end = add_months(window_start, scenario_config.comparison_months)
    near = [day for day in baseline if window_start <= day < near_end]
    far = [day for day in baseline if near_end <= day < end]
    near_total = sum((baseline[day] for day in near), Decimal(0))
    total = near_total + sum((baseline[day] for day in far), Decimal(0))
    if not near or not far or near_total <= 0:
        raise EvidenceFoundationGenerationError("INCOMPATIBLE_EVIDENCE_CONFIG: empty comparison window")
    if change == "REDUCTION":
        if config.reduction_drop_ratio <= scenario_config.reduction_total_drop_ratio:
            raise EvidenceFoundationGenerationError("INCOMPATIBLE_EVIDENCE_CONFIG: reduction margin")
        for day in revised:
            if day >= window_start:
                revised[day] = quantize(baseline[day] * (1 - config.reduction_drop_ratio))
        return revised
    if change == "DELAY":
        if not (scenario_config.delay_total_retention_lower <= 1 <= scenario_config.delay_total_retention_upper):
            raise EvidenceFoundationGenerationError("INCOMPATIBLE_EVIDENCE_CONFIG: delay retention")
        moved = quantize(near_total * config.delay_near_shift_ratio)
        lost = Decimal(0)
    elif change == "MIXED":
        moved = quantize(near_total * config.mixed_near_shift_ratio)
        lost = quantize(total * config.mixed_drop_ratio)
        # Net reduction remains visible after the comparison window too.
        for day in revised:
            if day >= end:
                revised[day] = quantize(baseline[day] * (1 - config.mixed_drop_ratio))
    else:
        raise EvidenceFoundationGenerationError("unsupported generator demand shape")
    if moved + lost >= near_total:
        raise EvidenceFoundationGenerationError("INCOMPATIBLE_EVIDENCE_CONFIG: removal exceeds near-term demand")
    remaining = near_total - moved - lost
    for day in near:
        revised[day] = quantize(baseline[day] * remaining / near_total)
    revised[near[-1]] += remaining - sum(revised[day] for day in near)
    increment = quantize(moved / len(far))
    for day in far:
        revised[day] = baseline[day] + increment
    revised[far[-1]] += moved - increment * len(far)
    return revised


class EvidenceFoundationGenerator:
    def generate(self, dataset_id, snapshot, signature, config, scenario_config, master, procurement, scenario):
        world = EvidenceFoundationWorld()
        start, end = demand_horizon(snapshot, scenario, procurement, config)
        rng = Random(config.evidence_seed)
        projects = sorted(master.projects, key=lambda row: row.project_code)
        materials = {row.material_id: row for row in master.materials}
        organizations = {row.organization_id: row for row in master.organizations}
        pairs = sorted(
            {(row.material_id, row.project_id) for row in master.material_projects},
            key=lambda pair: (materials[pair[0]].material_code, str(pair[1])),
        )
        project_materials = defaultdict(list)
        for material_id, project_id in pairs:
            project_materials[project_id].append(material_id)
        role_pool = sorted(
            [row for row in master.employee_role_assignments if row.role_type == "RESEARCH_REPRESENTATIVE" and active(row, snapshot)],
            key=lambda row: str(row.employee_id),
        )
        if not role_pool:
            raise EvidenceFoundationGenerationError("INCOMPLETE_MASTER_WORLD: research representative role missing")

        def uid(kind, key):
            return deterministic_uuid(signature, kind, key)

        for index, project in enumerate(projects):
            stage = scenario.project_lifecycle_requirements.get(project.project_id)
            if stage is None:
                stage = rng.choice(("NPI", "MASS_PRODUCTION", "EOL"))
            history_start = start - timedelta(days=365)
            mass_start = start - timedelta(days=180)
            eol_start = snapshot - timedelta(days=30 + index)
            stages = [("NPI", history_start, None)]
            if stage in {"MASS_PRODUCTION", "EOL"}:
                stages = [("NPI", history_start, mass_start), ("MASS_PRODUCTION", mass_start, None)]
            if stage == "EOL":
                stages[-1] = ("MASS_PRODUCTION", mass_start, eol_start)
                stages.append(("EOL", eol_start, None))
            for label, effective_from, effective_to in stages:
                world.project_lifecycle_history.append(ProjectLifecycleHistory(
                    dataset_version_id=dataset_id, project_lifecycle_id=uid("project_lifecycle", f"{project.project_id}:{label}"),
                    project_id=project.project_id, lifecycle_stage=label,
                    effective_from=effective_from, effective_to=effective_to,
                ))
            customers = sorted(
                [row for row in master.project_customers if row.project_id == project.project_id and active(row, snapshot)],
                key=lambda row: (row.relationship_type != "PRIMARY", str(row.customer_id)),
            )
            if not customers:
                raise EvidenceFoundationGenerationError("INCOMPLETE_MASTER_WORLD: project customer missing")
            # Project has no organization column. Derive one consistent assignment
            # from the existing related-material inventory organization hierarchy.
            unit_counts = Counter(
                organizations[materials[mid].primary_inventory_organization_id].parent_organization_id
                for mid in project_materials[project.project_id]
            )
            unit_id = sorted(unit_counts, key=lambda key: (-unit_counts[key], str(key)))[0]
            departments = sorted(
                [row for row in master.organizations if row.organization_type == "PLANNING_DEPARTMENT" and row.parent_organization_id == unit_id and active(row, snapshot)],
                key=lambda row: row.organization_code,
            )
            if not departments:
                raise EvidenceFoundationGenerationError("INCOMPLETE_MASTER_WORLD: planning department missing")
            representative = role_pool[index % len(role_pool)]
            effective_from = max(start, representative.effective_from, customers[0].effective_from)
            for ordinal in range(1, config.configs_per_project + 1):
                config_id = uid("product_config", f"{project.project_id}:{ordinal}")
                world.product_configs.append(ProductConfig(
                    dataset_version_id=dataset_id, product_config_id=config_id, project_id=project.project_id,
                    product_config_type="STANDARD", product_config_name=f"Config {project.project_code}-{ordinal:02d}",
                    product_name=f"Synthetic Product {index + 1:03d}", config_version="1.0",
                    customer_id=customers[0].customer_id, customer_material_code=None,
                    business_unit_id=unit_id, planning_department_id=departments[index % len(departments)].organization_id,
                    research_representative_employee_id=representative.employee_id,
                    product_config_status="ACTIVE", product_category_level_1="Electronics",
                    product_category_level_2=project.product_type or "Module", product_category_level_3="Standard Assembly",
                    product_team_name=f"Product Team {index + 1:03d}",
                    modified_by_employee_id=representative.employee_id,
                    modified_at=datetime.combine(snapshot, time(12), tzinfo=timezone.utc),
                    effective_from=effective_from, effective_to=None,
                ))
                for mid in project_materials[project.project_id]:
                    world.product_config_materials.append(ProductConfigMaterial(
                        dataset_version_id=dataset_id, product_config_material_id=uid("config_material", f"{config_id}:{mid}"),
                        product_config_id=config_id, material_id=mid,
                    ))

        anchors = material_anchors(scenario, procurement)
        for material_id, project_id in pairs:
            pair_key = f"{material_id}:{project_id}"
            pair_rng = Random(f"{config.evidence_seed}:{pair_key}")
            reference = Decimal(pair_rng.randint(config.reference_daily_qty_min, config.reference_daily_qty_max))
            plan = scenario.material_scenario_plans.get(material_id)
            is_target = plan is not None and plan.causal_project_id == project_id
            level = Decimal(1)
            change = "NONE"
            if is_target:
                change = plan.demand_change_type
                if plan.scenario_pattern == "AFTER_SALES":
                    level = (scenario_config.after_sales_level_ratio_min + scenario_config.after_sales_level_ratio_max) / 2
                elif plan.scenario_pattern in {"STOCKPILE", "INTERNAL_SIDE_PROJECT_OBSOLESCENCE"}:
                    level = Decimal(0)
            signal_id = uid("demand_signal", pair_key)
            world.demand_signals.append(DemandSignal(
                dataset_version_id=dataset_id, demand_signal_id=signal_id, material_id=material_id,
                project_id=project_id, organization_id=materials[material_id].primary_inventory_organization_id,
                signal_kind="PLANNED_DEMAND", scenario_generation_key=content_hash([signature, pair_key]),
                observed_from=start, reference_daily_qty=reference,
            ))
            baseline = {
                day: quantize(reference * level * (1 + config.daily_noise_ratio * Decimal(pair_rng.randint(-100, 100)) / 100))
                for day in days(start, end)
            }
            for day, qty in baseline.items():
                world.demand_signal_points.append(DemandSignalPoint(
                    dataset_version_id=dataset_id, demand_signal_point_id=uid("demand_point", f"{signal_id}:{day}"),
                    demand_signal_id=signal_id, demand_date=day, demand_qty=qty,
                ))
            for cycle, (before, after, window_start) in enumerate(source_cycles(anchors.get(material_id, []))):
                # A source planning cycle has a numeric budget refresh followed by a
                # dated revision. All candidate projects use the same observation dates.
                multiplier = config.planning_cycle_retention ** cycle if change != "NONE" else Decimal(1)
                cycle_base = {day: quantize(qty * multiplier) for day, qty in baseline.items()}
                revised = changed_quantities(cycle_base, window_start, change, scenario_config, config) if change != "NONE" else cycle_base
                for observed_on, values in ((before, cycle_base), (after, revised)):
                    for day in days(window_start, end):
                        world.demand_signal_revisions.append(DemandSignalRevision(
                            dataset_version_id=dataset_id,
                            demand_signal_revision_id=uid("demand_revision", f"{signal_id}:{observed_on}:{day}"),
                            demand_signal_id=signal_id, observed_on=observed_on,
                            demand_date=day, demand_qty=values[day],
                        ))
        return world
