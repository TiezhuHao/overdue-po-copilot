from uuid import uuid4

import pytest
from sqlalchemy import delete, event, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.generators.evidence_foundation.world import record_payload
from app.generators.forecasts.config import ForecastGenerationConfig
from app.models.platform import DatasetVersion, ProjectCustomer, PoLineSchedule
from app.models.evaluation import ScenarioTruth
from app.models.platform.evidence_foundation import DemandSignalPoint
from app.models.platform.forecasts import FORECAST_MODELS, ForecastVersion, MaterialProjectShipment, MonthlyForecast, WeeklyForecast, WeeklyForecastSnapshot, WeeklyProjectForecast
from app.services.forecast_generation import ForecastGenerationError, ForecastGenerationService
from app.services.evidence_foundation_generation import EvidenceFoundationError
from tests.test_evidence_foundation_integration import PC, SC, foundation, generate

pytestmark = pytest.mark.integration
FC = ForecastGenerationConfig()


def generate_forecast(session, dataset_id):
    return ForecastGenerationService(session).generate(dataset_id, FC, procurement_config=PC, scenario_config=SC)


@pytest.fixture(scope='module')
def forecast_worlds(migrated_database):
    results = []
    try:
        with Session(migrated_database) as session:
            for seed in (75001, 75002):
                did = foundation(session, seed)
                results.append((did, None))
                generate(session, did)
                results[-1] = (did, generate_forecast(session, did))
        yield results[0][1], results[1][1]
    finally:
        with Session(migrated_database) as session:
            for did, _ in results:
                session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_version_id == did))
            session.commit()


def test_forecast_roundtrip_idempotency(migrated_database, forecast_worlds):
    first, _ = forecast_worlds
    with Session(migrated_database) as session:
        reused = generate_forecast(session, first.dataset_version_id)
        assert reused.reused and reused.forecast_content_hash == first.forecast_content_hash
        dataset = session.get(DatasetVersion, first.dataset_version_id)
        assert dataset.status == 'GENERATING' and dataset.business_content_hash is None


