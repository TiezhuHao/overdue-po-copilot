from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.generators.config import GenerationConfig
from app.generators.signature import generation_signature
from app.generators.validation import MasterWorldValidationError
from app.models.platform import DatasetVersion, Material
from app.services.dataset_generation import DatasetGenerationService


@pytest.mark.integration
def test_generation_is_transactional_idempotent_and_dataset_isolated(
    migrated_database: Engine,
) -> None:
    suffix = uuid4().hex[:8]
    first_config = GenerationConfig.small_test(random_seed=8001)
    second_config = GenerationConfig.small_test(random_seed=8002)
    with Session(migrated_database, expire_on_commit=False) as session:
        first = DatasetGenerationService(session).generate(first_config, f"test-master-{suffix}-a")
        reused = DatasetGenerationService(session).generate(first_config, f"test-master-{suffix}-a")
        reused_under_requested_alias = DatasetGenerationService(session).generate(
            first_config, f"test-master-{suffix}-unused-alias"
        )
        second = DatasetGenerationService(session).generate(second_config, f"test-master-{suffix}-b")
        assert reused.reused is True
        assert reused.dataset_version_id == first.dataset_version_id
        assert reused_under_requested_alias.version_name == first.version_name
        assert first.dataset_version_id != second.dataset_version_id
        assert first.master_content_hash != second.master_content_hash

        rows = session.scalars(
            select(DatasetVersion).where(
                DatasetVersion.dataset_version_id.in_(
                    [first.dataset_version_id, second.dataset_version_id]
                )
            )
        ).all()
        assert all(row.status == "GENERATING" for row in rows)
        assert all(row.business_content_hash is None for row in rows)
        first_material = session.scalar(
            select(Material).where(Material.dataset_version_id == first.dataset_version_id)
        )
        second_material = session.scalar(
            select(Material).where(Material.dataset_version_id == second.dataset_version_id)
        )
        assert first_material.material_code == second_material.material_code
        assert first_material.material_id != second_material.material_id

        session.delete(rows[0])
        session.delete(rows[1])
        session.commit()


class _RejectingValidator:
    def validate(self, *args, **kwargs) -> None:
        raise MasterWorldValidationError("injected validation failure")


@pytest.mark.integration
def test_validation_failure_rolls_back_every_row(migrated_database: Engine) -> None:
    config = GenerationConfig.small_test(random_seed=9001)
    version_name = f"rollback-{uuid4().hex[:8]}"
    with Session(migrated_database) as session:
        with pytest.raises(MasterWorldValidationError, match="injected"):
            DatasetGenerationService(session, validator=_RejectingValidator()).generate(
                config, version_name
            )
    with Session(migrated_database) as session:
        assert session.scalar(
            select(func.count()).select_from(DatasetVersion).where(
                DatasetVersion.generation_signature == generation_signature(config)
            )
        ) == 0
