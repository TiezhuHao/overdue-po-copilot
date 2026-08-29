"""Deterministic SQL for Phase 6A report semantics.

The display projection is always ordered from the checked-in final-template
manifest. Expressions here define meaning, never an independent column order.
"""
from app.reporting.report_header_manifest import get_report_manifest


ARRAY_FIELDS = {
    'organization_active_projects', 'enterprise_active_projects', 'all_projects',
    'organization_active_customers', 'enterprise_active_customers', 'all_customers',
    'active_configurations', 'assembled_board_configurations',
}
BOOL_FIELDS = {'is_overdue', 'can_close', 'non_cancelable_non_returnable_flag'}
INT_FIELDS = {'po_line_number', 'shipment_number', 'material_lt_days', 'manufacturer_lt_days',
              'in_process_lt_days', 'row_number'}
DATE_FIELDS = {'order_date', 'due_date', 'snapshot_date', 'forecast_version_date',
               'stockpile_version_date'}
TIME_FIELDS = {'completion_at', 'modified_at'}


def _null(field):
    if field in ARRAY_FIELDS:
        return 'NULL::text[]'
    if field in BOOL_FIELDS:
        return 'NULL::boolean'
    if field in INT_FIELDS or field.endswith('_days'):
        return 'NULL::integer'
    if field in DATE_FIELDS:
        return 'NULL::date'
    if field in TIME_FIELDS:
        return 'NULL::timestamptz'
    if field.endswith(('_qty', '_ratio', '_ten_thousand')):
        return 'NULL::numeric'
    return 'NULL::text'


def _projection(report_id, expressions, *, include_dynamic=True):
    columns = []
    for column in get_report_manifest(report_id)['columns']:
        if not include_dynamic and column['slot']:
            continue
        field = column['canonical_field']
        columns.append(f"    {expressions.get(field, _null(field))} AS {field}")
    return ',\n'.join(columns)


def _report1():
    e = {
        'inventory_organization_code': 'io.organization_code',
        'inventory_organization_type': 'io.inventory_organization_type',
        'business_entity_name': 'be.organization_name', 'po_number': 'h.po_number',
        'po_line_number': 'l.po_line_number', 'shipment_number': 's.shipment_number',
        'close_status': 's.close_status', 'reference_project_name': 'p.project_name',
        'material_code': 'm.material_code', 'material_description': 'm.material_description',
        'specification_model': 'm.specification_model', 'supplier_code': 'sup.supplier_code',
        'supplier_name': 'sup.supplier_name', 'schedule_qty': 's.schedule_qty',
        'schedule_received_qty': 's.schedule_received_qty',
        'overdue_open_qty': 'greatest(s.schedule_qty-s.schedule_received_qty,0)',
        'order_date': 'l.order_date', 'due_date': 's.due_date', 'snapshot_date': 'd.snapshot_date',
        'material_lt_days': 'm.material_lt_days',
        'overdue_days': 'd.snapshot_date-l.order_date-m.material_lt_days-240',
        'is_overdue': 'true', 'order_buyer_name': 'ob.employee_name',
        'default_buyer_name': 'buyer.employee_name', 'material_controller_name': 'ctl.employee_name',
        'planning_manager_name': 'ctlm.employee_name', 'planning_director_name': 'ctld.employee_name',
        'purchasing_manager_name': 'buym.employee_name', 'purchasing_director_name': 'buyd.employee_name',
        'reference_project_code': 'p.project_code', 'can_close': 'l.can_close',
        'completion_at': 'l.completion_at', 'po_status': 'h.po_status',
    }
    return f"""CREATE VIEW reporting.report1_overdue_po_detail AS
SELECT
{_projection(1, e)},
    d.dataset_version_id, s.po_line_schedule_id, l.po_line_id, h.po_header_id,
    l.material_id, l.po_reference_project_id, h.supplier_id, h.inventory_organization_id AS organization_id,
    l.order_date + m.material_lt_days AS forecast_anchor_date
FROM platform.dataset_versions d
JOIN platform.po_headers h ON h.dataset_version_id=d.dataset_version_id
JOIN platform.po_lines l ON l.dataset_version_id=d.dataset_version_id AND l.po_header_id=h.po_header_id
JOIN platform.po_line_schedules s ON s.dataset_version_id=d.dataset_version_id AND s.po_line_id=l.po_line_id
JOIN platform.materials m ON m.dataset_version_id=d.dataset_version_id AND m.material_id=l.material_id
JOIN platform.organizations io ON io.dataset_version_id=d.dataset_version_id AND io.organization_id=h.inventory_organization_id
JOIN platform.organizations be ON be.dataset_version_id=d.dataset_version_id AND be.organization_id=h.business_entity_id
JOIN platform.suppliers sup ON sup.dataset_version_id=d.dataset_version_id AND sup.supplier_id=h.supplier_id
JOIN platform.employees ob ON ob.dataset_version_id=d.dataset_version_id AND ob.employee_id=h.order_buyer_employee_id
LEFT JOIN platform.projects p ON p.dataset_version_id=d.dataset_version_id AND p.project_id=l.po_reference_project_id
LEFT JOIN LATERAL (SELECT e.* FROM platform.material_responsibility_assignments r JOIN platform.employees e USING(dataset_version_id,employee_id)
 WHERE r.dataset_version_id=d.dataset_version_id AND r.material_id=l.material_id AND r.organization_id=h.inventory_organization_id
 AND r.responsibility_type='BUYER' AND r.effective_from<=d.snapshot_date AND (r.effective_to IS NULL OR r.effective_to>d.snapshot_date) LIMIT 1) buyer ON true
LEFT JOIN LATERAL (SELECT e.* FROM platform.material_responsibility_assignments r JOIN platform.employees e USING(dataset_version_id,employee_id)
 WHERE r.dataset_version_id=d.dataset_version_id AND r.material_id=l.material_id AND r.organization_id=h.inventory_organization_id
 AND r.responsibility_type='MATERIAL_CONTROLLER' AND r.effective_from<=d.snapshot_date AND (r.effective_to IS NULL OR r.effective_to>d.snapshot_date) LIMIT 1) ctl ON true
LEFT JOIN platform.employees ctlm ON ctlm.dataset_version_id=d.dataset_version_id AND ctlm.employee_id=ctl.manager_employee_id
LEFT JOIN platform.employees ctld ON ctld.dataset_version_id=d.dataset_version_id AND ctld.employee_id=ctl.director_employee_id
LEFT JOIN platform.employees buym ON buym.dataset_version_id=d.dataset_version_id AND buym.employee_id=buyer.manager_employee_id
LEFT JOIN platform.employees buyd ON buyd.dataset_version_id=d.dataset_version_id AND buyd.employee_id=buyer.director_employee_id
WHERE d.snapshot_date-l.order_date-m.material_lt_days-240 > 0"""


