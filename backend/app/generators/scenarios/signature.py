from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.signature import content_hash


def scenario_generation_signature(
    dataset_generation_signature: str,
    procurement_facts_hash: str,
    config: ScenarioGenerationConfig,
) -> str:
    return content_hash(
        {
            "dataset_generation_signature": dataset_generation_signature,
            "procurement_facts_hash": procurement_facts_hash,
            "scenario_config": config,
        }
    )
