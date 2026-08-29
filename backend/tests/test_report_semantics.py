from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app.reporting.calculations import estimated_consumption
from app.reporting.report_header_manifest import get_report_manifest, ordered_fields
from app.reporting.view_definitions import CANONICAL_VIEWS, create_statements


@pytest.mark.parametrize('qty,average,months,status', [
    (Decimal('10'), Decimal('0'), None, 'NO_FORECAST_DEMAND'),
    (Decimal('52'), Decimal('12'), Decimal('1'), 'FORECAST_AVAILABLE'),
])
def test_estimated_consumption(qty, average, months, status):
    result = estimated_consumption(qty, average)
    assert result == {'estimated_consumption_months': months, 'consumption_status': status}


@pytest.mark.parametrize('qty,average', [(Decimal('-1'), Decimal('1')), (Decimal('1'), Decimal('-1'))])
def test_estimated_consumption_rejects_negative_input(qty, average):
    with pytest.raises(ValueError, match='NEGATIVE_CONSUMPTION_INPUT'):
        estimated_consumption(qty, average)


def test_sql_defines_six_canonical_views_without_evaluation_dependency():
    assert len(CANONICAL_VIEWS) == 6
    sql = '\n'.join(create_statements()).lower()
    assert all(f'create view reporting.{name}' in sql for name in CANONICAL_VIEWS)
    assert 'evaluation.' not in sql and 'scenario_truth' not in sql
    assert 'date.today' not in sql and 'current_date' not in sql


@pytest.mark.parametrize('report_id', range(1, 7))
def test_semantic_sql_projection_follows_manifest(report_id):
    name = CANONICAL_VIEWS[report_id - 1]
    projection_name = 'report3_forecast_history_long' if report_id == 3 else name
    sql = next(value for value in create_statements() if value.startswith(f'CREATE VIEW reporting.{projection_name} '))
    manifest = get_report_manifest(report_id)
    expected = [c['canonical_field'] for c in manifest['columns'] if not c['slot'] or report_id == 4]
    positions = [sql.find(f' AS {field}') for field in expected]
    assert all(position >= 0 for position in positions)
    assert positions == sorted(positions)


def test_dynamic_semantics_remain_long_except_fixed_thirteen_week_slots():
    assert [c['canonical_field'] for c in get_report_manifest(3)['columns'] if c['slot']] == list(ordered_fields(3))[14:21]
    assert 'forecast_month' in next(s for s in create_statements() if s.startswith('CREATE VIEW reporting.report3_forecast_history_long'))
    assert 'month_index' in next(s for s in create_statements() if s.startswith('CREATE VIEW reporting.report6_stockpile_forecast_long'))
    assert 'week_13_forecast_qty' in next(s for s in create_statements() if s.startswith('CREATE VIEW reporting.report4_latest_13w_forecast'))


def test_public_semantic_summary_is_aggregate_only():
    summary = json.loads((Path(__file__).resolve().parents[2] / 'examples/report_semantic_summary.json').read_text(encoding='utf-8'))
    payload = json.dumps(summary).lower()
    assert summary['cross_report_orphan_count'] == 0
    assert not any(term in payload for term in ('true_cause', 'causal_project', 'scenario_pattern', 'expected_action'))