def _report2():
    e = {
        'inventory_organization_code': 'x.organization_code', 'material_code': 'x.material_code',
        'material_description': 'x.material_description', 'supplier_code': 'x.supplier_code',
        'supplier_name_en': 'x.supplier_name_en', 'buyer_name': 'x.buyer_name',
        'material_controller_account': 'x.controller_account', 'material_controller_name': 'x.controller_name',
        'material_controller_code': 'x.controller_code', 'primary_material_controller_name': 'x.primary_controller_name',
        'mpm_code': 'x.mpm_code', 'mpm_name': 'x.mpm_name', 'mpm_department_name': 'x.mpm_department_name',
        'material_lt_days': 'x.material_lt_days', 'manufacturer_lt_days': 'x.manufacturer_lt_days',
        'minimum_pack_qty': 'x.minimum_pack_qty', 'minimum_order_qty': 'x.minimum_order_qty',
        'non_cancelable_non_returnable_flag': 'x.non_cancelable_non_returnable_flag',
        'specification_model': 'x.specification_model',
        'all_supply_qty': 'x.all_supply_qty', 'actual_demand_total_qty': 'x.actual_demand_total_qty',
        'supply_demand_surplus_qty': 'x.supply_demand_surplus_qty',
        'trial_all_supply_qty': 'x.trial_all_supply_qty',
        'trial_actual_demand_total_qty': 'x.trial_actual_demand_total_qty',
        'trial_supply_demand_surplus_qty': 'x.trial_supply_demand_surplus_qty',
        'good_non_vmi_inventory_qty': 'x.available_qty', 'defective_inventory_qty': 'x.quality_hold_qty',
        'non_mrp_inventory_qty': 'x.blocked_qty', 'non_vmi_in_transit_order_qty': 'x.open_po_component_qty',
        'non_vmi_in_transit_delivery_qty': 'x.in_transit_component_qty',
        'standard_work_order_demand_qty': 'x.work_order_demand_qty',
        'planned_order_demand_qty': 'x.plan_demand_qty', 'long_term_forecast_demand_qty': 'x.forecast_demand_qty',
        'trial_good_non_vmi_inventory_qty': 'x.trial_available_qty',
        'trial_non_vmi_in_transit_order_qty': 'x.trial_open_po_component_qty',
        'trial_non_vmi_in_transit_delivery_qty': 'x.trial_in_transit_component_qty',
        'trial_standard_work_order_demand_qty': 'x.trial_work_order_demand_qty',
        'trial_planned_order_demand_qty': 'x.trial_plan_demand_qty',
        'trial_long_term_forecast_demand_qty': 'x.trial_forecast_demand_qty',
        'organization_active_projects': 'x.organization_active_projects',
        'enterprise_active_projects': 'x.enterprise_active_projects', 'top_project': 'x.top_project',
        'organization_active_customers': 'x.organization_active_customers',
        'enterprise_active_customers': 'x.enterprise_active_customers',
        'inventory_age_0_90_qty': 'x.on_hand_qty-x.age_over_90',
        'inventory_age_90_180_qty': 'x.age_over_90-x.age_over_180',
        'inventory_age_180_360_qty': 'x.age_over_180-x.age_over_360',
        'inventory_age_360_540_qty': 'x.age_over_360-x.age_over_540',
        'inventory_age_540_plus_qty': 'x.age_over_540',
        'cumulative_ordered_qty': 'x.cumulative_ordered_qty', 'cumulative_delivered_qty': 'x.cumulative_delivered_qty',
        'open_po_qty': 'x.open_po_component_qty+x.in_transit_component_qty',
        'demand_within_lt_qty': 'x.demand_within_lt_qty',
    }
    return f"""CREATE VIEW reporting.report2_material_supply_demand AS
WITH component AS (
 SELECT dataset_version_id,supply_demand_snapshot_id,
  coalesce(sum(component_qty) FILTER(WHERE component_side='SUPPLY'),0) all_supply_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_side='DEMAND'),0) actual_demand_total_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_side='SUPPLY' AND organization_type_scope='TRIAL'),0) trial_all_supply_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_side='DEMAND' AND organization_type_scope='TRIAL'),0) trial_actual_demand_total_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='OPEN_PO'),0) open_po_component_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='IN_TRANSIT'),0) in_transit_component_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='WORK_ORDER_DEMAND'),0) work_order_demand_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='PLAN_DEMAND'),0) plan_demand_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='FORECAST_DEMAND'),0) forecast_demand_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='OPEN_PO' AND organization_type_scope='TRIAL'),0) trial_open_po_component_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='IN_TRANSIT' AND organization_type_scope='TRIAL'),0) trial_in_transit_component_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='WORK_ORDER_DEMAND' AND organization_type_scope='TRIAL'),0) trial_work_order_demand_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='PLAN_DEMAND' AND organization_type_scope='TRIAL'),0) trial_plan_demand_qty,
  coalesce(sum(component_qty) FILTER(WHERE component_type='FORECAST_DEMAND' AND organization_type_scope='TRIAL'),0) trial_forecast_demand_qty
 FROM platform.supply_demand_components GROUP BY dataset_version_id,supply_demand_snapshot_id),
 age AS (SELECT dataset_version_id,inventory_snapshot_id,
  coalesce(max(age_qty) FILTER(WHERE age_threshold_days=90),0) age_over_90,
  coalesce(max(age_qty) FILTER(WHERE age_threshold_days=180),0) age_over_180,
  coalesce(max(age_qty) FILTER(WHERE age_threshold_days=360),0) age_over_360,
  coalesce(max(age_qty) FILTER(WHERE age_threshold_days=540),0) age_over_540
 FROM platform.inventory_age_buckets GROUP BY dataset_version_id,inventory_snapshot_id),
 project_context AS (SELECT mp.dataset_version_id,mp.material_id,
  array_agg(DISTINCT p.project_name ORDER BY p.project_name) FILTER(WHERE mp.organization_id=m.primary_inventory_organization_id) organization_active_projects,
  array_agg(DISTINCT p.project_name ORDER BY p.project_name) enterprise_active_projects,
  array_agg(DISTINCT c.customer_name ORDER BY c.customer_name) FILTER(WHERE mp.organization_id=m.primary_inventory_organization_id) organization_active_customers,
  array_agg(DISTINCT c.customer_name ORDER BY c.customer_name) enterprise_active_customers
 FROM platform.material_projects mp JOIN platform.materials m ON m.dataset_version_id=mp.dataset_version_id AND m.material_id=mp.material_id
 JOIN platform.dataset_versions d ON d.dataset_version_id=mp.dataset_version_id
 JOIN platform.projects p ON p.dataset_version_id=mp.dataset_version_id AND p.project_id=mp.project_id
 LEFT JOIN platform.project_customers pc ON pc.dataset_version_id=mp.dataset_version_id AND pc.project_id=mp.project_id AND pc.effective_from<=d.snapshot_date AND (pc.effective_to IS NULL OR pc.effective_to>d.snapshot_date)
 LEFT JOIN platform.customers c ON c.dataset_version_id=mp.dataset_version_id AND c.customer_id=pc.customer_id
 WHERE mp.effective_from<=d.snapshot_date AND (mp.effective_to IS NULL OR mp.effective_to>d.snapshot_date)
 GROUP BY mp.dataset_version_id,mp.material_id),
 top_project AS (SELECT dataset_version_id,material_id,project_name top_project FROM (
  SELECT w.dataset_version_id,w.material_id,p.project_name,row_number() over(PARTITION BY w.dataset_version_id,w.material_id ORDER BY sum(w.forecast_qty) DESC,w.project_id) rn
  FROM platform.weekly_project_forecasts w JOIN platform.weekly_forecast_snapshots ws ON ws.dataset_version_id=w.dataset_version_id AND ws.weekly_forecast_snapshot_id=w.weekly_forecast_snapshot_id
  JOIN platform.projects p ON p.dataset_version_id=w.dataset_version_id AND p.project_id=w.project_id WHERE ws.is_latest GROUP BY w.dataset_version_id,w.material_id,w.project_id,p.project_name) q WHERE rn=1),
 poagg AS (SELECT l.dataset_version_id,l.material_id,sum(l.ordered_qty) cumulative_ordered_qty,sum(l.received_qty) cumulative_delivered_qty
  FROM platform.po_lines l JOIN platform.dataset_versions d ON d.dataset_version_id=l.dataset_version_id WHERE l.order_date<=d.snapshot_date GROUP BY l.dataset_version_id,l.material_id),
 demand_lt AS (SELECT ds.dataset_version_id,ds.material_id,sum(coalesce(r.demand_qty,p.demand_qty)) demand_within_lt_qty
  FROM platform.demand_signals ds JOIN platform.demand_signal_points p ON p.dataset_version_id=ds.dataset_version_id AND p.demand_signal_id=ds.demand_signal_id
  JOIN platform.dataset_versions d ON d.dataset_version_id=ds.dataset_version_id
  JOIN platform.materials m ON m.dataset_version_id=ds.dataset_version_id AND m.material_id=ds.material_id
  LEFT JOIN LATERAL (SELECT dr.demand_qty FROM platform.demand_signal_revisions dr WHERE dr.dataset_version_id=p.dataset_version_id AND dr.demand_signal_id=p.demand_signal_id AND dr.demand_date=p.demand_date AND dr.observed_on<=d.snapshot_date ORDER BY dr.observed_on DESC LIMIT 1) r ON true
  WHERE p.demand_date>=d.snapshot_date AND p.demand_date<d.snapshot_date+m.material_lt_days GROUP BY ds.dataset_version_id,ds.material_id),
 x AS (SELECT d.dataset_version_id,d.snapshot_date,m.material_id,m.primary_inventory_organization_id organization_id,
  m.material_code,m.material_description,m.specification_model,m.material_lt_days,m.manufacturer_lt_days,m.minimum_pack_qty,m.minimum_order_qty,m.non_cancelable_non_returnable_flag,
  o.organization_code,s.supplier_id,s.supplier_code,s.supplier_name_en,b.employee_name buyer_name,
  ctl.account_name controller_account,ctl.employee_name controller_name,ctl.employee_code controller_code,pctl.employee_name primary_controller_name,
  me.employee_code mpm_code,me.employee_name mpm_name,mo.organization_name mpm_department_name,
  inv.on_hand_qty,inv.available_qty,inv.quality_hold_qty,inv.blocked_qty,
  CASE WHEN o.inventory_organization_type='TRIAL' THEN inv.available_qty ELSE 0 END trial_available_qty,
  c.all_supply_qty,c.actual_demand_total_qty,c.all_supply_qty-c.actual_demand_total_qty supply_demand_surplus_qty,
  c.trial_all_supply_qty,c.trial_actual_demand_total_qty,c.trial_all_supply_qty-c.trial_actual_demand_total_qty trial_supply_demand_surplus_qty,
  coalesce(c.open_po_component_qty,0) open_po_component_qty,coalesce(c.in_transit_component_qty,0) in_transit_component_qty,
  coalesce(c.work_order_demand_qty,0) work_order_demand_qty,coalesce(c.plan_demand_qty,0) plan_demand_qty,coalesce(c.forecast_demand_qty,0) forecast_demand_qty,
  coalesce(c.trial_open_po_component_qty,0) trial_open_po_component_qty,coalesce(c.trial_in_transit_component_qty,0) trial_in_transit_component_qty,
  coalesce(c.trial_work_order_demand_qty,0) trial_work_order_demand_qty,coalesce(c.trial_plan_demand_qty,0) trial_plan_demand_qty,coalesce(c.trial_forecast_demand_qty,0) trial_forecast_demand_qty,
  coalesce(a.age_over_90,0) age_over_90,coalesce(a.age_over_180,0) age_over_180,coalesce(a.age_over_360,0) age_over_360,coalesce(a.age_over_540,0) age_over_540,
  pc.organization_active_projects,pc.enterprise_active_projects,pc.organization_active_customers,pc.enterprise_active_customers,tp.top_project,
  coalesce(pa.cumulative_ordered_qty,0) cumulative_ordered_qty,coalesce(pa.cumulative_delivered_qty,0) cumulative_delivered_qty,coalesce(dl.demand_within_lt_qty,0) demand_within_lt_qty
 FROM platform.dataset_versions d JOIN platform.materials m ON m.dataset_version_id=d.dataset_version_id
 JOIN platform.organizations o ON o.dataset_version_id=d.dataset_version_id AND o.organization_id=m.primary_inventory_organization_id
 JOIN platform.inventory_snapshots inv ON inv.dataset_version_id=d.dataset_version_id AND inv.material_id=m.material_id
 JOIN platform.supply_demand_snapshots sd ON sd.dataset_version_id=d.dataset_version_id AND sd.material_id=m.material_id
 JOIN platform.material_mpm_assignments ma ON ma.dataset_version_id=d.dataset_version_id AND ma.material_id=m.material_id AND ma.effective_from<=d.snapshot_date AND (ma.effective_to IS NULL OR ma.effective_to>d.snapshot_date)
 JOIN platform.employees me ON me.dataset_version_id=d.dataset_version_id AND me.employee_id=ma.employee_id
 JOIN platform.organizations mo ON mo.dataset_version_id=d.dataset_version_id AND mo.organization_id=me.organization_id
 LEFT JOIN LATERAL (SELECT sa.supplier_id,su.supplier_code,su.supplier_name_en FROM platform.material_supplier_assignments sa JOIN platform.suppliers su USING(dataset_version_id,supplier_id) WHERE sa.dataset_version_id=d.dataset_version_id AND sa.material_id=m.material_id AND sa.assignment_type='PRIMARY' AND sa.effective_from<=d.snapshot_date AND (sa.effective_to IS NULL OR sa.effective_to>d.snapshot_date) LIMIT 1) s ON true
 LEFT JOIN LATERAL (SELECT e.employee_name FROM platform.material_responsibility_assignments r JOIN platform.employees e USING(dataset_version_id,employee_id) WHERE r.dataset_version_id=d.dataset_version_id AND r.material_id=m.material_id AND r.organization_id=m.primary_inventory_organization_id AND r.responsibility_type='BUYER' AND r.effective_from<=d.snapshot_date AND (r.effective_to IS NULL OR r.effective_to>d.snapshot_date) LIMIT 1) b ON true
 LEFT JOIN LATERAL (SELECT e.* FROM platform.material_responsibility_assignments r JOIN platform.employees e USING(dataset_version_id,employee_id) WHERE r.dataset_version_id=d.dataset_version_id AND r.material_id=m.material_id AND r.organization_id=m.primary_inventory_organization_id AND r.responsibility_type='MATERIAL_CONTROLLER' AND r.effective_from<=d.snapshot_date AND (r.effective_to IS NULL OR r.effective_to>d.snapshot_date) LIMIT 1) ctl ON true
 LEFT JOIN LATERAL (SELECT e.employee_name FROM platform.material_responsibility_assignments r JOIN platform.employees e USING(dataset_version_id,employee_id) WHERE r.dataset_version_id=d.dataset_version_id AND r.material_id=m.material_id AND r.organization_id=m.primary_inventory_organization_id AND r.responsibility_type='PRIMARY_MATERIAL_CONTROLLER' AND r.effective_from<=d.snapshot_date AND (r.effective_to IS NULL OR r.effective_to>d.snapshot_date) LIMIT 1) pctl ON true
 LEFT JOIN component c ON c.dataset_version_id=d.dataset_version_id AND c.supply_demand_snapshot_id=sd.supply_demand_snapshot_id
 LEFT JOIN age a ON a.dataset_version_id=d.dataset_version_id AND a.inventory_snapshot_id=inv.inventory_snapshot_id
 LEFT JOIN project_context pc ON pc.dataset_version_id=d.dataset_version_id AND pc.material_id=m.material_id
 LEFT JOIN top_project tp ON tp.dataset_version_id=d.dataset_version_id AND tp.material_id=m.material_id
 LEFT JOIN poagg pa ON pa.dataset_version_id=d.dataset_version_id AND pa.material_id=m.material_id
 LEFT JOIN demand_lt dl ON dl.dataset_version_id=d.dataset_version_id AND dl.material_id=m.material_id)
SELECT
{_projection(2, e)},
    x.dataset_version_id,x.material_id,x.organization_id,x.supplier_id,x.snapshot_date
FROM x"""


