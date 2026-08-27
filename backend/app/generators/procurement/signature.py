from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.signature import content_hash


def procurement_generation_signature(
    dataset_generation_signature: str,
    config: ProcurementGenerationConfig,
) -> str:
    return content_hash(
        {
            "dataset_generation_signature": dataset_generation_signature,
            "procurement_config": config,
        }
    )
