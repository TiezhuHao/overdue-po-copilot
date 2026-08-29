"""Read-only report semantic summaries and cross-report reconciliation."""
from hashlib import sha256
import json

from sqlalchemy import text

from app.reporting.view_definitions import CANONICAL_VIEWS


HASH_VIEWS = (*CANONICAL_VIEWS, 'report6_stockpile_forecast_long')


class ReportSemanticError(ValueError):
    pass


class ReportSemanticService:
    def __init__(self, executor):
        self.executor = executor

    def _scalar(self, sql, dataset_id):
        return self.executor.execute(text(sql), {'did': dataset_id}).scalar_one()

    def summary(self, dataset_id):
        counts = {name: self._scalar(f'SELECT count(*) FROM reporting.{name} WHERE dataset_version_id=:did', dataset_id)
                  for name in CANONICAL_VIEWS}
        counts['report3_forecast_history_long'] = self._scalar(
            'SELECT count(*) FROM reporting.report3_forecast_history_long WHERE dataset_version_id=:did', dataset_id)
        counts['report4_weekly_forecast_long'] = self._scalar(
            'SELECT count(*) FROM reporting.report4_weekly_forecast_long WHERE dataset_version_id=:did', dataset_id)
        counts['report6_stockpile_forecast_long'] = self._scalar(
            'SELECT count(*) FROM reporting.report6_stockpile_forecast_long WHERE dataset_version_id=:did', dataset_id)
        counts['zero_demand_material_count'] = self._scalar(
            'SELECT count(*) FROM reporting.report4_latest_13w_forecast WHERE dataset_version_id=:did AND thirteen_week_demand_qty=0', dataset_id)
        counts['report1_stockpile_asof_hit_count'] = self._scalar(
            "SELECT count(*) FROM reporting.report1_overdue_po_detail r WHERE r.dataset_version_id=:did AND EXISTS "
            "(SELECT 1 FROM platform.stockpile_versions v JOIN platform.stockpile_records sr "
            "ON sr.dataset_version_id=v.dataset_version_id AND sr.stockpile_version_id=v.stockpile_version_id "
            "WHERE v.dataset_version_id=r.dataset_version_id AND sr.material_id=r.material_id AND v.is_valid AND v.version_date<=r.order_date "
            "AND NOT EXISTS (SELECT 1 FROM platform.stockpile_versions n WHERE n.dataset_version_id=v.dataset_version_id "
            "AND n.is_valid AND n.version_date<=r.order_date AND (n.version_date>v.version_date OR (n.version_date=v.version_date AND n.sequence_no>v.sequence_no))))", dataset_id)
        counts['report1_stockpile_asof_miss_count'] = counts['report1_overdue_po_detail'] - counts['report1_stockpile_asof_hit_count']
        digest = sha256()
        for name in HASH_VIEWS:
            rows = sorted(self.executor.execute(text(
                f'SELECT row_to_json(t)::text FROM reporting.{name} t WHERE dataset_version_id=:did'), {'did': dataset_id}).scalars())
            digest.update(name.encode())
            digest.update(b'\0')
            digest.update('\n'.join(rows).encode())
        return {'counts': counts, 'report_semantic_content_hash': digest.hexdigest()}


