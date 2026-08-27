from datetime import date

from app.generators.context import GenerationContext
from app.models.platform import Organization


def generate_organizations(context: GenerationContext) -> list[Organization]:
    config = context.config
    effective_from = date(max(config.snapshot_date.year - 5, 1), 1, 1)
    rows: list[Organization] = []

    business_entities: list[Organization] = []
    for index in range(1, config.business_entity_count + 1):
        code = f"BE-{index:03d}"
        row = Organization(
            dataset_version_id=context.dataset_version_id,
            organization_id=context.entity_id("organization", code),
            organization_code=code,
            organization_name=f"Business Entity {index:02d}",
            organization_type="BUSINESS_ENTITY",
            inventory_organization_type=None,
            parent_organization_id=None,
            effective_from=effective_from,
            effective_to=None,
        )
        business_entities.append(row)
        rows.append(row)

    business_units: list[Organization] = []
    for index in range(1, config.business_unit_count + 1):
        code = f"BU-{index:03d}"
        parent = business_entities[(index - 1) % len(business_entities)]
        row = Organization(
            dataset_version_id=context.dataset_version_id,
            organization_id=context.entity_id("organization", code),
            organization_code=code,
            organization_name=f"Business Unit {index:02d}",
            organization_type="BUSINESS_UNIT",
            inventory_organization_type=None,
            parent_organization_id=parent.organization_id,
            effective_from=effective_from,
            effective_to=None,
        )
        business_units.append(row)
        rows.append(row)

    planning_departments: list[Organization] = []
    for index in range(1, config.planning_department_count + 1):
        code = f"PD-{index:03d}"
        parent = business_units[(index - 1) % len(business_units)]
        row = Organization(
            dataset_version_id=context.dataset_version_id,
            organization_id=context.entity_id("organization", code),
            organization_code=code,
            organization_name=f"Planning Department {index:02d}",
            organization_type="PLANNING_DEPARTMENT",
            inventory_organization_type=None,
            parent_organization_id=parent.organization_id,
            effective_from=effective_from,
            effective_to=None,
        )
        planning_departments.append(row)
        rows.append(row)

    trial_count = round(
        config.inventory_organization_count * float(config.trial_inventory_org_ratio)
    )
    trial_count = min(max(trial_count, 1), config.inventory_organization_count - 1)
    for index in range(1, config.inventory_organization_count + 1):
        code = f"ORG-{index:03d}"
        parent = business_units[(index - 1) % len(business_units)]
        inventory_type = (
            "TRIAL"
            if index > config.inventory_organization_count - trial_count
            else "MASS_PRODUCTION"
        )
        rows.append(
            Organization(
                dataset_version_id=context.dataset_version_id,
                organization_id=context.entity_id("organization", code),
                organization_code=code,
                organization_name=f"Inventory Organization {index:02d}",
                organization_type="INVENTORY_ORG",
                inventory_organization_type=inventory_type,
                parent_organization_id=parent.organization_id,
                effective_from=effective_from,
                effective_to=None,
            )
        )

    for index in range(1, config.department_count + 1):
        code = f"DEP-{index:03d}"
        parent = planning_departments[(index - 1) % len(planning_departments)]
        rows.append(
            Organization(
                dataset_version_id=context.dataset_version_id,
                organization_id=context.entity_id("organization", code),
                organization_code=code,
                organization_name=f"Department {index:02d}",
                organization_type="DEPARTMENT",
                inventory_organization_type=None,
                parent_organization_id=parent.organization_id,
                effective_from=effective_from,
                effective_to=None,
            )
        )
    return rows
