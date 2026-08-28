"""Local, operator-authorized backup/audit for the unfinished Phase 5C demo."""
import argparse
import gzip
import hashlib
import json
import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.core.config import settings

TABLES = ('inventory_snapshots', 'inventory_age_buckets', 'supply_demand_snapshots',
          'supply_demand_components', 'stockpile_versions', 'stockpile_records',
          'stockpile_forecasts', 'stockpile_balance_projections', 'stockpile_inventory_age_buckets')


def fingerprint(connection):
    result = {}
    inspector = inspect(connection)
    for schema in ('platform', 'evaluation'):
        for name in sorted(inspector.get_table_names(schema=schema)):
            # Names come from PostgreSQL's own catalog; quote them as identifiers.
            quoted = connection.dialect.identifier_preparer.quote_identifier
            rows = sorted(connection.scalars(text(
                f'SELECT row_to_json(t)::text FROM {quoted(schema)}.{quoted(name)} t')))
            result[f'{schema}.{name}'] = {'count': len(rows), 'hash': hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
    return result


def rebuild(engine, directory):
    """One authorized correction transaction, including DDL, data and upstream audit."""
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    archive = directory / 'operational_rows.json.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['archive_sha256']:
        raise ValueError('BACKUP_CHECKSUM_MISMATCH')
    from app.services.operational_evidence_generation import OperationalEvidenceGenerationService
    from app.generators.operational_evidence.cli import summary
    from app.models.platform import DatasetVersion
    from sqlalchemy import select
    with engine.begin() as connection:
        datasets = connection.execute(text('SELECT dataset_version_id, version_name, status FROM platform.dataset_versions FOR UPDATE')).all()
        if len(datasets) != 1 or datasets[0][1:] != ('demo-master-v1', 'GENERATING'):
            raise ValueError('REBUILD_ONLY_SINGLE_GENERATING_DEMO')
        if connection.scalar(text('SELECT version_num FROM alembic_version')) != '010_operational_evidence':
            raise ValueError('REBUILD_REQUIRES_DRAFT_010')
        before = fingerprint(connection)
        if before != manifest['tables']:
            raise ValueError('DATABASE_CHANGED_SINCE_BACKUP')
        # This explicit list cannot affect any upstream table. No CASCADE drops.
        for name in reversed(TABLES):
            connection.execute(text(f'DROP TABLE platform.{name}'))
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/010_operational_evidence.py'
        spec = importlib.util.spec_from_file_location('corrected_operational_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        connection.exec_driver_sql((Path(__file__).resolve().parents[1] / 'db/bootstrap/002_grants.sql').read_text(encoding='utf-8'))
        with Session(connection, join_transaction_mode='create_savepoint', expire_on_commit=False) as session:
            result = OperationalEvidenceGenerationService(session).generate(datasets[0][0])
        after = fingerprint(connection)
        for key, value in before.items():
            if key not in {'platform.' + t for t in TABLES} and after.get(key) != value:
                raise ValueError('UPSTREAM_CHANGED_DURING_REBUILD')
        rendered = summary(result)
    (directory / 'rebuild_summary.json').write_text(json.dumps(rendered, indent=2), encoding='utf-8')
    print(json.dumps({'rebuild_committed': True, 'upstream_unchanged': True, **rendered}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['backup', 'audit', 'rebuild'])
    parser.add_argument('--directory', required=True)
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    allowed = (Path(__file__).resolve().parents[2] / 'data' / 'synthetic').resolve()
    if not directory.is_relative_to(allowed) or directory == allowed:
        raise ValueError('BACKUP_MUST_BE_IN_IGNORED_SYNTHETIC_SUBDIRECTORY')
    engine = create_engine(settings.database_url_owner.get_secret_value(), hide_parameters=True)
    if args.mode == 'rebuild':
        try:
            rebuild(engine, directory)
        finally:
            engine.dispose()
        return
    with engine.connect() as connection:
        connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        fingerprints = fingerprint(connection)
        if args.mode == 'audit':
            before = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))['tables']
            changed = [key for key, value in before.items() if key not in {'platform.' + t for t in TABLES} and fingerprints.get(key) != value]
            if changed:
                raise ValueError('UPSTREAM_CHANGED: ' + ','.join(changed))
            print(json.dumps({'upstream_unchanged': True, 'table_count': len(fingerprints)}))
            return
        directory.mkdir(parents=True, exist_ok=False)
        payload = {name: list(connection.scalars(text(f'SELECT row_to_json(t)::text FROM platform.{name} t'))) for name in TABLES}
        archive = directory / 'operational_rows.json.gz'
        with gzip.open(archive, 'wt', encoding='utf-8') as handle:
            json.dump(payload, handle)
        with gzip.open(archive, 'rt', encoding='utf-8') as handle:
            assert json.load(handle) == payload
        manifest = {'tables': fingerprints, 'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                    'revision': connection.scalar(text('SELECT version_num FROM alembic_version'))}
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(json.dumps({'backup_verified': True, 'rows': sum(len(v) for v in payload.values()), 'archive_sha256': manifest['archive_sha256']}))
    engine.dispose()


if __name__ == '__main__':
    main()
