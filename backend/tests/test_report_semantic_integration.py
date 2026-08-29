from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.reporting.report_header_manifest import get_report_manifest
from app.reporting.semantic_service import ReportSemanticService, ReportReconciliationValidator
from app.reporting.view_definitions import CANONICAL_VIEWS
from tests.test_forecast_integration import forecast_worlds
from tests.test_operational_integration import operational_worlds


pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def report_world(migrated_database, operational_worlds):
    return operational_worlds[0]


def scalar(connection, sql, did):
    return connection.execute(text(sql), {'did': did}).scalar_one()


def test_reporting_schema_and_exact_business_column_order(migrated_database):
    with migrated_database.connect() as connection:
        views = set(connection.scalars(text("SELECT table_name FROM information_schema.views WHERE table_schema='reporting'")))
        assert set(CANONICAL_VIEWS) <= views
        for rid, name in enumerate(CANONICAL_VIEWS, 1):
            actual = list(connection.scalars(text("SELECT column_name FROM information_schema.columns WHERE table_schema='reporting' AND table_name=:name ORDER BY ordinal_position"), {'name': name}))
            expected = [c['canonical_field'] for c in get_report_manifest(rid)['columns'] if not c['slot'] or rid == 4]
            assert actual[:len(expected)] == expected
        assert connection.scalar(text("SELECT count(*) FROM information_schema.view_table_usage WHERE view_schema='reporting' AND table_schema='evaluation'")) == 0


def test_deferred_business_formulas_remain_null(migrated_database, report_world):
    did = report_world.dataset_version_id
    with migrated_database.connect() as c:
        for rid in (2, 4, 6):
            fields = [column['canonical_field'] for column in get_report_manifest(rid)['columns']
                      if column['business_status'] == 'DEFERRED_BUSINESS_FORMULA' and not column['slot']]
            view = CANONICAL_VIEWS[rid - 1]
            for field in fields:
                assert scalar(c, f'SELECT count(*) FROM reporting.{view} WHERE dataset_version_id=:did AND {field} IS NOT NULL', did) == 0


def test_report1_strict_overdue_open_qty_and_no_answer_columns(migrated_database, report_world):
    did = report_world.dataset_version_id
    with migrated_database.connect() as c:
        assert scalar(c, "SELECT count(*) FROM reporting.report1_overdue_po_detail WHERE dataset_version_id=:did AND (overdue_days<=0 OR NOT is_overdue)", did) == 0
        assert scalar(c, "SELECT count(*) FROM reporting.report1_overdue_po_detail WHERE dataset_version_id=:did AND overdue_open_qty<>greatest(schedule_qty-schedule_received_qty,0)", did) == 0
        columns = set(c.scalars(text("SELECT column_name FROM information_schema.columns WHERE table_schema='reporting' AND table_name='report1_overdue_po_detail'")))
        assert not {'true_cause','scenario_pattern','causal_project_id','expected_action'}.intersection(columns)
        row = c.execute(text("SELECT po_line_schedule_id,order_date,material_lt_days,snapshot_date FROM reporting.report1_overdue_po_detail WHERE dataset_version_id=:did LIMIT 1"), {'did': did}).one()
        exact = row.snapshot_date - timedelta(days=row.material_lt_days + 240)
        c.execute(text("UPDATE platform.po_lines l SET order_date=:day FROM platform.po_line_schedules s WHERE s.dataset_version_id=l.dataset_version_id AND s.po_line_id=l.po_line_id AND s.po_line_schedule_id=:sid"), {'day': exact, 'sid': row.po_line_schedule_id})
        assert c.scalar(text("SELECT count(*) FROM reporting.report1_overdue_po_detail WHERE po_line_schedule_id=:sid"), {'sid': row.po_line_schedule_id}) == 0


