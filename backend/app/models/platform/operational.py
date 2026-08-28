"""Normalized operational evidence; no diagnosis or evaluation labels."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.models.base import Base


def table(name, key, *items):
    columns = [
        sa.Column('dataset_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(key, postgresql.UUID(as_uuid=True), nullable=False), *items,
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('dataset_version_id', key),
        sa.ForeignKeyConstraint(['dataset_version_id'], ['platform.dataset_versions.dataset_version_id'], ondelete='CASCADE'),
    ]
    return sa.Table(name, Base.metadata, *columns, schema='platform')


inventory_snapshots = table('inventory_snapshots', 'inventory_snapshot_id',
    sa.Column('snapshot_date', sa.Date, nullable=False),
    sa.Column('material_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('material_mpm_assignment_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('on_hand_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('available_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('quality_hold_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('blocked_qty', sa.Numeric(20, 4), nullable=False),
    sa.ForeignKeyConstraint(["dataset_version_id","material_id"], ["platform.materials.dataset_version_id","platform.materials.material_id"], ondelete='RESTRICT', name='fk_op_0_0'),
    sa.ForeignKeyConstraint(["dataset_version_id","organization_id"], ["platform.organizations.dataset_version_id","platform.organizations.organization_id"], ondelete='RESTRICT', name='fk_op_0_1'),
    sa.ForeignKeyConstraint(["dataset_version_id","material_mpm_assignment_id"], ["platform.material_mpm_assignments.dataset_version_id","platform.material_mpm_assignments.material_mpm_assignment_id"], ondelete='RESTRICT', name='fk_op_0_2'),
    sa.UniqueConstraint("dataset_version_id", "material_id", name='uq_op_0_0'),
    sa.UniqueConstraint("dataset_version_id", "snapshot_date", "material_id", "organization_id", name='uq_op_0_1'),
    sa.CheckConstraint("on_hand_qty = available_qty + quality_hold_qty + blocked_qty", name='op_0_0'),
    sa.CheckConstraint("on_hand_qty >= 0 AND available_qty >= 0 AND quality_hold_qty >= 0 AND blocked_qty >= 0", name='op_0_1'))

inventory_age_buckets = table('inventory_age_buckets', 'inventory_age_bucket_id',
    sa.Column('inventory_snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('age_threshold_days', sa.Integer, nullable=False),
    sa.Column('age_qty', sa.Numeric(20, 4), nullable=False),
    sa.ForeignKeyConstraint(["dataset_version_id","inventory_snapshot_id"], ["platform.inventory_snapshots.dataset_version_id","platform.inventory_snapshots.inventory_snapshot_id"], ondelete='RESTRICT', name='fk_op_1_0'),
    sa.UniqueConstraint("dataset_version_id", "inventory_snapshot_id", "age_threshold_days", name='uq_op_1_0'),
    sa.CheckConstraint("age_threshold_days > 0 AND age_qty >= 0", name='op_1_0'))

supply_demand_snapshots = table('supply_demand_snapshots', 'supply_demand_snapshot_id',
    sa.Column('snapshot_date', sa.Date, nullable=False),
    sa.Column('material_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('all_supply_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('actual_demand_total_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('supply_demand_surplus_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('trial_all_supply_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('trial_actual_demand_total_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('trial_supply_demand_surplus_qty', sa.Numeric(20, 4), nullable=False),
    sa.ForeignKeyConstraint(["dataset_version_id","material_id"], ["platform.materials.dataset_version_id","platform.materials.material_id"], ondelete='RESTRICT', name='fk_op_2_0'),
    sa.ForeignKeyConstraint(["dataset_version_id","organization_id"], ["platform.organizations.dataset_version_id","platform.organizations.organization_id"], ondelete='RESTRICT', name='fk_op_2_1'),
    sa.UniqueConstraint("dataset_version_id", "material_id", name='uq_op_2_0'),
    sa.UniqueConstraint("dataset_version_id", "snapshot_date", "material_id", "organization_id", name='uq_op_2_1'),
    sa.CheckConstraint("all_supply_qty >= 0 AND actual_demand_total_qty >= 0 AND trial_all_supply_qty >= 0 AND trial_actual_demand_total_qty >= 0", name='op_2_0'),
    sa.CheckConstraint("supply_demand_surplus_qty = all_supply_qty - actual_demand_total_qty", name='op_2_1'),
    sa.CheckConstraint("trial_supply_demand_surplus_qty = trial_all_supply_qty - trial_actual_demand_total_qty", name='op_2_2'),
    sa.CheckConstraint("trial_all_supply_qty <= all_supply_qty AND trial_actual_demand_total_qty <= actual_demand_total_qty", name='op_2_3'))

supply_demand_components = table('supply_demand_components', 'supply_demand_component_id',
    sa.Column('supply_demand_snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('material_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('component_key', sa.String(200), nullable=False),
    sa.Column('component_type', sa.String(200), nullable=False),
    sa.Column('component_side', sa.String(200), nullable=False),
    sa.Column('organization_type_scope', sa.String(200), nullable=False),
    sa.Column('source_domain', sa.String(200), nullable=False),
    sa.Column('component_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('inventory_snapshot_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('po_line_schedule_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('demand_signal_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('source_forecast_version_id', postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column('period_start', sa.Date, nullable=True),
    sa.Column('period_end', sa.Date, nullable=True),
    sa.ForeignKeyConstraint(["dataset_version_id","supply_demand_snapshot_id"], ["platform.supply_demand_snapshots.dataset_version_id","platform.supply_demand_snapshots.supply_demand_snapshot_id"], ondelete='RESTRICT', name='fk_op_3_0'),
    sa.ForeignKeyConstraint(["dataset_version_id","material_id"], ["platform.materials.dataset_version_id","platform.materials.material_id"], ondelete='RESTRICT', name='fk_op_3_1'),
    sa.ForeignKeyConstraint(["dataset_version_id","organization_id"], ["platform.organizations.dataset_version_id","platform.organizations.organization_id"], ondelete='RESTRICT', name='fk_op_3_2'),
    sa.ForeignKeyConstraint(["dataset_version_id","inventory_snapshot_id"], ["platform.inventory_snapshots.dataset_version_id","platform.inventory_snapshots.inventory_snapshot_id"], ondelete='RESTRICT', name='fk_op_3_3'),
    sa.ForeignKeyConstraint(["dataset_version_id","po_line_schedule_id"], ["platform.po_line_schedules.dataset_version_id","platform.po_line_schedules.po_line_schedule_id"], ondelete='RESTRICT', name='fk_op_3_4'),
    sa.ForeignKeyConstraint(["dataset_version_id","project_id"], ["platform.projects.dataset_version_id","platform.projects.project_id"], ondelete='RESTRICT', name='fk_op_3_5'),
    sa.ForeignKeyConstraint(["dataset_version_id","demand_signal_id"], ["platform.demand_signals.dataset_version_id","platform.demand_signals.demand_signal_id"], ondelete='RESTRICT', name='fk_op_3_6'),
    sa.ForeignKeyConstraint(["dataset_version_id","source_forecast_version_id"], ["platform.forecast_versions.dataset_version_id","platform.forecast_versions.forecast_version_id"], ondelete='RESTRICT', name='fk_op_3_7'),
    sa.UniqueConstraint("dataset_version_id", "supply_demand_snapshot_id", "component_key", name='uq_op_3_0'),
    sa.CheckConstraint("organization_type_scope IN ('TRIAL','MASS_PRODUCTION')", name='op_3_0'),
    sa.CheckConstraint("component_side IN ('SUPPLY','DEMAND') AND component_qty >= 0", name='op_3_1'),
    sa.CheckConstraint("(component_side='SUPPLY' AND component_type IN ('ON_HAND_AVAILABLE','OPEN_PO','IN_TRANSIT','OTHER_CONFIRMED_SUPPLY')) OR (component_side='DEMAND' AND component_type IN ('WORK_ORDER_DEMAND','PLAN_DEMAND','FORECAST_DEMAND','OTHER_ACTUAL_DEMAND'))", name='op_3_2'),
    sa.CheckConstraint("component_side <> 'DEMAND' OR (demand_signal_id IS NOT NULL AND project_id IS NOT NULL AND source_forecast_version_id IS NOT NULL AND period_start IS NOT NULL AND period_end >= period_start)", name='op_3_3'),
    sa.CheckConstraint("component_type NOT IN ('OPEN_PO','IN_TRANSIT') OR po_line_schedule_id IS NOT NULL", name='op_3_4'),
    sa.CheckConstraint("component_type <> 'ON_HAND_AVAILABLE' OR inventory_snapshot_id IS NOT NULL", name='op_3_5'))

stockpile_versions = table('stockpile_versions', 'stockpile_version_id',
    sa.Column('version_name', sa.String(200), nullable=False),
    sa.Column('version_date', sa.Date, nullable=False),
    sa.Column('sequence_no', sa.Integer, nullable=False),
    sa.Column('is_valid', sa.Boolean, nullable=False),
    sa.Column('source_name', sa.String(200), nullable=False),
    sa.UniqueConstraint("dataset_version_id", "version_name", name='uq_op_4_0'),
    sa.UniqueConstraint("dataset_version_id", "version_date", "sequence_no", name='uq_op_4_1'),
    sa.CheckConstraint("sequence_no > 0", name='op_4_0'))

stockpile_records = table('stockpile_records', 'stockpile_record_id',
    sa.Column('stockpile_version_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('material_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('stockpile_tag', sa.String(200), nullable=False),
    sa.Column('stockpile_period_months', sa.Integer, nullable=False),
    sa.Column('target_stockpile_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('actual_stockpile_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('inventory_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('seven_day_demand_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('remaining_current_month_demand_qty', sa.Numeric(20, 4), nullable=False),
    sa.ForeignKeyConstraint(["dataset_version_id","stockpile_version_id"], ["platform.stockpile_versions.dataset_version_id","platform.stockpile_versions.stockpile_version_id"], ondelete='RESTRICT', name='fk_op_5_0'),
    sa.ForeignKeyConstraint(["dataset_version_id","material_id"], ["platform.materials.dataset_version_id","platform.materials.material_id"], ondelete='RESTRICT', name='fk_op_5_1'),
    sa.ForeignKeyConstraint(["dataset_version_id","organization_id"], ["platform.organizations.dataset_version_id","platform.organizations.organization_id"], ondelete='RESTRICT', name='fk_op_5_2'),
    sa.UniqueConstraint("dataset_version_id", "stockpile_version_id", "material_id", name='uq_op_5_0'),
    sa.CheckConstraint("stockpile_period_months BETWEEN 1 AND 6", name='op_5_0'),
    sa.CheckConstraint("target_stockpile_qty >= 0 AND actual_stockpile_qty >= 0 AND inventory_qty >= 0 AND seven_day_demand_qty >= 0 AND remaining_current_month_demand_qty >= 0", name='op_5_1'))

stockpile_forecasts = table('stockpile_forecasts', 'stockpile_forecast_id',
    sa.Column('stockpile_version_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('material_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('forecast_month', sa.Date, nullable=False),
    sa.Column('source_observed_on', sa.Date, nullable=False),
    sa.Column('demand_lineage', postgresql.JSONB, nullable=False),
    sa.Column('forecast_qty', sa.Numeric(20, 4), nullable=False),
    sa.ForeignKeyConstraint(["dataset_version_id","stockpile_version_id","material_id"], ["platform.stockpile_records.dataset_version_id","platform.stockpile_records.stockpile_version_id","platform.stockpile_records.material_id"], ondelete='RESTRICT', name='fk_op_6_0'),
    sa.UniqueConstraint("dataset_version_id", "stockpile_version_id", "material_id", "forecast_month", name='uq_op_6_0'),
    sa.CheckConstraint("forecast_qty >= 0 AND extract(day from forecast_month) = 1", name='op_6_0'),
    sa.CheckConstraint("jsonb_typeof(demand_lineage) = 'array' AND jsonb_array_length(demand_lineage) > 0", name='op_6_1'))

stockpile_balance_projections = table('stockpile_balance_projections', 'stockpile_balance_projection_id',
    sa.Column('stockpile_version_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('material_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('forecast_month', sa.Date, nullable=False),
    sa.Column('opening_available_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('planned_inbound_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('demand_qty', sa.Numeric(20, 4), nullable=False),
    sa.Column('closing_projected_qty', sa.Numeric(20, 4), nullable=False),
    sa.ForeignKeyConstraint(["dataset_version_id","stockpile_version_id","material_id"], ["platform.stockpile_records.dataset_version_id","platform.stockpile_records.stockpile_version_id","platform.stockpile_records.material_id"], ondelete='RESTRICT', name='fk_op_7_0'),
    sa.UniqueConstraint("dataset_version_id", "stockpile_version_id", "material_id", "forecast_month", name='uq_op_7_0'),
    sa.CheckConstraint("planned_inbound_qty >= 0 AND demand_qty >= 0 AND extract(day from forecast_month) = 1", name='op_7_0'),
    sa.CheckConstraint("closing_projected_qty = opening_available_qty + planned_inbound_qty - demand_qty", name='op_7_1'))

stockpile_inventory_age_buckets = table('stockpile_inventory_age_buckets', 'stockpile_inventory_age_bucket_id',
    sa.Column('stockpile_version_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('material_id', postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column('age_threshold_days', sa.Integer, nullable=False),
    sa.Column('age_qty', sa.Numeric(20, 4), nullable=False),
    sa.ForeignKeyConstraint(["dataset_version_id","stockpile_version_id","material_id"], ["platform.stockpile_records.dataset_version_id","platform.stockpile_records.stockpile_version_id","platform.stockpile_records.material_id"], ondelete='RESTRICT', name='fk_op_8_0'),
    sa.UniqueConstraint("dataset_version_id", "stockpile_version_id", "material_id", "age_threshold_days", name='uq_op_8_0'),
    sa.CheckConstraint("age_threshold_days > 0 AND age_qty >= 0", name='op_8_0'))

class InventorySnapshot(Base):
    __tablename__ = 'inventory_snapshots'
    __table__ = inventory_snapshots


class InventoryAgeBucket(Base):
    __tablename__ = 'inventory_age_buckets'
    __table__ = inventory_age_buckets


class SupplyDemandSnapshot(Base):
    __tablename__ = 'supply_demand_snapshots'
    __table__ = supply_demand_snapshots


class SupplyDemandComponent(Base):
    __tablename__ = 'supply_demand_components'
    __table__ = supply_demand_components


class StockpileVersion(Base):
    __tablename__ = 'stockpile_versions'
    __table__ = stockpile_versions


class StockpileRecord(Base):
    __tablename__ = 'stockpile_records'
    __table__ = stockpile_records


class StockpileForecast(Base):
    __tablename__ = 'stockpile_forecasts'
    __table__ = stockpile_forecasts


class StockpileBalanceProjection(Base):
    __tablename__ = 'stockpile_balance_projections'
    __table__ = stockpile_balance_projections


class StockpileInventoryAgeBucket(Base):
    __tablename__ = 'stockpile_inventory_age_buckets'
    __table__ = stockpile_inventory_age_buckets

OPERATIONAL_MODELS = (InventorySnapshot, InventoryAgeBucket, SupplyDemandSnapshot, SupplyDemandComponent, StockpileVersion, StockpileRecord, StockpileForecast, StockpileBalanceProjection, StockpileInventoryAgeBucket)
