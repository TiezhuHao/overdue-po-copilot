from app.generators.context import GenerationContext
from app.models.platform import Project


PROJECT_NAMES = (
    "Project Aurora",
    "Project Atlas",
    "Project Beacon",
    "Project Cedar",
    "Project Compass",
    "Project Delta",
    "Project Ember",
    "Project Falcon",
    "Project Grove",
    "Project Harbor",
    "Project Indigo",
    "Project Juniper",
    "Project Keystone",
    "Project Lantern",
    "Project Meadow",
    "Project Northstar",
    "Project Orbit",
    "Project Prism",
    "Project Quartz",
    "Project River",
    "Project Summit",
    "Project Timber",
    "Project Umbra",
    "Project Vale",
    "Project Willow",
    "Project Zenith",
)


def generate_projects(context: GenerationContext) -> list[Project]:
    count = context.config.project_count
    duplicate_indexes = {20, 21} if count >= 21 else {count - 1, count}
    rows: list[Project] = []
    for index in range(1, count + 1):
        code = f"PRJ-{index:04d}"
        if context.config.same_project_name_fixture_enabled and index in duplicate_indexes:
            name = "Project Phoenix"
        else:
            base_name = PROJECT_NAMES[(index - 1) % len(PROJECT_NAMES)]
            cycle = (index - 1) // len(PROJECT_NAMES)
            name = base_name if cycle == 0 else f"{base_name} {cycle + 1:02d}"
        rows.append(
            Project(
                dataset_version_id=context.dataset_version_id,
                project_id=context.entity_id("project", code),
                project_code=code,
                project_name=name,
                customer_project_name=f"Customer Program {index:04d}",
                brand_name=f"Synthetic Brand {1 + ((index - 1) % 6):02d}",
                product_type=context.rng.choice(
                    ("Connected Device", "Control Module", "Sensor Platform", "Power Unit")
                ),
                shipment_type=context.rng.choice(("STANDARD", "CONFIGURED")),
                business_mode=context.rng.choice(("DIRECT", "DISTRIBUTED")),
            )
        )
    return rows

