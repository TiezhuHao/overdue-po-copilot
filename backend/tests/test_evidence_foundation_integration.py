from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, func, insert, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings

from app.generators.config import GenerationConfig
from app.generators.evidence_foundation.config import EvidenceFoundationConfig
from app.generators.evidence_foundation.world import record_payload
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.scenarios.config import ScenarioGenerationConfig
from app.models.evaluation import ScenarioTruth
from app.models.platform import DatasetVersion, ProjectCustomer, PoLineSchedule
from app.models.platform.evidence_foundation import (
    EVIDENCE_MODELS, DemandSignal, DemandSignalPoint, DemandSignalRevision,
    ProductConfig, ProductConfigMaterial, ProjectLifecycleHistory,
)
from app.services.dataset_generation import DatasetGenerationService
from app.services.evidence_foundation_generation import EvidenceFoundationError, EvidenceFoundationGenerationService
from app.services.procurement_generation import ProcurementGenerationService
from app.services.scenario_generation import ScenarioGenerationService

pytestmark = pytest.mark.integration
PC = ProcurementGenerationConfig.small_test()
SC = ScenarioGenerationConfig.small_test()
EC = EvidenceFoundationConfig()


def foundation(session, seed):
    master = DatasetGenerationService(session).generate(GenerationConfig.small_test(random_seed=seed), "evidence-test-" + uuid4().hex[:8])
    ProcurementGenerationService(session).generate(master.dataset_version_id, PC)
    ScenarioGenerationService(session).generate(master.dataset_version_id, SC)
    return master.dataset_version_id


def generate(session, dataset_id, **kwargs):
    return EvidenceFoundationGenerationService(session, **kwargs).generate(dataset_id, EC, procurement_config=PC, scenario_config=SC)


@pytest.fixture(scope="module")
def stored_evidence(migrated_database):
    with Session(migrated_database, expire_on_commit=False) as session:
        dataset_id = foundation(session, 75001)
        result = generate(session, dataset_id)
    try:
        yield result
    finally:
        with Session(migrated_database) as session:
            session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_version_id == dataset_id))
            session.commit()


def test_evidence_idempotency_and_hash_after_database_roundtrip(migrated_database, stored_evidence):
    with Session(migrated_database) as session:
        reused = generate(session, stored_evidence.dataset_version_id)
        assert reused.reused
        assert reused.evidence_foundation_content_hash == stored_evidence.evidence_foundation_content_hash
        dataset = session.get(DatasetVersion, stored_evidence.dataset_version_id)
        assert dataset.status == "GENERATING" and dataset.business_content_hash is None


def test_evidence_config_conflict_and_generating_gate(migrated_database, stored_evidence):
    with Session(migrated_database) as session:
        with pytest.raises(EvidenceFoundationError, match="EVIDENCE_CONFIG_CONFLICT"):
            EvidenceFoundationGenerationService(session).generate(
                stored_evidence.dataset_version_id, EvidenceFoundationConfig(evidence_seed=20260830),
                procurement_config=PC, scenario_config=SC,
            )
    with migrated_database.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(update(DatasetVersion).where(DatasetVersion.dataset_version_id == stored_evidence.dataset_version_id).values(status="READY"))
            with Session(conn, join_transaction_mode="create_savepoint") as session:
                with pytest.raises(EvidenceFoundationError, match="DATASET_NOT_GENERATING"):
                    generate(session, stored_evidence.dataset_version_id)
        finally:
            transaction.rollback()


