"""Minimal public evidence projections for revision 012; no business-table writes."""

VIEWS = {
    "forecast_version_evidence": """
SELECT v.dataset_version_id,v.forecast_version_id,v.version_date,v.sequence_no,v.is_valid
FROM platform.forecast_versions v JOIN platform.dataset_versions d USING(dataset_version_id)
WHERE v.version_date<=d.snapshot_date""",
    "weekly_snapshot_evidence": """
SELECT s.dataset_version_id,s.weekly_forecast_snapshot_id,s.snapshot_date AS forecast_snapshot_date,
 s.source_forecast_version_id
FROM platform.weekly_forecast_snapshots s JOIN platform.dataset_versions d USING(dataset_version_id)
WHERE s.is_latest AND s.snapshot_date<=d.snapshot_date""",
    "supply_snapshot_evidence": """
SELECT s.dataset_version_id,s.material_id,s.organization_id,s.supply_demand_snapshot_id,
 s.snapshot_date AS supply_snapshot_date,i.inventory_snapshot_id,i.snapshot_date AS inventory_snapshot_date,
 a.employee_id AS mpm_employee_id
FROM platform.supply_demand_snapshots s
JOIN platform.inventory_snapshots i USING(dataset_version_id,material_id,organization_id)
JOIN platform.material_mpm_assignments a USING(dataset_version_id,material_mpm_assignment_id)""",
    "stockpile_forecast_evidence": """
SELECT f.dataset_version_id,f.stockpile_version_id,f.material_id,f.forecast_month,f.forecast_qty
FROM platform.stockpile_forecasts f JOIN platform.stockpile_versions v USING(dataset_version_id,stockpile_version_id)
JOIN platform.dataset_versions d USING(dataset_version_id)
WHERE v.is_valid AND v.version_date<=d.snapshot_date""",
    "stockpile_age_evidence": """
SELECT a.dataset_version_id,a.stockpile_version_id,a.material_id,a.age_threshold_days,a.age_qty
FROM platform.stockpile_inventory_age_buckets a JOIN platform.stockpile_versions v USING(dataset_version_id,stockpile_version_id)
JOIN platform.dataset_versions d USING(dataset_version_id)
WHERE v.is_valid AND v.version_date<=d.snapshot_date""",
}


def create_statements():
    return tuple(f"CREATE VIEW reporting.{name} AS {sql}" for name, sql in VIEWS.items())


def drop_statements():
    return tuple(f"DROP VIEW reporting.{name}" for name in reversed(VIEWS))
