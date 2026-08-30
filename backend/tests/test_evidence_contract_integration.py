"""Actual REST -> Adapter -> canonical joins over a disposable synthetic world."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from alembic import command
from sqlalchemy import text

from app.system_b.analytics.service import AnalyticsService
from app.system_b.analytics.calculations import calculate_forecast_change
from app.system_b.analytics.models import Availability
from tests.conftest import alembic_config
from tests.test_report_api import api_world, client
from tests.test_operational_integration import operational_worlds
from tests.test_forecast_integration import forecast_worlds
from tests.test_system_b_adapter import adapter_for

pytestmark = pytest.mark.integration


@pytest.fixture()
def adapter(client):
    def handler(request):
        path = "/api/v1/" + request.url.path.split("/api/v1/", 1)[1]
        response = client.get(path, params=dict(request.url.params))
        return httpx.Response(response.status_code, content=response.content)
    with adapter_for(handler) as result:
        yield result


def test_real_cross_report_join_and_po_consumption(adapter, api_world, migrated_database):
    did = api_world.dataset_version_id
    # Current stockpile membership need not overlap overdue POs. Select a real
    # historical record for the join test rather than fabricating current membership.
    with migrated_database.connect() as c:
        sid, vid = c.execute(text(
            "SELECT p.po_line_schedule_id,h.stockpile_version_id FROM reporting.report1_overdue_po_detail p "
            "JOIN reporting.report6_stockpile_history h USING(dataset_version_id,material_id) "
            "JOIN reporting.report4_latest_13w_forecast w USING(dataset_version_id,material_id) "
            "WHERE p.dataset_version_id=:did AND h.is_valid AND h.stockpile_record_id IS NOT NULL "
            "AND w.thirteen_week_demand_qty>0 "
            "ORDER BY p.po_line_schedule_id,h.version_date,h.sequence_no LIMIT 1"
        ), {"did": did}).one()
    po = adapter.purchase_orders(did, po_line_schedule_id=sid).items[0]
    stockpile = adapter.stockpile(did, stockpile_version_id=vid, material_id=po.material_id).items[0]
    material = adapter.material_supply_demand(did, material_id=po.material_id).items[0]
    weekly = adapter.latest_13w_forecast(did, material_id=po.material_id).items[0]
    history = adapter.forecast_history(did, po_line_schedule_id=po.po_line_schedule_id, page_size=500).items
    configs = adapter.product_configurations(did, material_id=po.material_id, page_size=500).items
    assert history and configs
    assert {row.material_id for row in (po, material, weekly, stockpile, *history, *configs)} == {po.material_id}
    assert po.organization_id == weekly.organization_id == material.organization_id
    project_ids = {row.project_id for row in configs}
    assert po.po_reference_project_id in project_ids
    assert {row.project_id for row in history} <= project_ids
    assert {row.project_id for row in weekly.project_contributions} <= project_ids
    assert po.po_header_id and po.po_line_id and po.supplier_id and material.mpm.employee_id
    result = AnalyticsService.analyze_purchase_order(po, weekly)
    assert result.consumption.status == Availability.AVAILABLE
    assert result.consumption.estimated_consumption_weeks is not None
    with migrated_database.connect() as c:
        parent = c.execute(text("SELECT l.po_header_id,l.po_line_id,l.material_id FROM platform.po_lines l "
                                "JOIN platform.po_line_schedules s USING(dataset_version_id,po_line_id) "
                                "WHERE s.dataset_version_id=:did AND s.po_line_schedule_id=:sid"),
                           {"did": did, "sid": po.po_line_schedule_id}).one()
        assert tuple(parent) == (po.po_header_id, po.po_line_id, po.material_id)


def test_week_dates_project_quantities_and_source_version_reconcile(adapter, api_world, migrated_database):
    did = api_world.dataset_version_id
    for row in adapter.latest_13w_forecast(did, page_size=500).items:
        totals = defaultdict(Decimal)
        for contribution in row.project_contributions:
            totals[contribution.week_index] += contribution.forecast_qty
        assert all(totals[week.week_index] == week.forecast_qty for week in row.weeks)
        assert sum(totals.values(), Decimal(0)) == row.thirteen_week_demand_qty
        assert all(week.week_start_date.weekday() == 0 for week in row.weeks)
        with migrated_database.connect() as c:
            identity = c.execute(text("SELECT snapshot_date,source_forecast_version_id FROM platform.weekly_forecast_snapshots "
                                      "WHERE dataset_version_id=:did AND weekly_forecast_snapshot_id=:sid"),
                                 {"did": did, "sid": row.weekly_forecast_snapshot_id}).one()
        assert tuple(identity) == (row.forecast_snapshot_date, row.source_forecast_version_id)


def test_forecast_chronology_and_same_period_comparison(adapter, api_world, migrated_database):
    did = api_world.dataset_version_id
    po = adapter.purchase_orders(did, page_size=1).items[0]
    rows = adapter.forecast_history(did, po_line_schedule_id=po.po_line_schedule_id, page_size=500).items
    groups = defaultdict(list)
    with migrated_database.connect() as c:
        versions = {row.forecast_version_id: row for row in c.execute(text(
            "SELECT forecast_version_id,version_date,sequence_no,is_valid FROM platform.forecast_versions WHERE dataset_version_id=:did"
        ), {"did": did})}
    for row in rows:
        source = versions[row.forecast_version_id]
        assert source.is_valid and source.sequence_no == row.forecast_version_sequence
        assert source.sequence_no == max(v.sequence_no for v in versions.values() if v.is_valid and v.version_date == source.version_date)
        assert row.horizon_start_month <= row.forecast_month < row.horizon_end_month_exclusive
        groups[row.project_id, row.forecast_month].append(row)
    comparable = next(values for values in groups.values() if len(values) >= 2)
    ordered = sorted(comparable, key=lambda row: (row.forecast_version_date, row.forecast_version_sequence))
    old, new = ordered[:2]
    assert old.forecast_version_id != new.forecast_version_id and old.forecast_version_date < new.forecast_version_date
    result = calculate_forecast_change(old, new)
    assert result.forecast_change_qty == new.forecast_qty - old.forecast_qty
    selected = adapter.forecast_history(did, po_line_schedule_id=po.po_line_schedule_id,
                                        project_id=old.project_id, forecast_version_id=old.forecast_version_id).items
    assert selected and all(row.forecast_version_id == old.forecast_version_id for row in selected)


def test_stockpile_history_boundaries_and_missing_states(adapter, api_world, migrated_database):
    did = api_world.dataset_version_id
    snapshot = adapter.get_dataset(did).snapshot_date
    with migrated_database.connect() as c:
        versions = list(c.execute(text("SELECT stockpile_version_id,version_date,sequence_no,is_valid FROM platform.stockpile_versions "
                                       "WHERE dataset_version_id=:did ORDER BY version_date,sequence_no"), {"did": did}))
    valid = [v for v in versions if v.is_valid and v.version_date <= snapshot]
    assert any(v.version_date > snapshot for v in versions)
    dates = {valid[0].version_date - timedelta(days=1), valid[0].version_date,
             valid[0].version_date + timedelta(days=1), snapshot}
    dates.update(v.version_date for v in valid if v.sequence_no > 1)
    for as_of in sorted(dates):
        expected = max((v for v in valid if v.version_date <= as_of), key=lambda v: (v.version_date, v.sequence_no), default=None)
        result = adapter.stockpile(did, as_of_date=as_of, page_size=500)
        assert result.stockpile_selection.stockpile_version_id == (expected.stockpile_version_id if expected else None)
        assert all(row.stockpile_version_date <= as_of for row in result.items)
        assert result == adapter.stockpile(did, as_of_date=as_of, page_size=500)
    missing = adapter.stockpile(did, as_of_date=snapshot, material_id=UUID(int=1))
    assert missing.total == 0 and missing.stockpile_selection.stockpile_version_id is not None


def test_stockpile_version_children_and_each_po_order_date(adapter, api_world, migrated_database):
    did = api_world.dataset_version_id
    orders = adapter.purchase_orders(did, page_size=500).items
    # Several schedules include repeated materials with independently dated evidence.
    for po in orders[:8]:
        result = adapter.stockpile(did, material_id=po.material_id, as_of_date=po.order_date)
        with migrated_database.connect() as c:
            vid = c.scalar(text("SELECT stockpile_version_id FROM platform.stockpile_versions WHERE dataset_version_id=:did "
                                "AND is_valid AND version_date<=:day ORDER BY version_date DESC,sequence_no DESC LIMIT 1"),
                           {"did": did, "day": po.order_date})
        assert result.stockpile_selection.stockpile_version_id == vid
    historical = adapter.stockpile(did, as_of_date=orders[0].snapshot_date - timedelta(days=21), page_size=500)
    assert historical.items
    vid = historical.stockpile_selection.stockpile_version_id
    exact = adapter.stockpile(did, stockpile_version_id=vid, page_size=500)
    assert exact.items == historical.items
    with migrated_database.connect() as c:
        for row in historical.items:
            params = {"did": did, "vid": vid, "mid": row.material_id}
            actual = c.scalar(text("SELECT actual_stockpile_qty FROM platform.stockpile_records "
                                   "WHERE dataset_version_id=:did AND stockpile_version_id=:vid AND material_id=:mid"), params)
            months = list(c.execute(text("SELECT forecast_month,forecast_qty FROM platform.stockpile_forecasts "
                                         "WHERE dataset_version_id=:did AND stockpile_version_id=:vid AND material_id=:mid ORDER BY forecast_month"), params))
            assert row.actual_stockpile_qty == actual
            assert [(m.period, m.quantity) for m in row.future_months] == [tuple(m) for m in months]
            ages = list(c.execute(text("SELECT age_threshold_days,age_qty FROM platform.stockpile_inventory_age_buckets "
                                       "WHERE dataset_version_id=:did AND stockpile_version_id=:vid AND material_id=:mid ORDER BY age_threshold_days"), params))
            assert [(a.threshold_days, a.quantity) for a in row.inventory_age_quantities] == [tuple(a) for a in ages]
            assert row.agreement_unit_price is None  # No current price attached to history.


def test_temporal_and_dataset_filters_reject_unavailable_evidence(client, adapter, api_world, operational_worlds):
    did = api_world.dataset_version_id
    snapshot = adapter.get_dataset(did).snapshot_date
    base = {"dataset_version_id": str(did)}
    assert client.get("/api/v1/reports/stockpile", params=base | {"as_of_date": str(snapshot + timedelta(days=1))}).status_code == 422
    other = adapter.stockpile(operational_worlds[1].dataset_version_id).stockpile_selection.stockpile_version_id
    assert client.get("/api/v1/reports/stockpile", params=base | {"stockpile_version_id": str(other)}).status_code == 422
    material = adapter.purchase_orders(did, page_size=1).items[0].material_id
    assert adapter.material_supply_demand(operational_worlds[1].dataset_version_id, material_id=material).items == ()


def test_012_upgrade_downgrade_preserves_existing_facts(migrated_database, api_world, test_database_url):
    config = alembic_config(test_database_url)
    with migrated_database.connect() as c:
        before = c.scalar(text("SELECT md5(string_agg(row_to_json(t)::text,',' ORDER BY stockpile_record_id)) "
                               "FROM platform.stockpile_records t WHERE dataset_version_id=:did"), {"did": api_world.dataset_version_id})
    command.downgrade(config, "011_report_semantic_views")
    command.upgrade(config, "head")
    with migrated_database.connect() as c:
        after = c.scalar(text("SELECT md5(string_agg(row_to_json(t)::text,',' ORDER BY stockpile_record_id)) "
                              "FROM platform.stockpile_records t WHERE dataset_version_id=:did"), {"did": api_world.dataset_version_id})
    assert before == after