def test_forecast_model_migration_agreement(migrated_database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.models import Base
    names = {m.__tablename__ for m in FORECAST_MODELS}

    def included(obj, name, type_, reflected, compare_to):
        table = obj if type_ == 'table' else getattr(obj, 'table', None)
        return table is not None and table.name in names

    with migrated_database.connect() as conn:
        context = MigrationContext.configure(conn, opts={'include_schemas': True, 'include_object': included})
        assert compare_metadata(context, Base.metadata) == []


@pytest.mark.parametrize('model,field,value', [
    (ForecastVersion, 'sequence_no', 0), (MonthlyForecast, 'forecast_qty', -1),
    (MonthlyForecast, 'forecast_month', '2026-08-02'), (MaterialProjectShipment, 'shipped_qty', -1),
    (WeeklyProjectForecast, 'week_index', 14), (WeeklyForecast, 'week_index', 0),
    (WeeklyForecast, 'forecast_qty', -1), (WeeklyProjectForecast, 'week_start_date', '2026-08-25'),
])
def test_postgres_forecast_checks(database_connection, forecast_worlds, model, field, value):
    row = getattr(forecast_worlds[0].world, model.__tablename__)[0]
    keys = [c.key for c in model.__table__.primary_key]
    with pytest.raises(IntegrityError) as error:
        database_connection.execute(update(model).where(*(getattr(model, k) == getattr(row, k) for k in keys)).values({field: value}))
    assert error.value.orig.sqlstate == '23514'


@pytest.mark.parametrize('model', FORECAST_MODELS)
def test_forecast_uniqueness(database_connection, forecast_worlds, model):
    row = getattr(forecast_worlds[0].world, model.__tablename__)[0]
    with pytest.raises(IntegrityError) as error:
        database_connection.execute(insert(model), record_payload(row))
    assert error.value.orig.sqlstate == '23505'


def test_latest_partial_unique_index(database_connection, forecast_worlds):
    from datetime import timedelta
    row = forecast_worlds[0].world.weekly_forecast_snapshots[0]
    payload = record_payload(row)
    payload['weekly_forecast_snapshot_id'] = uuid4()
    payload['snapshot_date'] += timedelta(days=7)
    with pytest.raises(IntegrityError) as error:
        database_connection.execute(insert(WeeklyForecastSnapshot), payload)
    assert error.value.orig.sqlstate == '23505'
    assert error.value.orig.diag.constraint_name == 'uq_fc_latest_snapshot'


FK_CASES = [(m, fk) for m in FORECAST_MODELS for fk in m.__table__.foreign_key_constraints if len(fk.elements) == 2]


@pytest.mark.parametrize('model,fk', FK_CASES, ids=[m.__tablename__ + '-' + fk.elements[1].parent.key for m, fk in FK_CASES])
def test_forecast_dataset_scoped_foreign_keys(database_connection, forecast_worlds, model, fk):
    first, other = forecast_worlds
    row = getattr(first.world, model.__tablename__)[0]
    target = fk.elements[1].column
    foreign_id = database_connection.scalar(select(target).where(target.table.c.dataset_version_id == other.dataset_version_id))
    assert foreign_id is not None
    keys = [c.key for c in model.__table__.primary_key]
    with pytest.raises(IntegrityError) as error:
        database_connection.execute(update(model).where(*(getattr(model, k) == getattr(row, k) for k in keys)).values({fk.elements[1].parent.key: foreign_id}))
    assert error.value.orig.sqlstate == '23503'


@pytest.mark.parametrize('model', FORECAST_MODELS)
def test_partial_forecast_world_rejected(database_connection, forecast_worlds, model):
    first, _ = forecast_worlds
    row = getattr(first.world, model.__tablename__)[0]
    if model is ForecastVersion:
        database_connection.execute(delete(MonthlyForecast).where(MonthlyForecast.dataset_version_id == first.dataset_version_id, MonthlyForecast.forecast_version_id == row.forecast_version_id))
    elif model is WeeklyForecastSnapshot:
        for child in (WeeklyForecast, WeeklyProjectForecast):
            database_connection.execute(delete(child).where(child.dataset_version_id == first.dataset_version_id))
    keys = [c.key for c in model.__table__.primary_key]
    database_connection.execute(delete(model).where(*(getattr(model, k) == getattr(row, k) for k in keys)))
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises(ForecastGenerationError, match='INCOMPLETE_FORECAST_WORLD'):
            generate_forecast(session, first.dataset_version_id)


@pytest.mark.parametrize('model,message', [(ProjectCustomer, 'INCOMPLETE_MASTER_WORLD'), (PoLineSchedule, 'INCOMPLETE_PROCUREMENT_WORLD'),
                                        (ScenarioTruth, 'INCOMPLETE_SCENARIO_WORLD'), (DemandSignalPoint, 'INCOMPLETE_EVIDENCE_FOUNDATION')])
def test_missing_forecast_prerequisites(database_connection, forecast_worlds, model, message):
    did = forecast_worlds[0].dataset_version_id
    key = next(c for c in model.__table__.primary_key if c.key != 'dataset_version_id')
    target = database_connection.scalar(select(key).where(model.dataset_version_id == did))
    database_connection.execute(delete(model).where(model.dataset_version_id == did, key == target))
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises((ForecastGenerationError, EvidenceFoundationError), match=message):
            generate_forecast(session, did)


def test_forecast_config_conflict_and_ready_gate(database_connection, forecast_worlds):
    did = forecast_worlds[0].dataset_version_id
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises(ForecastGenerationError, match='FORECAST_CONFIG_CONFLICT'):
            ForecastGenerationService(session).generate(did, ForecastGenerationConfig(seed=20260831), procurement_config=PC, scenario_config=SC)
    database_connection.execute(update(DatasetVersion).where(DatasetVersion.dataset_version_id == did).values(status='READY'))
    with Session(database_connection, join_transaction_mode='create_savepoint') as session:
        with pytest.raises(ForecastGenerationError, match='DATASET_NOT_GENERATING'):
            generate_forecast(session, did)


def test_forecast_failure_rolls_back_stage(migrated_database):
    with Session(migrated_database) as session:
        did = foundation(session, 75003)
        generate(session, did)

        def reject(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith('INSERT INTO platform.weekly_project_forecasts'):
                raise RuntimeError('injected forecast stage failure')

        event.listen(migrated_database, 'before_cursor_execute', reject)
        try:
            with pytest.raises(RuntimeError, match='injected forecast stage failure'):
                generate_forecast(session, did)
        finally:
            event.remove(migrated_database, 'before_cursor_execute', reject)
        for model in FORECAST_MODELS:
            assert session.scalar(select(func.count()).select_from(model).where(model.dataset_version_id == did)) == 0
        session.execute(delete(DatasetVersion).where(DatasetVersion.dataset_version_id == did))
        session.commit()


def test_actual_forecast_role_permissions(migrated_database, test_database_url, forecast_worlds):
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    for role in ('generator', 'api'):
        credentials = make_url(getattr(settings, f'database_url_{role}').get_secret_value())
        engine = create_engine(make_url(test_database_url).set(username=credentials.username, password=credentials.password), isolation_level='AUTOCOMMIT')
        try:
            with engine.connect() as conn:
                assert conn.scalar(text('SELECT current_user')) == 'system_a_' + role
                for model in FORECAST_MODELS:
                    table = 'platform.' + model.__tablename__
                    if role == 'generator':
                        assert conn.execute(text(f'INSERT INTO {table} SELECT * FROM {table} WHERE false')).rowcount == 0
                    else:
                        with pytest.raises(DBAPIError) as error:
                            conn.execute(text(f'SELECT * FROM {table} LIMIT 1'))
                        assert error.value.orig.sqlstate == '42501'
                if role == 'api':
                    with pytest.raises(DBAPIError) as error:
                        conn.execute(text('SELECT * FROM evaluation.scenario_truth LIMIT 1'))
                    assert error.value.orig.sqlstate == '42501'
        finally:
            engine.dispose()
