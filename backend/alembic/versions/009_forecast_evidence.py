"""Create normalized versioned monthly and weekly source forecast facts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '009_forecast_evidence'
down_revision = '008_evidence_foundation'
branch_labels = None
depends_on = None


def _uuid(name):
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def _fk(field, table, target=None):
    return sa.ForeignKeyConstraint(['dataset_version_id', field],
                                   [f'platform.{table}.dataset_version_id', f'platform.{table}.{target or field}'],
                                   name=f'fk_fc_{field}_{table}', ondelete='RESTRICT')


def _create(name, keys, *items):
    op.create_table(name, _uuid('dataset_version_id'), *items,
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.PrimaryKeyConstraint('dataset_version_id', *keys),
                    sa.ForeignKeyConstraint(['dataset_version_id'], ['platform.dataset_versions.dataset_version_id'], ondelete='CASCADE'),
                    schema='platform')


def _index(name, table, *fields, **kwargs):
    op.create_index(name, table, ['dataset_version_id', *fields], schema='platform', **kwargs)


def upgrade():
    _create('forecast_versions', ['forecast_version_id'], _uuid('forecast_version_id'),
            sa.Column('version_name', sa.String(100), nullable=False),
            sa.Column('version_date', sa.Date, nullable=False),
            sa.Column('sequence_no', sa.Integer, nullable=False),
            sa.Column('is_valid', sa.Boolean, nullable=False),
            sa.Column('description', sa.String(200)),
            sa.UniqueConstraint('dataset_version_id', 'version_name', name='uq_fc_version_name'),
            sa.UniqueConstraint('dataset_version_id', 'version_date', 'sequence_no', name='uq_fc_version_sequence'),
            sa.CheckConstraint('sequence_no > 0', name='sequence_positive'))
    _index('ix_fc_version_date', 'forecast_versions', 'version_date')
    _create('monthly_forecasts', ['forecast_version_id', 'material_id', 'project_id', 'forecast_month'],
            *(_uuid(f) for f in ('forecast_version_id', 'material_id', 'project_id', 'demand_signal_id')),
            sa.Column('forecast_month', sa.Date, nullable=False),
            sa.Column('forecast_qty', sa.Numeric(20, 4), nullable=False),
            sa.Column('forecast_source', sa.String(64), nullable=False),
            _fk('forecast_version_id', 'forecast_versions'), _fk('material_id', 'materials'),
            _fk('project_id', 'projects'), _fk('demand_signal_id', 'demand_signals'),
            sa.CheckConstraint('extract(day from forecast_month) = 1', name='month_first'),
            sa.CheckConstraint('forecast_qty >= 0', name='quantity_nonnegative'))
    _index('ix_fc_month_pair', 'monthly_forecasts', 'material_id', 'project_id', 'forecast_version_id')
    _index('ix_fc_month_signal', 'monthly_forecasts', 'demand_signal_id')
    _index('ix_fc_month_project', 'monthly_forecasts', 'project_id')
    _create('material_project_shipments', ['material_project_shipment_id'],
            *(_uuid(f) for f in ('material_project_shipment_id', 'material_id', 'project_id', 'demand_signal_id')),
            sa.Column('shipment_date', sa.Date, nullable=False),
            sa.Column('shipped_qty', sa.Numeric(20, 4), nullable=False),
            _fk('material_id', 'materials'), _fk('project_id', 'projects'), _fk('demand_signal_id', 'demand_signals'),
            sa.CheckConstraint('shipped_qty >= 0', name='shipment_nonnegative'))
    _index('ix_fc_ship_pair_date', 'material_project_shipments', 'material_id', 'project_id', 'shipment_date')
    _index('ix_fc_ship_project', 'material_project_shipments', 'project_id')
    _index('ix_fc_ship_signal', 'material_project_shipments', 'demand_signal_id')
    _create('weekly_forecast_snapshots', ['weekly_forecast_snapshot_id'], _uuid('weekly_forecast_snapshot_id'),
            sa.Column('snapshot_date', sa.Date, nullable=False), _uuid('source_forecast_version_id'),
            sa.Column('is_latest', sa.Boolean, nullable=False),
            _fk('source_forecast_version_id', 'forecast_versions', 'forecast_version_id'),
            sa.UniqueConstraint('dataset_version_id', 'snapshot_date', name='uq_fc_snapshot_date'))
    _index('uq_fc_latest_snapshot', 'weekly_forecast_snapshots', unique=True, postgresql_where=sa.text('is_latest'))
    _index('ix_fc_snapshot_source', 'weekly_forecast_snapshots', 'source_forecast_version_id')
    for project in (True, False):
        name = 'weekly_project_forecasts' if project else 'weekly_forecasts'
        tag = 'project' if project else 'material'
        keys = ['weekly_forecast_snapshot_id', 'material_id'] + (['project_id'] if project else [])
        extra = ([_uuid('project_id'), _uuid('demand_signal_id'), _fk('project_id', 'projects'),
                  _fk('demand_signal_id', 'demand_signals')] if project else [])
        _create(name, [*keys, 'week_start_date'],
                _uuid('weekly_forecast_snapshot_id'), _uuid('material_id'), _uuid('organization_id'),
                sa.Column('week_index', sa.Integer, nullable=False),
                sa.Column('week_start_date', sa.Date, nullable=False),
                sa.Column('forecast_qty', sa.Numeric(20, 4), nullable=False), *extra,
                _fk('weekly_forecast_snapshot_id', 'weekly_forecast_snapshots'),
                _fk('material_id', 'materials'), _fk('organization_id', 'organizations'),
                sa.UniqueConstraint('dataset_version_id', *keys, 'week_index', name=f'uq_fc_week_{tag}_index'),
                sa.CheckConstraint('week_index BETWEEN 1 AND 13', name='week_index_range'),
                sa.CheckConstraint('extract(isodow from week_start_date) = 1', name='monday_start'),
                sa.CheckConstraint('forecast_qty >= 0', name='quantity_nonnegative'))
        _index(f'ix_fc_week_{tag}_material', name, 'material_id', 'week_start_date')
        _index(f'ix_fc_week_{tag}_org', name, 'organization_id')
        if project:
            _index('ix_fc_week_project_signal', name, 'demand_signal_id')
            _index('ix_fc_week_project_project', name, 'project_id')


def downgrade():
    for name in ('weekly_forecasts', 'weekly_project_forecasts', 'weekly_forecast_snapshots',
                 'material_project_shipments', 'monthly_forecasts', 'forecast_versions'):
        op.drop_table(name, schema='platform')