def _report3():
    e = {
        'material_code': 'm.material_code', 'business_unit_name': 'ctx.business_unit_name',
        'planning_department_name': 'ctx.planning_department_name', 'project_name': 'p.project_name',
        'customer_project_name': 'p.customer_project_name', 'customer_name': 'ctx.customer_name',
        'brand_name': 'p.brand_name', 'product_type': 'p.product_type', 'shipment_type': 'p.shipment_type',
        'business_mode': 'p.business_mode', 'forecast_source': 'mf.forecast_source',
        'forecast_version_name': 'v.version_name', 'forecast_version_date': 'v.version_date',
        'forecast_total_qty': 'sum(mf.forecast_qty) over(PARTITION BY r.po_line_schedule_id,v.forecast_version_id,mf.material_id,mf.project_id)',
        'cumulative_shipped_qty': "coalesce((SELECT sum(sh.shipped_qty) FROM platform.material_project_shipments sh WHERE sh.dataset_version_id=mf.dataset_version_id AND sh.material_id=mf.material_id AND sh.project_id=mf.project_id AND sh.shipment_date<=v.version_date),0)",
    }
    return f"""CREATE VIEW reporting.report3_forecast_history_long AS
WITH daily_final AS (SELECT v.* FROM platform.forecast_versions v WHERE v.is_valid AND NOT EXISTS
 (SELECT 1 FROM platform.forecast_versions n WHERE n.dataset_version_id=v.dataset_version_id AND n.version_date=v.version_date AND n.is_valid AND n.sequence_no>v.sequence_no)),
 window_versions AS (SELECT r.dataset_version_id,r.po_line_schedule_id,r.material_id,r.forecast_anchor_date,v.forecast_version_id,v.version_date,v.window_position
 FROM reporting.report1_overdue_po_detail r
 JOIN LATERAL ((SELECT b.forecast_version_id,b.version_date,0::bigint window_position FROM daily_final b WHERE b.dataset_version_id=r.dataset_version_id AND b.version_date<r.forecast_anchor_date ORDER BY b.version_date DESC LIMIT 1)
 UNION ALL (SELECT q.forecast_version_id,q.version_date,row_number() over(ORDER BY q.version_date)::bigint FROM
   (SELECT a.forecast_version_id,a.version_date FROM daily_final a WHERE a.dataset_version_id=r.dataset_version_id AND a.version_date>r.forecast_anchor_date ORDER BY a.version_date LIMIT 5) q)) v ON true),
 project_context AS (SELECT pc.dataset_version_id,pc.project_id,
  CASE WHEN count(DISTINCT bu.organization_id)=1 THEN min(bu.organization_name) END business_unit_name,
  CASE WHEN count(DISTINCT pd.organization_id)=1 THEN min(pd.organization_name) END planning_department_name,
  CASE WHEN count(DISTINCT c.customer_id)=1 THEN min(c.customer_name) END customer_name
 FROM platform.product_configs pc JOIN platform.dataset_versions d ON d.dataset_version_id=pc.dataset_version_id
 JOIN platform.organizations bu ON bu.dataset_version_id=pc.dataset_version_id AND bu.organization_id=pc.business_unit_id
 JOIN platform.organizations pd ON pd.dataset_version_id=pc.dataset_version_id AND pd.organization_id=pc.planning_department_id
 JOIN platform.customers c ON c.dataset_version_id=pc.dataset_version_id AND c.customer_id=pc.customer_id
 WHERE pc.effective_from<=d.snapshot_date AND (pc.effective_to IS NULL OR pc.effective_to>d.snapshot_date)
 GROUP BY pc.dataset_version_id,pc.project_id)
SELECT
{_projection(3, e, include_dynamic=False)},
    mf.dataset_version_id,r.po_line_schedule_id,mf.material_id,mf.project_id,v.forecast_version_id,mf.demand_signal_id,
    mf.forecast_month,mf.forecast_qty,r.forecast_anchor_date,w.window_position,
    CASE WHEN w.window_position=0 THEN 'BASELINE' ELSE 'POST' END window_role
FROM window_versions w JOIN reporting.report1_overdue_po_detail r ON r.dataset_version_id=w.dataset_version_id AND r.po_line_schedule_id=w.po_line_schedule_id
JOIN daily_final v ON v.dataset_version_id=w.dataset_version_id AND v.forecast_version_id=w.forecast_version_id
JOIN platform.monthly_forecasts mf ON mf.dataset_version_id=w.dataset_version_id AND mf.forecast_version_id=w.forecast_version_id AND mf.material_id=w.material_id
JOIN platform.materials m ON m.dataset_version_id=mf.dataset_version_id AND m.material_id=mf.material_id
JOIN platform.projects p ON p.dataset_version_id=mf.dataset_version_id AND p.project_id=mf.project_id
LEFT JOIN project_context ctx ON ctx.dataset_version_id=mf.dataset_version_id AND ctx.project_id=mf.project_id
WHERE mf.forecast_month>=date_trunc('month',v.version_date)::date
 AND mf.forecast_month<(date_trunc('month',v.version_date)+interval '7 months')::date"""


