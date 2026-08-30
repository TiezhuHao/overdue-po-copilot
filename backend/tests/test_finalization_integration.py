from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, text, update
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.finalization.service import DatasetFinalizationError, DatasetFinalizationService
from app.main import app
from app.models.evaluation import ScenarioTruth
from app.models.platform import DatasetVersion, Material
from app.services.operational_evidence_generation import OperationalEvidenceError, OperationalEvidenceGenerationService
from tests.test_operational_integration import operational_worlds
from tests.test_forecast_integration import forecast_worlds


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def finalized_world(migrated_database, operational_worlds):
    world = operational_worlds[0]
    with Session(migrated_database) as session:
        first = DatasetFinalizationService(session).finalize(world.dataset_version_id)
    yield world, first


def test_finalization_requires_complete_world(migrated_database):
    did = uuid4()
    with Session(migrated_database) as session:
        with session.begin():
            session.execute(insert(DatasetVersion), {
                "dataset_version_id": did, "version_name": f"incomplete-{did}", "random_seed": 1,
                "snapshot_date": date(2026, 8, 26), "generator_version": "test", "schema_version": "011",
                "generation_config": {}, "generation_signature": f"sig-{did}", "business_content_hash": None,
                "status": "GENERATING",
            })
        with pytest.raises(DatasetFinalizationError, match="INCOMPLETE"):
            DatasetFinalizationService(session, require_repository_scan=False).finalize(did)
        with session.begin():
            session.execute(text("DELETE FROM platform.dataset_versions WHERE dataset_version_id=:did"), {"did": did})


def test_dataset_generating_to_ready_and_hash(finalized_world):
    _, result = finalized_world
    assert result.status == "READY" and not result.reused
    assert len(result.business_content_hash) == len(result.report_semantic_content_hash) == 64
    assert result.business_content_hash != result.report_semantic_content_hash


def test_finalization_idempotency(migrated_database, finalized_world):
    world, first = finalized_world
    with Session(migrated_database) as session:
        again = DatasetFinalizationService(session).finalize(world.dataset_version_id)
    assert again.reused and again.business_content_hash == first.business_content_hash


def test_business_hash_excludes_direct_private_rows(migrated_database, finalized_world):
    world, first = finalized_world
    with Session(migrated_database) as session:
        row = session.scalar(select(ScenarioTruth).where(ScenarioTruth.dataset_version_id == world.dataset_version_id).limit(1))
        original = row.expected_action
        with session.begin_nested():
            row.expected_action = "private-test-only-change"
            session.flush()
            again = DatasetFinalizationService(session, require_repository_scan=False)._business_hash(
                session.get(DatasetVersion, world.dataset_version_id))[0]
            assert again == first.business_content_hash
            row.expected_action = original


def test_ready_content_mismatch_detected(migrated_database, finalized_world):
    world, _ = finalized_world
    with Session(migrated_database) as session:
        material = session.scalar(select(Material).where(Material.dataset_version_id == world.dataset_version_id).limit(1))
        original = material.material_description
        material.material_description = original + " changed"
        session.commit()
    try:
        with Session(migrated_database) as session:
            with pytest.raises(DatasetFinalizationError, match="READY_DATASET_CONTENT_MISMATCH"):
                DatasetFinalizationService(session, require_repository_scan=False).finalize(world.dataset_version_id)
    finally:
        with Session(migrated_database) as session:
            material = session.scalar(select(Material).where(Material.dataset_version_id == world.dataset_version_id).limit(1))
            material.material_description = original
            session.commit()


def test_ready_dataset_generator_rejected(migrated_database, finalized_world):
    world, _ = finalized_world
    with Session(migrated_database) as session:
        with pytest.raises(OperationalEvidenceError, match="DATASET_NOT_GENERATING"):
            OperationalEvidenceGenerationService(session).generate(world.dataset_version_id)


def test_default_ready_api_behavior(migrated_database, finalized_world):
    world, _ = finalized_world
    def override():
        with Session(migrated_database) as session:
            yield session
    app.dependency_overrides[get_db_session] = override
    try:
        response = TestClient(app).get("/api/v1/reports/overdue-pos", params={"page_size": 1})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200 and response.json()["dataset_version_id"] == str(world.dataset_version_id)
