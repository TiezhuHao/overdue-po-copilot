from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.generators.master_data.world import MasterWorld
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.procurement.generator import ProcurementGenerator
from app.generators.procurement.signature import procurement_generation_signature
from app.generators.procurement.validation import ProcurementWorldValidator
from app.generators.procurement.world import ProcurementWorld
from app.models.platform import DatasetVersion, PoHeader, PoLine, PoLineSchedule
from app.services.dataset_generation import COLLECTION_MODELS


class ProcurementGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProcurementGenerationResult:
    dataset_version_id: UUID
    dataset_version_name: str
    procurement_signature: str
    procurement_content_hash: str
    counts: dict[str, int]
    validation_status: str
    reused: bool
    world: ProcurementWorld
    master: MasterWorld
    snapshot_date: Any


class ProcurementGenerationService:
    def __init__(
        self,
        session: Session,
        generator: ProcurementGenerator | None = None,
        validator: ProcurementWorldValidator | None = None,
    ) -> None:
        self.session = session
        self.generator = generator or ProcurementGenerator()
        self.validator = validator or ProcurementWorldValidator()

    def _load_master(self, dataset_version_id: UUID) -> MasterWorld:
        return MasterWorld(
            **{
                name: list(
                    self.session.scalars(
                        select(model).where(model.dataset_version_id == dataset_version_id)
                    )
                )
                for name, model in COLLECTION_MODELS
            }
        )

    def _load_procurement(self, dataset_version_id: UUID) -> ProcurementWorld:
        return ProcurementWorld(
            po_headers=list(
                self.session.scalars(
                    select(PoHeader).where(PoHeader.dataset_version_id == dataset_version_id)
                )
            ),
            po_lines=list(
                self.session.scalars(
                    select(PoLine).where(PoLine.dataset_version_id == dataset_version_id)
                )
            ),
            po_line_schedules=list(
                self.session.scalars(
                    select(PoLineSchedule).where(
                        PoLineSchedule.dataset_version_id == dataset_version_id
                    )
                )
            ),
        )

    def generate(
        self,
        dataset_version_id: UUID,
        config: ProcurementGenerationConfig,
    ) -> ProcurementGenerationResult:
        reused = False
        with self.session.begin():
            dataset = self.session.scalar(
                select(DatasetVersion)
                .where(DatasetVersion.dataset_version_id == dataset_version_id)
                .with_for_update()
            )
            if dataset is None:
                raise ProcurementGenerationError("DATASET_NOT_FOUND")
            if dataset.status != "GENERATING":
                raise ProcurementGenerationError("DATASET_NOT_GENERATING")
            master = self._load_master(dataset_version_id)
            if any(not getattr(master, name) for name in MasterWorld.COLLECTION_NAMES):
                raise ProcurementGenerationError("INCOMPLETE_MASTER_WORLD")
            signature = procurement_generation_signature(dataset.generation_signature, config)
            existing_counts = {
                "po_headers": self.session.scalar(
                    select(func.count()).select_from(PoHeader).where(
                        PoHeader.dataset_version_id == dataset_version_id
                    )
                ),
                "po_lines": self.session.scalar(
                    select(func.count()).select_from(PoLine).where(
                        PoLine.dataset_version_id == dataset_version_id
                    )
                ),
                "po_line_schedules": self.session.scalar(
                    select(func.count()).select_from(PoLineSchedule).where(
                        PoLineSchedule.dataset_version_id == dataset_version_id
                    )
                ),
            }
            if all(value == 0 for value in existing_counts.values()):
                world = self.generator.generate(
                    dataset_version_id, dataset.snapshot_date, signature, config, master
                )
                self.validator.validate(world, master, dataset_version_id)
                self.session.add_all(world.po_headers)
                self.session.flush()
                self.session.add_all(world.po_lines)
                self.session.flush()
                self.session.add_all(world.po_line_schedules)
                self.session.flush()
            elif any(value == 0 for value in existing_counts.values()):
                raise ProcurementGenerationError("INCOMPLETE_PROCUREMENT_WORLD")
            else:
                world = self._load_procurement(dataset_version_id)
                self.validator.validate(world, master, dataset_version_id)
                expected = self.generator.generate(
                    dataset_version_id, dataset.snapshot_date, signature, config, master
                )
                if world.procurement_content_hash(signature) != expected.procurement_content_hash(
                    signature
                ):
                    raise ProcurementGenerationError("PROCUREMENT_CONFIG_CONFLICT")
                reused = True

            return ProcurementGenerationResult(
                dataset_version_id=dataset_version_id,
                dataset_version_name=dataset.version_name,
                procurement_signature=signature,
                procurement_content_hash=world.procurement_content_hash(signature),
                counts=world.counts(),
                validation_status="PASS",
                reused=reused,
                world=world,
                master=master,
                snapshot_date=dataset.snapshot_date,
            )