def _report3_default():
    return """CREATE VIEW reporting.report3_forecast_history AS
SELECT * FROM reporting.report3_forecast_history_long WHERE window_position<=3"""


def _report4_long():
    return """CREATE VIEW reporting.report4_weekly_forecast_long AS
SELECT s.dataset_version_id,s.weekly_forecast_snapshot_id,m.material_id,
 m.primary_inventory_organization_id organization_id,g.week_index,
 (s.snapshot_date+((8-extract(isodow from s.snapshot_date)::int)%7)+7*(g.week_index-1))::date week_start_date,
 coalesce(w.forecast_qty,0) forecast_qty
FROM platform.weekly_forecast_snapshots s
JOIN platform.materials m ON m.dataset_version_id=s.dataset_version_id
CROSS JOIN generate_series(1,13) g(week_index)
LEFT JOIN platform.weekly_forecasts w ON w.dataset_version_id=s.dataset_version_id
 AND w.weekly_forecast_snapshot_id=s.weekly_forecast_snapshot_id
 AND w.material_id=m.material_id AND w.week_index=g.week_index
WHERE s.is_latest"""


def _report4_project_long():
    return """CREATE VIEW reporting.report4_weekly_project_long AS
SELECT w.dataset_version_id,w.weekly_forecast_snapshot_id,w.material_id,w.organization_id,w.project_id,
 w.demand_signal_id,w.week_index,w.week_start_date,w.forecast_qty
FROM platform.weekly_project_forecasts w JOIN platform.weekly_forecast_snapshots s
 USING(dataset_version_id,weekly_forecast_snapshot_id) WHERE s.is_latest"""


