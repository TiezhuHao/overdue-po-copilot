"""Normalized source forecast facts; no diagnostic fields."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.platform.evidence_foundation import _dataset_fk


class ForecastRow:
    dataset_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _fk(field, table, target=None):
    return ForeignKeyConstraint(['dataset_version_id', field],
                                [f'platform.{table}.dataset_version_id', f'platform.{table}.{target or field}'],
                                name=f'fk_fc_{field}_{table}', ondelete='RESTRICT')


class ForecastVersion(ForecastRow, Base):
    __tablename__ = 'forecast_versions'
    __table_args__ = (
        PrimaryKeyConstraint('dataset_version_id', 'forecast_version_id'), _dataset_fk(),
        UniqueConstraint('dataset_version_id', 'version_name', name='uq_fc_version_name'),
        UniqueConstraint('dataset_version_id', 'version_date', 'sequence_no', name='uq_fc_version_sequence'),
        CheckConstraint('sequence_no > 0', name='sequence_positive'),
        Index('ix_fc_version_date', 'dataset_version_id', 'version_date'), {'schema': 'platform'},
    )
    forecast_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    version_name: Mapped[str] = mapped_column(String(100), nullable=False)
    version_date: Mapped[date] = mapped_column(Date, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200))


class MonthlyForecast(ForecastRow, Base):
    __tablename__ = 'monthly_forecasts'
    __table_args__ = (
        PrimaryKeyConstraint('dataset_version_id', 'forecast_version_id', 'material_id', 'project_id', 'forecast_month'),
        _dataset_fk(), _fk('forecast_version_id', 'forecast_versions'), _fk('material_id', 'materials'),
        _fk('project_id', 'projects'), _fk('demand_signal_id', 'demand_signals'),
        CheckConstraint('extract(day from forecast_month) = 1', name='month_first'),
        CheckConstraint('forecast_qty >= 0', name='quantity_nonnegative'),
        Index('ix_fc_month_pair', 'dataset_version_id', 'material_id', 'project_id', 'forecast_version_id'),
        Index('ix_fc_month_signal', 'dataset_version_id', 'demand_signal_id'),
        Index('ix_fc_month_project', 'dataset_version_id', 'project_id'), {'schema': 'platform'},
    )
    forecast_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    demand_signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    forecast_month: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    forecast_source: Mapped[str] = mapped_column(String(64), nullable=False)


class MaterialProjectShipment(ForecastRow, Base):
    __tablename__ = 'material_project_shipments'
    __table_args__ = (
        PrimaryKeyConstraint('dataset_version_id', 'material_project_shipment_id'), _dataset_fk(),
        _fk('material_id', 'materials'), _fk('project_id', 'projects'), _fk('demand_signal_id', 'demand_signals'),
        CheckConstraint('shipped_qty >= 0', name='shipment_nonnegative'),
        Index('ix_fc_ship_pair_date', 'dataset_version_id', 'material_id', 'project_id', 'shipment_date'),
        Index('ix_fc_ship_project', 'dataset_version_id', 'project_id'),
        Index('ix_fc_ship_signal', 'dataset_version_id', 'demand_signal_id'), {'schema': 'platform'},
    )
    material_project_shipment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    demand_signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    shipment_date: Mapped[date] = mapped_column(Date, nullable=False)
    shipped_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class WeeklyForecastSnapshot(ForecastRow, Base):
    __tablename__ = 'weekly_forecast_snapshots'
    __table_args__ = (
        PrimaryKeyConstraint('dataset_version_id', 'weekly_forecast_snapshot_id'), _dataset_fk(),
        _fk('source_forecast_version_id', 'forecast_versions', 'forecast_version_id'),
        UniqueConstraint('dataset_version_id', 'snapshot_date', name='uq_fc_snapshot_date'),
        Index('uq_fc_latest_snapshot', 'dataset_version_id', unique=True, postgresql_where=text('is_latest')),
        Index('ix_fc_snapshot_source', 'dataset_version_id', 'source_forecast_version_id'), {'schema': 'platform'},
    )
    weekly_forecast_snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_forecast_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False)


class WeeklyColumns:
    weekly_forecast_snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    material_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    week_index: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_qty: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


def _weekly_constraints(project):
    keys = ['dataset_version_id', 'weekly_forecast_snapshot_id', 'material_id'] + (['project_id'] if project else [])
    tag = 'project' if project else 'material'
    return (
        PrimaryKeyConstraint(*keys, 'week_start_date'), _dataset_fk(),
        _fk('weekly_forecast_snapshot_id', 'weekly_forecast_snapshots'),
        _fk('material_id', 'materials'), _fk('organization_id', 'organizations'),
        UniqueConstraint(*keys, 'week_index', name=f'uq_fc_week_{tag}_index'),
        CheckConstraint('week_index BETWEEN 1 AND 13', name='week_index_range'),
        CheckConstraint('extract(isodow from week_start_date) = 1', name='monday_start'),
        CheckConstraint('forecast_qty >= 0', name='quantity_nonnegative'),
        Index(f'ix_fc_week_{tag}_material', 'dataset_version_id', 'material_id', 'week_start_date'),
        Index(f'ix_fc_week_{tag}_org', 'dataset_version_id', 'organization_id'),
    )


class WeeklyProjectForecast(WeeklyColumns, ForecastRow, Base):
    __tablename__ = 'weekly_project_forecasts'
    __table_args__ = _weekly_constraints(True) + (
        _fk('project_id', 'projects'), _fk('demand_signal_id', 'demand_signals'),
        Index('ix_fc_week_project_signal', 'dataset_version_id', 'demand_signal_id'),
        Index('ix_fc_week_project_project', 'dataset_version_id', 'project_id'), {'schema': 'platform'},
    )
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    demand_signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class WeeklyForecast(WeeklyColumns, ForecastRow, Base):
    __tablename__ = 'weekly_forecasts'
    __table_args__ = _weekly_constraints(False) + ({'schema': 'platform'},)


FORECAST_MODELS = (ForecastVersion, MonthlyForecast, MaterialProjectShipment, WeeklyForecastSnapshot, WeeklyProjectForecast, WeeklyForecast)
