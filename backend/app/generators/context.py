from dataclasses import dataclass
from random import Random
from uuid import UUID

from app.core.ids import deterministic_uuid
from app.generators.config import GenerationConfig


@dataclass(frozen=True)
class GenerationContext:
    dataset_version_id: UUID
    generation_signature: str
    config: GenerationConfig
    rng: Random

    def entity_id(self, entity_type: str, stable_business_key: str) -> UUID:
        return deterministic_uuid(
            self.generation_signature,
            entity_type,
            stable_business_key,
        )

