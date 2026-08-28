from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.generators.evidence_foundation.world import record_payload
from app.generators.operational_evidence.config import OperationalEvidenceConfig
from app.models import Base
from app.models.evaluation import ScenarioTruth
from app.models.platform import DatasetVersion, ProjectCustomer, PoLineSchedule
from app.models.platform.evidence_foundation import DemandSignalPoint
from app.models.platform.forecasts import MonthlyForecast
from app.models.platform.operational import OPERATIONAL_MODELS, InventorySnapshot, InventoryAgeBucket, SupplyDemandSnapshot, SupplyDemandComponent, StockpileVersion, StockpileRecord, StockpileForecast, StockpileBalanceProjection, StockpileInventoryAgeBucket
from app.services.operational_evidence_generation import OperationalEvidenceError, OperationalEvidenceGenerationService
from tests.test_forecast_integration import forecast_worlds, generate_forecast
from tests.test_evidence_foundation_integration import PC, SC, foundation, generate

pytestmark = pytest.mark.integration


def generate_operational(session, did, config=None):
    return OperationalEvidenceGenerationService(session).generate(did, config, procurement_config=PC, scenario_config=SC)


def upstream_fingerprint(connection, did):
    excluded = {m.__table__.fullname for m in OPERATIONAL_MODELS}
    digest = sha256()
    for name in sorted(set(Base.metadata.tables) - excluded):
        # Only static metadata names are used; the dataset value is bound.
        rows = sorted(connection.scalars(text(f'SELECT row_to_json(t)::text FROM {name} t WHERE dataset_version_id=:did'), {'did': did}))
        digest.update(name.encode())
        digest.update('\n'.join(rows).encode())
    return digest.hexdigest()


@pytest.fixture(scope='module')
def operational_worlds(migrated_database, forecast_worlds):
    results = []
    for forecast in forecast_worlds:
        with migrated_database.connect() as conn:
            before = upstream_fingerprint(conn, forecast.dataset_version_id)
        with Session(migrated_database) as session:
            results.append(generate_operational(session, forecast.dataset_version_id))
        with migrated_database.connect() as conn:
            assert upstream_fingerprint(conn, forecast.dataset_version_id) == before
    return results


def test_operational_database_idempotency_and_upstream_unchanged(migrated_database, operational_worlds):
    original = operational_worlds[0]
    with Session(migrated_database) as session:
        reused = generate_operational(session, original.dataset_version_id)
        assert reused.reused and reused.operational_content_hash == original.operational_content_hash
        dataset = session.get(DatasetVersion, original.dataset_version_id)
        assert dataset.status == 'GENERATING' and dataset.business_content_hash is None


def test_operational_metadata_matches_migration(migrated_database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    names = {m.__tablename__ for m in OPERATIONAL_MODELS}
    def include(obj, name, kind, reflected, comparison):
        table = obj if kind == 'table' else getattr(obj, 'table', None)
        return table is not None and table.name in names
    with migrated_database.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn, opts={'include_schemas': True, 'include_object': include}), Base.metadata) == []


@pytest.mark.parametrize('model,field,value', [
    (InventorySnapshot, 'available_qty', -1), (InventorySnapshot, 'available_qty', 100000000),
    (InventoryAgeBucket, 'age_qty', -1), (InventoryAgeBucket, 'age_threshold_days', 0),
    (SupplyDemandSnapshot, 'supply_demand_surplus_qty', 100000000),
    (SupplyDemandSnapshot, 'trial_all_supply_qty', -1), (SupplyDemandComponent, 'component_qty', -1),
    (StockpileVersion, 'sequence_no', 0), (StockpileRecord, 'target_stockpile_qty', -1),
    (StockpileRecord, 'stockpile_period_months', 0), (StockpileForecast, 'forecast_qty', -1),
    (StockpileForecast, 'forecast_month', '2026-01-02'), (StockpileForecast, 'demand_lineage', []),
    (StockpileBalanceProjection, 'demand_qty', -1), (StockpileBalanceProjection, 'closing_projected_qty', 100000000),
    (StockpileInventoryAgeBucket, 'age_qty', -1),
])
def test_operational_postgres_checks(database_connection, operational_worlds, model, field, value):
    row = getattr(operational_worlds[0].world, model.__tablename__)[0]
    with pytest.raises(IntegrityError) as caught:
        database_connection.execute(update(model).where(*(getattr(model, c.key) == getattr(row, c.key) for c in model.__table__.primary_key)).values({field: value}))
    assert caught.value.orig.sqlstate == '23514'


@pytest.mark.parametrize('model', OPERATIONAL_MODELS)
def test_operational_business_grain_unique(database_connection, operational_worlds, model):
    row = getattr(operational_worlds[0].world, model.__tablename__)[0]
    payload = record_payload(row)
    # Change surrogate PK so this verifies the business UQ rather than the PK.
    identity = next(c.key for c in model.__table__.primary_key if c.key != 'dataset_version_id')
    payload[identity] = uuid4()
    with pytest.raises(IntegrityError) as caught:
        database_connection.execute(insert(model), payload)
    assert caught.value.orig.sqlstate == '23505'


FK_CASES = [(m, fk) for m in OPERATIONAL_MODELS for fk in m.__table__.foreign_key_constraints if len(fk.elements) > 1]