def test_report2_grain_core_reconciliation_and_mpm(migrated_database, report_world):
    did = report_world.dataset_version_id
    with migrated_database.connect() as c:
        assert scalar(c, "SELECT count(*) FROM reporting.report2_material_supply_demand WHERE dataset_version_id=:did", did) == scalar(c, "SELECT count(*) FROM platform.materials WHERE dataset_version_id=:did", did)
        assert scalar(c, "SELECT count(*) FROM (SELECT material_id FROM reporting.report2_material_supply_demand WHERE dataset_version_id=:did GROUP BY material_id HAVING count(*)<>1) q", did) == 0
        assert scalar(c, "SELECT count(*) FROM reporting.report2_material_supply_demand WHERE dataset_version_id=:did AND supply_demand_surplus_qty<>all_supply_qty-actual_demand_total_qty", did) == 0
        assert scalar(c, "SELECT count(*) FROM reporting.report2_material_supply_demand r LEFT JOIN platform.material_mpm_assignments a ON a.dataset_version_id=r.dataset_version_id AND a.material_id=r.material_id AND a.effective_from<=r.snapshot_date AND (a.effective_to IS NULL OR a.effective_to>r.snapshot_date) WHERE r.dataset_version_id=:did AND a.material_id IS NULL", did) == 0


def test_report3_window_seven_months_and_shipment_cutoff(migrated_database, report_world):
    did = report_world.dataset_version_id
    with migrated_database.connect() as c:
        assert scalar(c, "SELECT count(*) FROM (SELECT po_line_schedule_id,count(DISTINCT forecast_version_id) n,min(window_position) lo,max(window_position) hi FROM reporting.report3_forecast_history WHERE dataset_version_id=:did GROUP BY 1) q WHERE n<>4 OR lo<>0 OR hi<>3", did) == 0
        assert scalar(c, "SELECT count(*) FROM reporting.report3_forecast_history WHERE dataset_version_id=:did AND ((window_role='BASELINE' AND forecast_version_date>=forecast_anchor_date) OR (window_role='POST' AND forecast_version_date<=forecast_anchor_date))", did) == 0
        assert scalar(c, "SELECT count(*) FROM (SELECT po_line_schedule_id,material_id,project_id,forecast_version_id,count(*) n,min(forecast_month) lo,max(forecast_month) hi FROM reporting.report3_forecast_history WHERE dataset_version_id=:did GROUP BY 1,2,3,4) q WHERE n<>7 OR hi<>(lo+interval '6 months')::date", did) == 0
        assert scalar(c, "SELECT count(*) FROM reporting.report3_forecast_history r WHERE dataset_version_id=:did AND cumulative_shipped_qty<>coalesce((SELECT sum(s.shipped_qty) FROM platform.material_project_shipments s WHERE s.dataset_version_id=r.dataset_version_id AND s.material_id=r.material_id AND s.project_id=r.project_id AND s.shipment_date<=r.forecast_version_date),0)", did) == 0


def test_report4_latest_monday_thirteen_weeks_and_zero_demand(migrated_database, report_world):
    did = report_world.dataset_version_id
    with migrated_database.connect() as c:
        assert scalar(c, "SELECT count(*) FROM reporting.report4_latest_13w_forecast WHERE dataset_version_id=:did", did) == scalar(c, "SELECT count(*) FROM platform.materials WHERE dataset_version_id=:did", did)
        assert scalar(c, "SELECT count(*) FROM (SELECT material_id,count(*) n,min(week_index) lo,max(week_index) hi,min(extract(isodow from week_start_date)) dow FROM reporting.report4_weekly_forecast_long WHERE dataset_version_id=:did GROUP BY material_id) q WHERE n<>13 OR lo<>1 OR hi<>13 OR dow<>1", did) == 0
        assert scalar(c, "SELECT count(*) FROM reporting.report4_latest_13w_forecast WHERE dataset_version_id=:did AND weekly_average_demand_qty<>thirteen_week_demand_qty/13", did) == 0
        material_id = c.scalar(text("SELECT material_id FROM platform.materials WHERE dataset_version_id=:did ORDER BY material_id LIMIT 1"), {'did': did})
        c.execute(text("UPDATE platform.weekly_forecasts SET forecast_qty=0 WHERE dataset_version_id=:did AND material_id=:mid"), {'did': did, 'mid': material_id})
        c.execute(text("UPDATE platform.weekly_project_forecasts SET forecast_qty=0 WHERE dataset_version_id=:did AND material_id=:mid"), {'did': did, 'mid': material_id})
        assert scalar(c, "SELECT count(*) FROM reporting.report4_latest_13w_forecast WHERE dataset_version_id=:did AND thirteen_week_demand_qty=0", did) > 0