class ReportReconciliationValidator:
    """Validate public semantics against legal platform source facts only."""
    CHECKS = {
        'report1_report2_material_orphans': "SELECT count(*) FROM reporting.report1_overdue_po_detail a LEFT JOIN reporting.report2_material_supply_demand b USING(dataset_version_id,material_id) WHERE a.dataset_version_id=:did AND b.material_id IS NULL",
        'report1_report3_window_orphans': "SELECT count(*) FROM reporting.report1_overdue_po_detail a LEFT JOIN (SELECT dataset_version_id,po_line_schedule_id,count(DISTINCT forecast_version_id) versions FROM reporting.report3_forecast_history GROUP BY 1,2) b USING(dataset_version_id,po_line_schedule_id) WHERE a.dataset_version_id=:did AND coalesce(b.versions,0)<>4",
        'report1_report5_project_orphans': "SELECT count(*) FROM reporting.report1_overdue_po_detail a LEFT JOIN reporting.report5_product_configuration b ON b.dataset_version_id=a.dataset_version_id AND b.project_id=a.po_reference_project_id WHERE a.dataset_version_id=:did AND a.po_reference_project_id IS NOT NULL AND b.project_id IS NULL",
        'report2_report4_material_orphans': "SELECT count(*) FROM reporting.report2_material_supply_demand a LEFT JOIN reporting.report4_latest_13w_forecast b USING(dataset_version_id,material_id) WHERE a.dataset_version_id=:did AND b.material_id IS NULL",
        'report3_report5_project_orphans': "SELECT count(*) FROM (SELECT DISTINCT dataset_version_id,material_id,project_id FROM reporting.report3_forecast_history WHERE dataset_version_id=:did) a LEFT JOIN reporting.report5_product_configuration b USING(dataset_version_id,material_id,project_id) WHERE b.project_id IS NULL",
        'report6_report2_material_orphans': "SELECT count(*) FROM reporting.report6_stockpile_detail a LEFT JOIN reporting.report2_material_supply_demand b USING(dataset_version_id,material_id) WHERE a.dataset_version_id=:did AND b.material_id IS NULL",
        'report2_supply_reconciliation_errors': "SELECT count(*) FROM reporting.report2_material_supply_demand r JOIN platform.supply_demand_snapshots s USING(dataset_version_id,material_id) JOIN LATERAL (SELECT coalesce(sum(component_qty) FILTER(WHERE component_side='SUPPLY'),0) q FROM platform.supply_demand_components c WHERE c.dataset_version_id=s.dataset_version_id AND c.supply_demand_snapshot_id=s.supply_demand_snapshot_id) x ON true WHERE r.dataset_version_id=:did AND (r.all_supply_qty<>x.q OR r.all_supply_qty<>s.all_supply_qty)",
        'report2_demand_reconciliation_errors': "SELECT count(*) FROM reporting.report2_material_supply_demand r JOIN platform.supply_demand_snapshots s USING(dataset_version_id,material_id) JOIN LATERAL (SELECT coalesce(sum(component_qty) FILTER(WHERE component_side='DEMAND'),0) q FROM platform.supply_demand_components c WHERE c.dataset_version_id=s.dataset_version_id AND c.supply_demand_snapshot_id=s.supply_demand_snapshot_id) x ON true WHERE r.dataset_version_id=:did AND (r.actual_demand_total_qty<>x.q OR r.actual_demand_total_qty<>s.actual_demand_total_qty OR r.supply_demand_surplus_qty<>r.all_supply_qty-r.actual_demand_total_qty)",
        'report4_project_material_errors': "SELECT count(*) FROM reporting.report4_weekly_forecast_long m JOIN LATERAL (SELECT coalesce(sum(p.forecast_qty),0) q FROM reporting.report4_weekly_project_long p WHERE p.dataset_version_id=m.dataset_version_id AND p.weekly_forecast_snapshot_id=m.weekly_forecast_snapshot_id AND p.material_id=m.material_id AND p.week_start_date=m.week_start_date) x ON true WHERE m.dataset_version_id=:did AND m.forecast_qty<>x.q",
        'report6_future_version_errors': "SELECT count(*) FROM reporting.report6_stockpile_detail r JOIN platform.dataset_versions d USING(dataset_version_id) WHERE r.dataset_version_id=:did AND r.stockpile_version_date>d.snapshot_date",
        'report6_month_errors': "SELECT count(*) FROM (SELECT dataset_version_id,stockpile_version_id,material_id,count(*) n,min(month_index) lo,max(month_index) hi FROM reporting.report6_stockpile_forecast_long WHERE dataset_version_id=:did GROUP BY 1,2,3) q WHERE n<>6 OR lo<>1 OR hi<>6",
        'demand_lineage_orphans': "SELECT count(*) FROM (SELECT dataset_version_id,material_id,project_id,demand_signal_id FROM reporting.report3_forecast_history WHERE dataset_version_id=:did UNION SELECT dataset_version_id,material_id,project_id,demand_signal_id FROM reporting.report4_weekly_project_long WHERE dataset_version_id=:did) q LEFT JOIN platform.demand_signals s USING(dataset_version_id,material_id,project_id,demand_signal_id) WHERE s.demand_signal_id IS NULL",
        'report6_demand_lineage_orphans': "SELECT count(*) FROM reporting.report6_stockpile_forecast_long r CROSS JOIN LATERAL jsonb_array_elements(r.demand_lineage) j LEFT JOIN platform.demand_signals s ON s.dataset_version_id=r.dataset_version_id AND s.material_id=r.material_id AND s.project_id=(j->>'project_id')::uuid AND s.demand_signal_id=(j->>'demand_signal_id')::uuid LEFT JOIN (SELECT DISTINCT dataset_version_id,material_id,project_id,demand_signal_id FROM reporting.report4_weekly_project_long) w ON w.dataset_version_id=r.dataset_version_id AND w.material_id=r.material_id AND w.project_id=(j->>'project_id')::uuid AND w.demand_signal_id=(j->>'demand_signal_id')::uuid WHERE r.dataset_version_id=:did AND (s.demand_signal_id IS NULL OR w.demand_signal_id IS NULL)",
        'report6_demand_lineage_qty_errors': "SELECT count(*) FROM (SELECT r.stockpile_version_id,r.material_id,r.forecast_month,r.forecast_qty,coalesce(sum((j->>'forecast_qty')::numeric),0) lineage_qty FROM reporting.report6_stockpile_forecast_long r CROSS JOIN LATERAL jsonb_array_elements(r.demand_lineage) j WHERE r.dataset_version_id=:did GROUP BY 1,2,3,4) q WHERE forecast_qty<>lineage_qty",
        'report2_mpm_snapshot_errors': "SELECT count(*) FROM reporting.report2_material_supply_demand r LEFT JOIN platform.material_mpm_assignments a ON a.dataset_version_id=r.dataset_version_id AND a.material_id=r.material_id AND a.effective_from<=r.snapshot_date AND (a.effective_to IS NULL OR a.effective_to>r.snapshot_date) LEFT JOIN platform.employees e ON e.dataset_version_id=a.dataset_version_id AND e.employee_id=a.employee_id WHERE r.dataset_version_id=:did AND (a.material_id IS NULL OR r.mpm_code IS DISTINCT FROM e.employee_code)",
    }

    def __init__(self, executor):
        self.executor = executor

    def validate(self, dataset_id):
        results = {name: self.executor.execute(text(sql), {'did': dataset_id}).scalar_one()
                   for name, sql in self.CHECKS.items()}
        results['report1_report6_selector_errors'] = self.executor.execute(text(
            "SELECT count(*) FROM reporting.report1_overdue_po_detail r WHERE r.dataset_version_id=:did AND NOT EXISTS "
            "(SELECT 1 FROM platform.dataset_versions d WHERE d.dataset_version_id=r.dataset_version_id)"), {'did': dataset_id}).scalar_one()
        if any(results.values()):
            raise ReportSemanticError('REPORT_RECONCILIATION_FAILED:' + json.dumps(results, sort_keys=True))
        return results