@pytest.mark.parametrize('model,fk', FK_CASES, ids=[m.__tablename__ + '-' + fk.name for m, fk in FK_CASES])
def test_operational_dataset_scoped_fk(database_connection, operational_worlds, model, fk):
    first, other = operational_worlds
    row = getattr(first.world, model.__tablename__)[0]
    target = fk.elements[0].column.table
    remote = database_connection.execute(select(*(e.column for e in fk.elements)).where(target.c.dataset_version_id == other.dataset_version_id)).first()
    assert remote is not None
    values = {e.parent.key: remote[i] for i, e in enumerate(fk.elements) if i}
    with pytest.raises(IntegrityError) as caught:
        database_connection.execute(update(model).where(*(getattr(model, c.key) == getattr(row, c.key) for c in model.__table__.primary_key)).values(values))
    assert caught.value.orig.sqlstate == '23503'


def remove_operational_row(connection, table, row):
    for child in OPERATIONAL_MODELS:
        for fk in child.__table__.foreign_key_constraints:
            if fk.elements[0].column.table is table:
                conditions = [e.parent == row[e.column.key] for e in fk.elements]
                for dependent in connection.execute(select(child.__table__).where(*conditions)).mappings().all():
                    remove_operational_row(connection, child.__table__, dependent)
    connection.execute(delete(table).where(*(c == row[c.key] for c in table.primary_key)))


@pytest.mark.parametrize('model', OPERATIONAL_MODELS)
def test_partial_operational_world_rejected(database_connection, operational_worlds, model):
    did = operational_worlds[0].dataset_version_id
    row = database_connection.execute(select(model.__table__).where(model.dataset_version_id == did)).mappings().first()
    remove_operational_row(database_connection, model.__table__, row)
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises(OperationalEvidenceError, match='INCOMPLETE_OPERATIONAL_EVIDENCE'):
            generate_operational(session, did)


@pytest.mark.parametrize('model,field,value,message', [
    (ProjectCustomer, 'relationship_type', 'SECONDARY', 'INCOMPLETE_MASTER_WORLD'),
    (PoLineSchedule, 'schedule_qty', 999999, 'INCOMPLETE_PROCUREMENT_WORLD'),
    (ScenarioTruth, 'stockpile_flag', 'toggle', 'INCOMPLETE_SCENARIO_WORLD'),
    (DemandSignalPoint, 'demand_qty', 999999, 'INCOMPLETE_EVIDENCE_FOUNDATION'),
    (MonthlyForecast, 'forecast_qty', 999999, 'INCOMPLETE_FORECAST_WORLD'),
])
def test_corrupt_nonempty_prerequisites_rejected(database_connection, operational_worlds, model, field, value, message):
    did = operational_worlds[0].dataset_version_id
    row = database_connection.execute(select(model.__table__).where(model.dataset_version_id == did)).mappings().first()
    if value == 'toggle':
        value = not row[field]
    if model is ProjectCustomer:
        row = database_connection.execute(select(model.__table__).where(model.dataset_version_id == did, model.relationship_type == 'PRIMARY')).mappings().first()
    database_connection.execute(update(model).where(*(getattr(model, c.key) == row[c.key] for c in model.__table__.primary_key)).values({field: value}))
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises(OperationalEvidenceError, match=message):
            generate_operational(session, did)


def test_operational_config_conflict_and_ready_gate(database_connection, operational_worlds):
    did = operational_worlds[0].dataset_version_id
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises(OperationalEvidenceError, match='OPERATIONAL_CONFIG_CONFLICT'):
            generate_operational(session, did, OperationalEvidenceConfig(seed=20260832))
    database_connection.execute(update(DatasetVersion).where(DatasetVersion.dataset_version_id == did).values(status='READY'))
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises(OperationalEvidenceError, match='DATASET_NOT_GENERATING'):
            generate_operational(session, did)


def test_operational_insertion_failure_rolls_back_all_tables(migrated_database):
    with Session(migrated_database) as session:
        did = foundation(session, 76003)
        generate(session, did)
        generate_forecast(session, did)
        with migrated_database.connect() as conn:
            before = upstream_fingerprint(conn, did)
        def fail(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith('INSERT INTO platform.stockpile_forecasts'):
                raise RuntimeError('injected operational failure')
        event.listen(migrated_database, 'before_cursor_execute', fail)
        try:
            with pytest.raises(RuntimeError, match='injected operational failure'):
                generate_operational(session, did)
        finally:
            event.remove(migrated_database, 'before_cursor_execute', fail)
        for model in OPERATIONAL_MODELS:
            assert session.scalar(select(func.count()).select_from(model).where(model.dataset_version_id == did)) == 0
        assert upstream_fingerprint(session.connection(), did) == before
        session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_version_id == did))
        session.commit()


def test_actual_operational_role_permissions(migrated_database, test_database_url, operational_worlds):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    for role in ('generator', 'api', 'evaluator'):
        credentials = make_url(getattr(settings, f'database_url_{role}').get_secret_value())
        engine = create_engine(make_url(test_database_url).set(username=credentials.username, password=credentials.password), isolation_level='AUTOCOMMIT', hide_parameters=True)
        try:
            with engine.connect() as conn:
                assert conn.scalar(text('SELECT current_user')) == 'system_a_' + role
                for model in OPERATIONAL_MODELS:
                    table = 'platform.' + model.__tablename__
                    if role == 'generator':
                        assert conn.execute(text(f'INSERT INTO {table} SELECT * FROM {table} WHERE false')).rowcount == 0
                    elif role == 'api':
                        with pytest.raises(DBAPIError) as caught:
                            conn.execute(text(f'SELECT * FROM {table} LIMIT 1'))
                        assert caught.value.orig.sqlstate == '42501'
                if role == 'api':
                    with pytest.raises(DBAPIError) as caught:
                        conn.execute(text('SELECT * FROM evaluation.scenario_truth LIMIT 1'))
                    assert caught.value.orig.sqlstate == '42501'
                else:
                    conn.execute(text('SELECT * FROM evaluation.scenario_truth LIMIT 1'))
        finally:
            engine.dispose()