def _report4():
    e = {
        'material_code': 'r2.material_code', 'organization_code': 'r2.inventory_organization_code',
        'specification_model': 'r2.specification_model', 'organization_active_projects': 'r2.organization_active_projects',
        'enterprise_active_projects': 'r2.enterprise_active_projects', 'top_project': 'r2.top_project',
        'material_description': 'r2.material_description', 'supplier_code': 'r2.supplier_code',
        'supplier_name_en': 'r2.supplier_name_en', 'brand_name': 'pc.brand_name',
        'active_configurations': 'pc.active_configurations',
        'assembled_board_configurations': 'pc.assembled_board_configurations', 'buyer_name': 'r2.buyer_name',
        'material_controller_account': 'r2.material_controller_account', 'material_controller_name': 'r2.material_controller_name',
        'material_controller_code': 'r2.material_controller_code', 'minimum_pack_qty': 'r2.minimum_pack_qty',
        'open_po_qty': 'r2.open_po_qty', 'snapshot_date': 'r2.snapshot_date',
        'historical_cumulative_ordered_qty': 'r2.cumulative_ordered_qty',
        'good_subinventory_qty': 'coalesce(inv.available_qty,0)',
        'defective_subinventory_qty': 'coalesce(inv.quality_hold_qty,0)',
        'thirteen_week_demand_qty': 'q.thirteen_week_demand_qty',
        'weekly_average_demand_qty': 'q.thirteen_week_demand_qty/13',
    }
    for index in range(1, 14):
        e[f'week_{index:02d}_forecast_qty'] = f'q.week_{index:02d}_forecast_qty'
    weeks = ','.join(f"coalesce(max(forecast_qty) FILTER(WHERE week_index={i}),0) week_{i:02d}_forecast_qty" for i in range(1,14))
    return f"""CREATE VIEW reporting.report4_latest_13w_forecast AS
WITH config_context AS (SELECT pcm.dataset_version_id,pcm.material_id,
 CASE WHEN count(DISTINCT p.brand_name)=1 THEN min(p.brand_name) END brand_name,
 string_agg(DISTINCT pc.product_config_name,', ' ORDER BY pc.product_config_name) active_configurations,
 string_agg(DISTINCT pc.product_config_name,', ' ORDER BY pc.product_config_name) FILTER(WHERE pc.product_config_type='PCBA') assembled_board_configurations
 FROM platform.product_config_materials pcm JOIN platform.product_configs pc USING(dataset_version_id,product_config_id)
 JOIN platform.projects p ON p.dataset_version_id=pc.dataset_version_id AND p.project_id=pc.project_id
 JOIN platform.dataset_versions d ON d.dataset_version_id=pc.dataset_version_id
 WHERE pc.effective_from<=d.snapshot_date AND (pc.effective_to IS NULL OR pc.effective_to>d.snapshot_date)
 GROUP BY pcm.dataset_version_id,pcm.material_id),
q AS (SELECT dataset_version_id,weekly_forecast_snapshot_id,material_id,organization_id,{weeks},sum(forecast_qty) thirteen_week_demand_qty
 FROM reporting.report4_weekly_forecast_long GROUP BY dataset_version_id,weekly_forecast_snapshot_id,material_id,organization_id)
SELECT
{_projection(4, e)},
    r2.dataset_version_id,r2.material_id,r2.organization_id,q.weekly_forecast_snapshot_id
FROM reporting.report2_material_supply_demand r2 JOIN q USING(dataset_version_id,material_id,organization_id)
LEFT JOIN config_context pc USING(dataset_version_id,material_id)
LEFT JOIN platform.inventory_snapshots inv USING(dataset_version_id,material_id)"""


