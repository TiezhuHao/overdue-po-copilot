from uuid import uuid4

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.generators.config import GenerationConfig
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.generators.scenarios.validation import ScenarioWorldValidationError
from app.models.evaluation import ScenarioTruth
from app.models.platform import DatasetVersion
from app.services.dataset_generation import DatasetGenerationService
from app.services.procurement_generation import ProcurementGenerationService
from app.services.scenario_generation import ScenarioGenerationError, ScenarioGenerationService


pytestmark = pytest.mark.integration


def _foundation(session: Session, seed: int):
    suffix = uuid4().hex[:8]
    master = DatasetGenerationService(session).generate(
        GenerationConfig.small_test(random_seed=seed), f"scenario-test-{suffix}"
    )
    ProcurementGenerationService(session).generate(
        master.dataset_version_id,
        ProcurementGenerationConfig.small_test(random_seed=seed + 1000),
    )
    return master


def test_scenario_service_truth_scope_idempotency_and_config_conflict(
    migrated_database: Engine,
) -> None:
    with Session(migrated_database, expire_on_commit=False) as session:
        master = _foundation(session, 51001)
        config = ScenarioGenerationConfig.small_test(scenario_seed=61001)
        first = ScenarioGenerationService(session).generate(master.dataset_version_id, config)
        reused = ScenarioGenerationService(session).generate(master.dataset_version_id, config)
        assert reused.reused is True
        assert len(first.world.scenario_truth_rows) == first.overdue_schedule_count
        assert reused.scenario_content_hash == first.scenario_content_hash
        with pytest.raises(ScenarioGenerationError, match="SCENARIO_CONFIG_CONFLICT"):
            ScenarioGenerationService(session).generate(
                master.dataset_version_id,
                ScenarioGenerationConfig.small_test(scenario_seed=61002),
            )
        dataset = session.get(DatasetVersion, master.dataset_version_id)
        assert dataset.status == "GENERATING"
        assert dataset.business_content_hash is None
        session.delete(dataset)
        session.commit()


def test_partial_scenario_world_is_rejected(migrated_database: Engine) -> None:
    with Session(migrated_database, expire_on_commit=False) as session:
        master = _foundation(session, 51002)
        config = ScenarioGenerationConfig.small_test(scenario_seed=61003)
        result = ScenarioGenerationService(session).generate(master.dataset_version_id, config)
        session.execute(
            delete(ScenarioTruth).where(
                ScenarioTruth.scenario_truth_id
                == result.world.scenario_truth_rows[0].scenario_truth_id
            )
        )
        session.commit()
        with pytest.raises(ScenarioGenerationError, match="INCOMPLETE_SCENARIO_WORLD"):
            ScenarioGenerationService(session).generate(master.dataset_version_id, config)
        dataset = session.get(DatasetVersion, master.dataset_version_id)
        session.delete(dataset)
        session.commit()


class _RejectingValidator:
    def validate(self, *args, **kwargs) -> None:
        raise ScenarioWorldValidationError("injected scenario failure")


def test_scenario_failure_rolls_back_truth_rows(migrated_database: Engine) -> None:
    with Session(migrated_database, expire_on_commit=False) as session:
        master = _foundation(session, 51003)
        with pytest.raises(ScenarioWorldValidationError, match="injected"):
            ScenarioGenerationService(session, validator=_RejectingValidator()).generate(
                master.dataset_version_id,
                ScenarioGenerationConfig.small_test(scenario_seed=61004),
            )
        assert session.scalar(
            select(func.count()).select_from(ScenarioTruth).where(
                ScenarioTruth.dataset_version_id == master.dataset_version_id
            )
        ) == 0
        dataset = session.get(DatasetVersion, master.dataset_version_id)
        session.delete(dataset)
        session.commit()
