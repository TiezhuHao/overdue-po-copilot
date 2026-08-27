from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import deterministic_uuid
from app.generators.config import GenerationConfig
from app.generators.context import GenerationContext
from app.generators.master_data.generator import MasterDataGenerator
from app.generators.master_data.world import MasterWorld
from app.generators.signature import canonicalize, generation_config_payload, generation_signature
from app.generators.validation import MasterDataValidator, MasterWorldValidationError
from app.models.platform import (
    Customer,
    DatasetVersion,
    Employee,
    EmployeeRoleAssignment,
    Material,
    MaterialMpmAssignment,
    MaterialProject,
    MaterialResponsibilityAssignment,
    MaterialSupplierAssignment,
    Organization,
    Project,
    ProjectCustomer,
    Supplier,
)


class DatasetGenerationConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class MasterGenerationResult:
    dataset_version_id: UUID
    version_name: str
    generation_signature: str
    master_content_hash: str
    counts: dict[str, int]
    validation_status: str
    reused: bool
    world: MasterWorld


COLLECTION_MODELS: tuple[tuple[str, type[Any]], ...] = (
    ("organizations", Organization),
    ("employees", Employee),
    ("employee_role_assignments", EmployeeRoleAssignment),
    ("customers", Customer),
    ("suppliers", Supplier),
    ("projects", Project),
    ("materials", Material),
    ("material_projects", MaterialProject),
    ("material_mpm_assignments", MaterialMpmAssignment),
    ("material_supplier_assignments", MaterialSupplierAssignment),
    ("project_customers", ProjectCustomer),
    ("material_responsibility_assignments", MaterialResponsibilityAssignment),
)


class DatasetGenerationService:
    def __init__(
        self,
        session: Session,
        generator: MasterDataGenerator | None = None,
        validator: MasterDataValidator | None = None,
    ) -> None:
        self.session = session
        self.generator = generator or MasterDataGenerator()
        self.validator = validator or MasterDataValidator()

    def _load_world(self, dataset_version_id: UUID) -> MasterWorld:
        values = {
            name: list(
                self.session.scalars(
                    select(model).where(model.dataset_version_id == dataset_version_id)
                )
            )
            for name, model in COLLECTION_MODELS
        }
        return MasterWorld(**values)

    def generate(self, config: GenerationConfig, version_name: str) -> MasterGenerationResult:
        signature = generation_signature(config)
        dataset_version_id = deterministic_uuid(signature, "dataset_version", signature)
        reused = False
        actual_version_name = version_name

        with self.session.begin():
            existing = self.session.scalar(
                select(DatasetVersion).where(
                    DatasetVersion.generation_signature == signature
                )
            )
            if existing is None:
                existing = self.session.scalar(
                    select(DatasetVersion).where(DatasetVersion.version_name == version_name)
                )
            if existing is not None:
                if existing.generation_signature != signature:
                    raise DatasetGenerationConflict(
                        f"version_name {version_name!r} is already bound to another signature"
                    )
                if existing.status == "READY":
                    raise DatasetGenerationConflict("the matching dataset is already READY")
                if existing.status != "GENERATING":
                    raise DatasetGenerationConflict(
                        f"the matching dataset has terminal status {existing.status}"
                    )
                world = self._load_world(existing.dataset_version_id)
                if any(not getattr(world, name) for name in MasterWorld.COLLECTION_NAMES):
                    raise MasterWorldValidationError(
                        "the existing GENERATING dataset is incomplete"
                    )
                self.validator.validate(world, existing.dataset_version_id, config.snapshot_date)
                dataset_version_id = existing.dataset_version_id
                actual_version_name = existing.version_name
                reused = True
            else:
                dataset = DatasetVersion(
                    dataset_version_id=dataset_version_id,
                    version_name=version_name,
                    random_seed=config.random_seed,
                    snapshot_date=config.snapshot_date,
                    generator_version=config.generator_version,
                    schema_version=config.schema_version,
                    generation_config=canonicalize(generation_config_payload(config)),
                    generation_signature=signature,
                    business_content_hash=None,
                    status="GENERATING",
                )
                self.session.add(dataset)
                self.session.flush()
                context = GenerationContext(
                    dataset_version_id=dataset_version_id,
                    generation_signature=signature,
                    config=config,
                    rng=Random(config.random_seed),
                )
                world = self.generator.generate(context)
                self.validator.validate(world, dataset_version_id, config.snapshot_date)
                # The models intentionally avoid ORM relationship state. Flush explicit
                # dependency layers so PostgreSQL can enforce every dataset-scoped FK.
                self.session.add_all(world.organizations)
                self.session.flush()
                self.session.add_all(world.employees)
                self.session.add_all(world.customers)
                self.session.add_all(world.suppliers)
                self.session.add_all(world.projects)
                self.session.add_all(world.materials)
                self.session.flush()
                for name in MasterWorld.COLLECTION_NAMES:
                    if name not in {
                        "organizations",
                        "employees",
                        "customers",
                        "suppliers",
                        "projects",
                        "materials",
                    }:
                        self.session.add_all(getattr(world, name))
                self.session.flush()

            master_hash = world.master_content_hash(signature)
            return MasterGenerationResult(
                dataset_version_id=dataset_version_id,
                version_name=actual_version_name,
                generation_signature=signature,
                master_content_hash=master_hash,
                counts=world.counts(),
                validation_status="PASS",
                reused=reused,
                world=world,
            )