def _report5():
    e = {
        'row_number': 'row_number() over(ORDER BY pc.dataset_version_id,p.project_code,pc.product_config_name,pc.config_version,m.material_code)',
        'product_config_type': 'pc.product_config_type', 'product_config_name': 'pc.product_config_name',
        'product_name': 'pc.product_name', 'product_config_version': 'pc.config_version',
        'material_code': 'm.material_code', 'customer_material_code': 'pc.customer_material_code',
        'business_unit_name': 'bu.organization_name', 'planning_department_name': 'pd.organization_name',
        'project_name': 'p.project_name', 'customer_project_name': 'p.customer_project_name',
        'research_representative_name': 'rr.employee_name', 'modified_by_name': 'mb.employee_name',
        'modified_at': 'pc.modified_at', 'product_config_status': 'pc.product_config_status',
        'product_category_level_1': 'pc.product_category_level_1',
        'product_category_level_2': 'pc.product_category_level_2',
        'product_category_level_3': 'pc.product_category_level_3',
        'lifecycle_stage': 'lh.lifecycle_stage', 'customer_code': 'c.customer_code',
        'customer_short_code': 'c.customer_short_code', 'product_team_name': 'pc.product_team_name',
    }
    return f"""CREATE VIEW reporting.report5_product_configuration AS
SELECT
{_projection(5, e)},
 d.dataset_version_id,p.project_id,pc.product_config_id,m.material_id,pc.customer_id,pc.business_unit_id,pc.planning_department_id
FROM platform.dataset_versions d JOIN platform.product_configs pc ON pc.dataset_version_id=d.dataset_version_id
JOIN platform.projects p ON p.dataset_version_id=d.dataset_version_id AND p.project_id=pc.project_id
JOIN platform.product_config_materials pcm ON pcm.dataset_version_id=d.dataset_version_id AND pcm.product_config_id=pc.product_config_id
JOIN platform.materials m ON m.dataset_version_id=d.dataset_version_id AND m.material_id=pcm.material_id
JOIN platform.project_lifecycle_history lh ON lh.dataset_version_id=d.dataset_version_id AND lh.project_id=p.project_id AND lh.effective_from<=d.snapshot_date AND (lh.effective_to IS NULL OR lh.effective_to>d.snapshot_date)
JOIN platform.organizations bu ON bu.dataset_version_id=d.dataset_version_id AND bu.organization_id=pc.business_unit_id
JOIN platform.organizations pd ON pd.dataset_version_id=d.dataset_version_id AND pd.organization_id=pc.planning_department_id
JOIN platform.customers c ON c.dataset_version_id=d.dataset_version_id AND c.customer_id=pc.customer_id
JOIN platform.employees rr ON rr.dataset_version_id=d.dataset_version_id AND rr.employee_id=pc.research_representative_employee_id
JOIN platform.employees mb ON mb.dataset_version_id=d.dataset_version_id AND mb.employee_id=pc.modified_by_employee_id
WHERE pc.effective_from<=d.snapshot_date AND (pc.effective_to IS NULL OR pc.effective_to>d.snapshot_date)"""