def test_evidence_migration_matches_model_metadata(migrated_database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.models import Base

    names = {model.__tablename__ for model in EVIDENCE_MODELS}

    def included(obj, name, type_, reflected, compare_to):
        table = obj if type_ == "table" else getattr(obj, "table", None)
        return table is not None and table.name in names

    with migrated_database.connect() as connection:
        context = MigrationContext.configure(connection, opts={"include_schemas": True, "include_object": included})
        assert compare_metadata(context, Base.metadata) == []


def _changed_payload(model, row):
    payload = record_payload(row)
    key = next(column.key for column in model.__table__.primary_key if column.key != "dataset_version_id")
    payload[key] = uuid4()
    return payload


@pytest.mark.parametrize("invalid_stage", [None, "AFTER_SALES", "overlap"])
def test_project_lifecycle_no_overlap_and_controlled_stage(migrated_database, stored_evidence, invalid_stage):
    row = stored_evidence.world.project_lifecycle_history[0]
    payload = _changed_payload(ProjectLifecycleHistory, row)
    if invalid_stage != "overlap":
        payload["lifecycle_stage"] = invalid_stage
    with migrated_database.connect() as conn:
        with pytest.raises(IntegrityError) as error:
            conn.execute(insert(ProjectLifecycleHistory), payload)
        assert error.value.orig.sqlstate == ("23P01" if invalid_stage == "overlap" else "23502" if invalid_stage is None else "23514")


@pytest.mark.parametrize("model,field", [
    (ProductConfig, "project_id"), (ProductConfig, "customer_id"),
    (ProductConfig, "business_unit_id"), (ProductConfig, "planning_department_id"),
    (ProductConfig, "research_representative_employee_id"), (ProductConfig, "modified_by_employee_id"),
    (ProductConfigMaterial, "product_config_id"), (ProductConfigMaterial, "material_id"),
    (DemandSignal, "material_id"), (DemandSignal, "project_id"), (DemandSignal, "organization_id"),
    (ProjectLifecycleHistory, "project_id"),
])
def test_evidence_cross_dataset_foreign_keys(migrated_database, stored_evidence, model, field):
    # IDs exist in the original dataset, but cannot be referenced from another one.
    row = getattr(stored_evidence.world, model.__tablename__)[0]
    payload = _changed_payload(model, row)
    with Session(migrated_database) as session:
        other = DatasetGenerationService(session).generate(GenerationConfig.small_test(random_seed=75002), "evidence-foreign-" + uuid4().hex[:8])
        try:
            # Use a valid row from the original dataset with exactly one FK changed
            # to a real key from the other dataset, not merely a nonexistent UUID.
            fk = next(c for c in model.__table__.foreign_key_constraints if field in c.columns.keys())
            target = fk.elements[-1].column
            foreign_id = session.scalar(select(target).where(target.table.c.dataset_version_id == other.dataset_version_id))
            if foreign_id is None:
                # Product config targets need their evidence populated too.
                session.rollback()
                ProcurementGenerationService(session).generate(other.dataset_version_id, PC)
                ScenarioGenerationService(session).generate(other.dataset_version_id, SC)
                generate(session, other.dataset_version_id)
                foreign_id = session.scalar(select(target).where(target.table.c.dataset_version_id == other.dataset_version_id))
            payload[field] = foreign_id
            if model is ProductConfig:
                payload["product_config_name"] += "-foreign"
            session.rollback()
            with pytest.raises(IntegrityError) as error:
                primary_id = next(c for c in model.__table__.primary_key if c.key != "dataset_version_id")
                session.execute(update(model).where(
                    model.dataset_version_id == row.dataset_version_id,
                    primary_id == getattr(row, primary_id.key),
                ).values({field: foreign_id}))
            assert error.value.orig.sqlstate == "23503"
            session.rollback()
        finally:
            session.rollback()
            session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_version_id == other.dataset_version_id))
            session.commit()


@pytest.mark.parametrize("model", [DemandSignalPoint, DemandSignalRevision])
@pytest.mark.parametrize("violation", ["duplicate", "negative"])
def test_demand_signal_date_uniqueness_and_negative_quantity(migrated_database, stored_evidence, model, violation):
    row = getattr(stored_evidence.world, model.__tablename__)[0]
    payload = _changed_payload(model, row)
    if violation == "negative":
        payload["demand_qty"] = -1
    with migrated_database.connect() as conn:
        with pytest.raises(IntegrityError) as error:
            conn.execute(insert(model), payload)
        assert error.value.orig.sqlstate == ("23514" if violation == "negative" else "23505")


