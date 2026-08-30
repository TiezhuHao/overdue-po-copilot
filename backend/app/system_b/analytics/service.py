"""Thin canonical-data orchestration; callers own retrieval, never this service."""

from app.system_b.analytics.calculations import (
    calculate_consumption, calculate_coverage, calculate_po_aging, calculate_po_consumption,
)
from app.system_b.analytics.models import MaterialForecastAnalytics, PurchaseOrderAnalytics
from app.system_b.models import PurchaseOrder, WeeklyForecastSnapshot


class AnalyticsService:
    @staticmethod
    def analyze_purchase_order(
        po: PurchaseOrder, forecast: WeeklyForecastSnapshot | None = None,
    ) -> PurchaseOrderAnalytics:
        return PurchaseOrderAnalytics(
            dataset_version_id=po.dataset_version_id, snapshot_date=po.snapshot_date,
            material_code=po.material_code, material_id=po.material_id,
            po_number=po.po_number, po_line_number=po.po_line_number, shipment_number=po.shipment_number,
            aging=calculate_po_aging(po.order_date, po.material_lt_days, as_of_date=po.snapshot_date),
            consumption=calculate_po_consumption(po, forecast),
        )

    @staticmethod
    def analyze_material_forecast(forecast: WeeklyForecastSnapshot) -> MaterialForecastAnalytics:
        # Both numerators and all 13 buckets belong to this single canonical row.
        return MaterialForecastAnalytics(
            dataset_version_id=forecast.dataset_version_id, snapshot_date=forecast.snapshot_date,
            material_code=forecast.material_code, material_id=forecast.material_id,
            consumption=calculate_consumption(forecast.open_po_qty, forecast.weeks),
            coverage=calculate_coverage(forecast.good_subinventory_qty, forecast.weeks),
        )