def _report6_history():
    return """CREATE VIEW reporting.report6_stockpile_history AS
SELECT v.dataset_version_id,v.stockpile_version_id,v.version_name,v.version_date,v.sequence_no,v.is_valid,
 r.material_id,r.organization_id,r.stockpile_record_id,r.stockpile_tag,r.stockpile_period_months,
 r.target_stockpile_qty,r.actual_stockpile_qty,r.inventory_qty,r.seven_day_demand_qty,r.remaining_current_month_demand_qty
FROM platform.stockpile_versions v LEFT JOIN platform.stockpile_records r USING(dataset_version_id,stockpile_version_id)
JOIN platform.dataset_versions d USING(dataset_version_id)
WHERE v.version_date<=d.snapshot_date"""


def _report6_long(table, name, fields):
    return f"""CREATE VIEW reporting.{name} AS
WITH current_version AS (SELECT v.* FROM platform.stockpile_versions v JOIN platform.dataset_versions d USING(dataset_version_id)
 WHERE v.is_valid AND v.version_date<=d.snapshot_date AND NOT EXISTS (SELECT 1 FROM platform.stockpile_versions n
 WHERE n.dataset_version_id=v.dataset_version_id AND n.is_valid AND n.version_date<=d.snapshot_date
 AND (n.version_date>v.version_date OR (n.version_date=v.version_date AND n.sequence_no>v.sequence_no))))
SELECT t.dataset_version_id,t.stockpile_version_id,t.material_id,v.version_date,{fields}
FROM platform.{table} t JOIN current_version v USING(dataset_version_id,stockpile_version_id)"""


