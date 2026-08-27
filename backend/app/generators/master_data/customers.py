from app.generators.context import GenerationContext
from app.models.platform import Customer


CUSTOMER_NAMES = (
    "Customer Alpha",
    "Customer Beta",
    "Customer Gamma",
    "Customer Delta",
    "Customer Epsilon",
    "Customer Zeta",
    "Customer Eta",
    "Customer Theta",
    "Customer Iota",
    "Customer Kappa",
    "Customer Lambda",
    "Customer Mu",
)


def generate_customers(context: GenerationContext) -> list[Customer]:
    rows: list[Customer] = []
    for index in range(1, context.config.customer_count + 1):
        code = f"CUS-{index:04d}"
        base_name = CUSTOMER_NAMES[(index - 1) % len(CUSTOMER_NAMES)]
        cycle = (index - 1) // len(CUSTOMER_NAMES)
        name = base_name if cycle == 0 else f"{base_name} {cycle + 1:02d}"
        rows.append(
            Customer(
                dataset_version_id=context.dataset_version_id,
                customer_id=context.entity_id("customer", code),
                customer_code=code,
                customer_short_code=f"C{index:03d}",
                customer_name=name,
            )
        )
    return rows

