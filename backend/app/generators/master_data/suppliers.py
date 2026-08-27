from app.generators.context import GenerationContext
from app.models.platform import Supplier


SUPPLIER_NAMES = (
    "Supplier Nova",
    "Supplier Vertex",
    "Supplier Horizon",
    "Supplier Summit",
    "Supplier Meridian",
    "Supplier Cascade",
    "Supplier Harbor",
    "Supplier Meadow",
    "Supplier Orbit",
    "Supplier Prism",
    "Supplier Quill",
    "Supplier Ridge",
    "Supplier Solstice",
    "Supplier Timber",
    "Supplier Vale",
)
CURRENCIES = ("CNY", "USD", "EUR")


def generate_suppliers(context: GenerationContext) -> list[Supplier]:
    rows: list[Supplier] = []
    for index in range(1, context.config.supplier_count + 1):
        code = f"SUP-{index:04d}"
        base_name = SUPPLIER_NAMES[(index - 1) % len(SUPPLIER_NAMES)]
        cycle = (index - 1) // len(SUPPLIER_NAMES)
        name = base_name if cycle == 0 else f"{base_name} {cycle + 1:02d}"
        rows.append(
            Supplier(
                dataset_version_id=context.dataset_version_id,
                supplier_id=context.entity_id("supplier", code),
                supplier_code=code,
                supplier_name=name,
                supplier_name_en=name,
                currency_code=context.rng.choices(CURRENCIES, weights=(6, 3, 1), k=1)[0],
                is_active=True,
            )
        )
    return rows