def _report6():
    e = {
        'stockpile_version_name': 'v.version_name', 'stockpile_version_date': 'v.version_date',
        'stockpile_nature': 'r.stockpile_tag', 'purchasing_category': 'r2.purchasing_category',
        'material_code': 'm.material_code', 'model': 'm.model', 'material_description': 'm.material_description',
        'agreement_unit_price': 'sa.agreement_unit_price', 'planned_stockpile_qty': 'r.target_stockpile_qty',
        'inventory_qty': 'r.inventory_qty', 'seven_day_demand_qty': 'r.seven_day_demand_qty',
        'stockpile_qty_gap': 'r.target_stockpile_qty-r.actual_stockpile_qty',
        'stockpile_completion_ratio': 'CASE WHEN r.target_stockpile_qty=0 THEN NULL ELSE r.actual_stockpile_qty/r.target_stockpile_qty END',
    }
    return f"""CREATE VIEW reporting.report6_stockpile_detail AS
WITH current_version AS (SELECT v.* FROM platform.stockpile_versions v JOIN platform.dataset_versions d USING(dataset_version_id)
 WHERE v.is_valid AND v.version_date<=d.snapshot_date AND NOT EXISTS (SELECT 1 FROM platform.stockpile_versions n
 WHERE n.dataset_version_id=v.dataset_version_id AND n.is_valid AND n.version_date<=d.snapshot_date
 AND (n.version_date>v.version_date OR (n.version_date=v.version_date AND n.sequence_no>v.sequence_no))))
SELECT
{_projection(6, e, include_dynamic=False)},
 r.dataset_version_id,r.stockpile_record_id,r.stockpile_version_id,r.material_id,r.organization_id,
 CASE WHEN r.target_stockpile_qty=0 THEN 'ZERO_TARGET' ELSE 'TARGET_AVAILABLE' END stockpile_achievement_status
FROM current_version v JOIN platform.stockpile_records r USING(dataset_version_id,stockpile_version_id)
JOIN platform.materials m USING(dataset_version_id,material_id)
LEFT JOIN reporting.report2_material_supply_demand r2 USING(dataset_version_id,material_id)
LEFT JOIN LATERAL (SELECT x.agreement_unit_price FROM platform.material_supplier_assignments x JOIN platform.dataset_versions d USING(dataset_version_id)
 WHERE x.dataset_version_id=r.dataset_version_id AND x.material_id=r.material_id AND x.assignment_type='PRIMARY'
 AND x.effective_from<=d.snapshot_date AND (x.effective_to IS NULL OR x.effective_to>d.snapshot_date) LIMIT 1) sa ON true"""


def _estimated_consumption():
    return """CREATE VIEW reporting.overdue_consumption_context AS
SELECT r1.dataset_version_id,r1.po_line_schedule_id,r1.material_id,r1.overdue_open_qty,
 r4.weekly_average_demand_qty,
 CASE WHEN r4.weekly_average_demand_qty=0 THEN NULL ELSE r1.overdue_open_qty/r4.weekly_average_demand_qty*12/52 END estimated_consumption_months,
 CASE WHEN r4.weekly_average_demand_qty=0 THEN 'NO_FORECAST_DEMAND' ELSE 'FORECAST_AVAILABLE' END consumption_status
FROM reporting.report1_overdue_po_detail r1 JOIN reporting.report4_latest_13w_forecast r4 USING(dataset_version_id,material_id)"""


VIEW_ORDER = (
    ('report1_overdue_po_detail', _report1),
    ('report2_material_supply_demand', _report2),
    ('report5_product_configuration', _report5),
    ('report3_forecast_history_long', _report3),
    ('report3_forecast_history', _report3_default),
    ('report4_weekly_forecast_long', _report4_long),
    ('report4_weekly_project_long', _report4_project_long),
    ('report4_latest_13w_forecast', _report4),
    ('report6_stockpile_history', _report6_history),
    ('report6_stockpile_forecast_long', lambda: _report6_long('stockpile_forecasts', 'report6_stockpile_forecast_long',
       "row_number() over(PARTITION BY t.dataset_version_id,t.stockpile_version_id,t.material_id ORDER BY t.forecast_month) month_index,t.forecast_month,t.forecast_qty,t.source_observed_on,t.demand_lineage")),
    ('report6_stockpile_balance_long', lambda: _report6_long('stockpile_balance_projections', 'report6_stockpile_balance_long',
       't.forecast_month,t.opening_available_qty,t.planned_inbound_qty,t.demand_qty,t.closing_projected_qty')),
    ('report6_stockpile_age_long', lambda: _report6_long('stockpile_inventory_age_buckets', 'report6_stockpile_age_long',
       't.age_threshold_days,t.age_qty')),
    ('report6_stockpile_detail', _report6),
    ('overdue_consumption_context', _estimated_consumption),
)
CANONICAL_VIEWS = (
    'report1_overdue_po_detail', 'report2_material_supply_demand', 'report3_forecast_history',
    'report4_latest_13w_forecast', 'report5_product_configuration', 'report6_stockpile_detail',
)


def create_statements():
    return tuple(builder() for _, builder in VIEW_ORDER)


def drop_statements():
    return tuple(f'DROP VIEW IF EXISTS reporting.{name}' for name, _ in reversed(VIEW_ORDER))
