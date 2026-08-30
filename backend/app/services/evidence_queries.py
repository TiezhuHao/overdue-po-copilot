"""REST-only projection enrichment, using authorized reporting views exclusively."""
from sqlalchemy import text


def enriched_source(report_id, view):
    base = f"reporting.{view}"
    if report_id == 2:
        return f"""(SELECT r.*,e.supply_demand_snapshot_id,e.inventory_snapshot_id,e.mpm_employee_id,
 e.supply_snapshot_date,e.inventory_snapshot_date FROM {base} r
 LEFT JOIN reporting.supply_snapshot_evidence e USING(dataset_version_id,material_id,organization_id)) evidence"""
    if report_id == 3:
        return f"""(SELECT r.*,v.sequence_no forecast_version_sequence,
 date_trunc('month',r.forecast_version_date)::date horizon_start_month,
 (date_trunc('month',r.forecast_version_date)+interval '7 months')::date horizon_end_month_exclusive
 FROM {base} r JOIN reporting.forecast_version_evidence v USING(dataset_version_id,forecast_version_id)
 WHERE v.is_valid) r"""
    if report_id == 4:
        return f"""(SELECT r.*,s.forecast_snapshot_date,s.source_forecast_version_id
 FROM {base} r JOIN reporting.weekly_snapshot_evidence s USING(dataset_version_id,weekly_forecast_snapshot_id)) evidence"""
    if report_id == 6:
        return f"""(SELECT r.*,h.actual_stockpile_qty,h.sequence_no stockpile_version_sequence
 FROM {base} r JOIN reporting.report6_stockpile_history h
 USING(dataset_version_id,stockpile_version_id,material_id,stockpile_record_id,organization_id)) evidence"""
    return base


HISTORICAL_STOCKPILE_SOURCE = """(SELECT h.dataset_version_id,h.stockpile_record_id,h.stockpile_version_id,
 h.material_id,h.organization_id,m.material_code,h.version_name stockpile_version_name,
 h.version_date stockpile_version_date,h.sequence_no stockpile_version_sequence,
 h.stockpile_tag stockpile_nature,h.target_stockpile_qty planned_stockpile_qty,h.actual_stockpile_qty,
 h.inventory_qty,h.seven_day_demand_qty,h.target_stockpile_qty-h.actual_stockpile_qty stockpile_qty_gap,
 CASE WHEN h.target_stockpile_qty=0 THEN NULL ELSE h.actual_stockpile_qty/h.target_stockpile_qty END stockpile_completion_ratio,
 NULL::numeric agreement_unit_price
 FROM reporting.report6_stockpile_history h
 JOIN reporting.report2_material_supply_demand m USING(dataset_version_id,material_id)
 WHERE h.is_valid AND h.stockpile_record_id IS NOT NULL) evidence"""


def weekly_details(executor, dataset_id, rows):
    for row in rows:
        params = {"did": dataset_id, "mid": row["material_id"], "sid": row["weekly_forecast_snapshot_id"]}
        row["weeks"] = list(executor.execute(text(
            "SELECT week_index,week_start_date,forecast_qty FROM reporting.report4_weekly_forecast_long "
            "WHERE dataset_version_id=:did AND material_id=:mid AND weekly_forecast_snapshot_id=:sid ORDER BY week_index"
        ), params).mappings())
        row["project_contributions"] = list(executor.execute(text(
            "SELECT project_id,week_index,week_start_date,forecast_qty FROM reporting.report4_weekly_project_long "
            "WHERE dataset_version_id=:did AND material_id=:mid AND weekly_forecast_snapshot_id=:sid ORDER BY project_id,week_index"
        ), params).mappings())
