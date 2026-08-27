from decimal import Decimal

from app.generators.context import GenerationContext
from app.models.platform import Material, Organization


MATERIAL_CATEGORIES = (
    "Communication IC",
    "Power Management IC",
    "Sensor",
    "Memory",
    "Connector",
    "Passive Component",
    "Module",
)
LEAD_TIMES = (14, 21, 30, 45, 60, 90, 120)
LEAD_TIME_WEIGHTS = (8, 12, 24, 24, 18, 10, 4)


def generate_materials(
    context: GenerationContext,
    organizations: list[Organization],
) -> list[Material]:
    inventory_organizations = [
        organization
        for organization in organizations
        if organization.organization_type == "INVENTORY_ORG"
    ]
    trial_organizations = [
        organization
        for organization in inventory_organizations
        if organization.inventory_organization_type == "TRIAL"
    ]
    mass_organizations = [
        organization
        for organization in inventory_organizations
        if organization.inventory_organization_type == "MASS_PRODUCTION"
    ]

    rows: list[Material] = []
    for index in range(1, context.config.material_count + 1):
        code = f"MAT-{index:04d}"
        category = MATERIAL_CATEGORIES[(index - 1) % len(MATERIAL_CATEGORIES)]
        if index == 1:
            primary_organization = trial_organizations[0]
        else:
            organization_pool = (
                trial_organizations
                if context.rng.random() < 0.12
                else mass_organizations
            )
            primary_organization = context.rng.choice(organization_pool)
        lead_time = context.rng.choices(
            LEAD_TIMES,
            weights=LEAD_TIME_WEIGHTS,
            k=1,
        )[0]
        manufacturer_lead_time = lead_time + context.rng.choice((0, 0, 7, 14, 30))
        rows.append(
            Material(
                dataset_version_id=context.dataset_version_id,
                material_id=context.entity_id("material", code),
                material_code=code,
                material_description=f"Synthetic {category} {index:04d}",
                specification_model=f"Synthetic Specification {index:04d}",
                model=f"Model-{index:04d}",
                material_lt_days=lead_time,
                manufacturer_lt_days=manufacturer_lead_time,
                minimum_pack_qty=Decimal(context.rng.choice((1, 5, 10, 20, 50))),
                minimum_order_qty=Decimal(context.rng.choice((10, 25, 50, 100, 200))),
                non_cancelable_non_returnable_flag=context.rng.random() < 0.20,
                primary_inventory_organization_id=primary_organization.organization_id,
            )
        )
    return rows