@pytest.mark.parametrize("model", EVIDENCE_MODELS)
def test_partial_evidence_rejected_without_repair(migrated_database, stored_evidence, model):
    # Roll back the deliberate damage after checking rejection; keep module fixture intact.
    with migrated_database.connect() as conn:
        outer = conn.begin()
        try:
            row = getattr(stored_evidence.world, model.__tablename__)[0]
            key = next(c for c in model.__table__.primary_key if c.key != "dataset_version_id")
            conn.execute(delete(model).where(model.dataset_version_id == row.dataset_version_id, key == getattr(row, key.key)))
            with Session(conn, join_transaction_mode="create_savepoint") as session:
                with pytest.raises(EvidenceFoundationError, match="INCOMPLETE_EVIDENCE_FOUNDATION"):
                    generate(session, stored_evidence.dataset_version_id)
        finally:
            outer.rollback()


@pytest.mark.parametrize("model,error_code", [
    (ProjectCustomer, "INCOMPLETE_MASTER_WORLD"),
    (PoLineSchedule, "INCOMPLETE_PROCUREMENT_WORLD"),
    (ScenarioTruth, "INCOMPLETE_SCENARIO_WORLD"),
])
def test_partial_prerequisite_world_is_rejected(migrated_database, stored_evidence, model, error_code):
    with migrated_database.connect() as conn:
        outer = conn.begin()
        try:
            key = next(c for c in model.__table__.primary_key if c.key != "dataset_version_id")
            target = conn.scalar(select(key).where(model.dataset_version_id == stored_evidence.dataset_version_id))
            conn.execute(delete(model).where(key == target, model.dataset_version_id == stored_evidence.dataset_version_id))
            with Session(conn, join_transaction_mode="create_savepoint") as session:
                with pytest.raises(EvidenceFoundationError, match=error_code):
                    generate(session, stored_evidence.dataset_version_id)
        finally:
            outer.rollback()


def test_evidence_insert_failure_rolls_back_all_six_tables(migrated_database):
    from sqlalchemy import event

    with Session(migrated_database) as session:
        dataset_id = foundation(session, 75003)

        def reject_points(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO platform.demand_signal_points"):
                raise RuntimeError("injected write failure after other evidence tables")

        event.listen(migrated_database, "before_cursor_execute", reject_points)
        try:
            with pytest.raises(RuntimeError, match="injected write failure"):
                generate(session, dataset_id)
        finally:
            event.remove(migrated_database, "before_cursor_execute", reject_points)
        for model in EVIDENCE_MODELS:
            assert session.scalar(select(func.count()).select_from(model).where(model.dataset_version_id == dataset_id)) == 0
        session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_version_id == dataset_id))
        session.commit()


def test_evidence_raw_table_permissions(migrated_database, stored_evidence, test_database_url):
    with migrated_database.connect() as conn:
        for model in EVIDENCE_MODELS:
            table = "platform." + model.__tablename__
            assert conn.scalar(text("SELECT has_table_privilege('system_a_generator', :table, 'INSERT')"), {"table": table})
            assert not conn.scalar(text("SELECT has_table_privilege('system_a_api', :table, 'SELECT')"), {"table": table})
    for role in ("generator", "api"):
        credentials = make_url(getattr(settings, f"database_url_{role}").get_secret_value())
        engine = create_engine(make_url(test_database_url).set(username=credentials.username, password=credentials.password), isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                assert conn.scalar(text("SELECT current_user")) == f"system_a_{role}"
                for model in EVIDENCE_MODELS:
                    table = "platform." + model.__tablename__
                    if role == "generator":
                        assert conn.execute(text(f"INSERT INTO {table} SELECT * FROM {table} WHERE false")).rowcount == 0
                    else:
                        with pytest.raises(DBAPIError) as denied:
                            conn.execute(text(f"SELECT * FROM {table} LIMIT 1"))
                        assert denied.value.orig.sqlstate == "42501"
        finally:
            engine.dispose()