def test_report5_cardinality_and_lifecycle(migrated_database, report_world):
    did = report_world.dataset_version_id
    with migrated_database.connect() as c:
        assert scalar(c, "SELECT count(*) FROM reporting.report5_product_configuration WHERE dataset_version_id=:did", did) == scalar(c, "SELECT count(*) FROM platform.product_config_materials WHERE dataset_version_id=:did", did)
        assert scalar(c, "SELECT count(*) FROM reporting.report5_product_configuration WHERE dataset_version_id=:did AND lifecycle_stage NOT IN ('NPI','MASS_PRODUCTION','EOL')", did) == 0
        assert scalar(c, "SELECT count(*) FROM (SELECT project_id,count(DISTINCT product_config_id) n FROM reporting.report5_product_configuration WHERE dataset_version_id=:did GROUP BY project_id) q WHERE n<2", did) == 0


def test_report6_current_asof_six_month_balance_and_age(migrated_database, report_world):
    did = report_world.dataset_version_id
    with migrated_database.connect() as c:
        assert scalar(c, "SELECT count(*) FROM reporting.report6_stockpile_detail r JOIN platform.dataset_versions d USING(dataset_version_id) WHERE r.dataset_version_id=:did AND r.stockpile_version_date>d.snapshot_date", did) == 0
        assert scalar(c, "SELECT count(*) FROM (SELECT material_id,count(*) n,min(month_index) lo,max(month_index) hi FROM reporting.report6_stockpile_forecast_long WHERE dataset_version_id=:did GROUP BY material_id) q WHERE n<>6 OR lo<>1 OR hi<>6", did) == 0
        assert scalar(c, "SELECT count(*) FROM (SELECT material_id,forecast_month,opening_available_qty,lag(closing_projected_qty) over(PARTITION BY material_id ORDER BY forecast_month) previous FROM reporting.report6_stockpile_balance_long WHERE dataset_version_id=:did) q WHERE previous IS NOT NULL AND opening_available_qty<>previous", did) == 0
        assert scalar(c, "SELECT count(*) FROM (SELECT material_id,age_threshold_days,age_qty,lag(age_qty) over(PARTITION BY material_id ORDER BY age_threshold_days) previous FROM reporting.report6_stockpile_age_long WHERE dataset_version_id=:did) q WHERE previous IS NOT NULL AND age_qty>previous", did) == 0
        # Every overdue row can execute the as-of selection; hit and miss are both valid outputs.
        rows = c.execute(text("SELECT r.po_line_schedule_id,(SELECT h.stockpile_version_id FROM reporting.report6_stockpile_history h WHERE h.dataset_version_id=r.dataset_version_id AND h.is_valid AND h.version_date<=r.order_date ORDER BY h.version_date DESC,h.sequence_no DESC LIMIT 1) selected FROM reporting.report1_overdue_po_detail r WHERE r.dataset_version_id=:did"), {'did': did}).all()
        assert len(rows) > 0 and len({row.po_line_schedule_id for row in rows}) == len(rows)


def test_cross_report_reconciliation_and_semantic_determinism(migrated_database, report_world):
    did = report_world.dataset_version_id
    with migrated_database.connect() as c:
        assert not any(ReportReconciliationValidator(c).validate(did).values())
        first = ReportSemanticService(c).summary(did)
        second = ReportSemanticService(c).summary(did)
        assert first == second and len(first['report_semantic_content_hash']) == 64


def test_reporting_api_role_permissions(migrated_database, test_database_url, report_world):
    did = report_world.dataset_version_id
    credentials = make_url(settings.database_url_api.get_secret_value())
    engine = create_engine(make_url(test_database_url).set(username=credentials.username,password=credentials.password), isolation_level='AUTOCOMMIT', hide_parameters=True)
    try:
        with engine.connect() as c:
            for name in CANONICAL_VIEWS:
                c.execute(text(f'SELECT * FROM reporting.{name} WHERE dataset_version_id=:did LIMIT 1'), {'did': did})
            for target in ('evaluation.scenario_truth','platform.supply_demand_snapshots','platform.stockpile_records'):
                with pytest.raises(DBAPIError) as caught:
                    c.execute(text(f'SELECT * FROM {target} LIMIT 1'))
                assert caught.value.orig.sqlstate == '42501'
    finally:
        engine.dispose()
