"""Exact template metadata only: no workbook business rows or database facts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest

from app.reporting.report_header_manifest import (
    MANIFEST_PATH, get_report_manifest, manifest_content_hash,
    ordered_fields, render_markdown, validate_manifest,
)
from app.reporting.field_mapping import render_markdown as render_field_mapping


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('report_id,count', [(1, 37), (2, 106), (3, 23), (4, 44), (5, 22), (6, 60)])
def test_final_template_columns_and_source_structure(report_id, count):
    report = get_report_manifest(report_id)
    assert report['column_count'] == len(ordered_fields(report_id)) == count
    assert len(set(ordered_fields(report_id))) == count
    assert report['source_template'].startswith(f'报表{report_id}_')
    assert report['source_template'].endswith('_最终模板.xlsx')
    assert '(1)' not in report['source_template']
    assert report['sheet_structure'][0]['sheet_name'] == report['sheet_name']
    assert all('header_cells' in sheet and 'data_rows' not in sheet for sheet in report['sheet_structure'])
    raw = json.dumps(report['sheet_structure'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    assert hashlib.sha256(raw.encode()).hexdigest() == report['source_header_structure_sha256']


def test_report2_exact_template_order_not_document_group_order():
    columns = get_report_manifest(2)['columns']
    assert columns[51]['display_name'] == '最小包装'
    assert [(c['excel_column'], c['display_name']) for c in columns[-2:]] == [
        ('DA', '实际需求合计'), ('DB', '实际需求合计(试产)')]


def test_report6_exact_multilevel_headers_and_warning_position():
    columns = get_report_manifest(6)['columns']
    assert columns[26]['header_path'] == ['结余预测（库存-消耗）(万元)', '超30天未消耗', '数量']
    assert columns[27]['header_path'] == ['结余预测（库存-消耗）(万元)', '超30天未消耗', '金额']
    assert columns[38]['excel_column'] == 'AM'
    assert columns[38]['display_name'] == '囤料消耗预警'
    assert columns[39]['header_path'] == ['库龄分布(万元)', '超30天', '数量']
    assert columns[55]['display_name'] == '囤料呆滞预警'


@pytest.mark.parametrize('report_id,count,first_offset', [(3, 7, 0), (4, 13, 0), (6, 6, 1)])
def test_dynamic_slots_have_no_fixed_future_dates(report_id, count, first_offset):
    columns = [c for c in get_report_manifest(report_id)['columns'] if c['slot']]
    assert [c['slot']['slot_index'] for c in columns] == list(range(1, count + 1))
    assert [c['slot']['offset'] for c in columns] == list(range(first_offset, first_offset + count))
    assert not re.search(r'20\d{2}[-/]?\d{2}', json.dumps([c['slot'] for c in columns]))
    assert len({c['slot']['header_cell'] for c in columns}) == count


def test_manifest_canonical_mapping_matches_data_contract():
    contract = (ROOT / 'docs/DATA_CONTRACT.md').read_text(encoding='utf-8')
    sections = re.split(r'^## [3-8]\. Report ', contract, flags=re.M)[1:7]
    for rid, section in enumerate(sections, 1):
        section = re.split(r'^## ', section, flags=re.M)[0]
        if rid == 3:
            section = section.split('### 5.3')[0]
        mapping = {}
        for line in section.splitlines():
            cells = [cell.strip() for cell in line.split('|')]
            if not line.startswith('|') or len(cells) < 4 or not re.fullmatch(r'`[a-z][a-z0-9_]*`', cells[2]):
                continue
            if rid == 6 and re.fullmatch(r'`[a-z][a-z0-9_]*`', cells[3]):
                mapping[(cells[1], '数量')] = cells[2].strip('`')
                mapping[(cells[1], '金额')] = cells[3].strip('`')
            else:
                mapping[cells[1]] = cells[2].strip('`')
        for column in get_report_manifest(rid)['columns']:
            path = column['header_path']
            key = tuple(path[-2:]) if rid == 6 and len(path) == 3 else path[-1]
            assert column['canonical_field'] == mapping[key]
        assert set(mapping.values()) == set(ordered_fields(rid))


def test_markdown_is_exact_projection_of_machine_contract():
    assert (ROOT / 'docs/REPORT_HEADER_MANIFEST.md').read_text(encoding='utf-8').rstrip() == render_markdown().rstrip()
    mapping = (ROOT / 'docs/REPORT_FIELD_MAPPING.md').read_text(encoding='utf-8')
    assert mapping.rstrip() == render_field_mapping().rstrip()
    assert sum(1 for line in mapping.splitlines() if re.match(r'^\| [0-9]+ \|', line)) == sum(len(ordered_fields(rid)) for rid in range(1, 7))


def test_manifest_is_deterministic_and_caller_cannot_mutate_it():
    before = manifest_content_hash()
    report = get_report_manifest(2)
    report['columns'].reverse()
    report['sheet_structure'][0]['header_cells'].clear()
    assert get_report_manifest(2)['columns'][0]['column_index'] == 1
    assert get_report_manifest(2)['sheet_structure'][0]['header_cells']
    assert manifest_content_hash() == before


@pytest.mark.parametrize('value', [0, 7, True, '1', None])
def test_unknown_report_rejected(value):
    with pytest.raises(ValueError, match='UNKNOWN_REPORT_ID'):
        get_report_manifest(value)


@pytest.mark.parametrize('mutation,expected', [
    ('order', 'HEADER_COLUMN_ORDER_CHANGED'),
    ('label', 'EXACT_TEMPLATE_HEADER_MISMATCH'),
    ('source', 'SOURCE_HEADER_STRUCTURE_CHANGED'),
    ('slot', 'DYNAMIC_HEADER_ANCHOR_MISMATCH'),
    ('duplicate', 'DUPLICATE_CANONICAL_FIELD'),
    ('old_template', 'FINAL_TEMPLATE_REQUIRED'),
])
def test_manifest_rejects_contract_drift(mutation, expected):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    report = manifest['reports'][2]
    if mutation == 'order':
        report['columns'][0], report['columns'][1] = report['columns'][1], report['columns'][0]
    elif mutation == 'label':
        report['columns'][0]['display_name'] = 'changed'
    elif mutation == 'source':
        report['sheet_structure'][0]['header_cells']['A3'] = 'changed'
    elif mutation == 'slot':
        report['columns'][14]['slot']['offset'] = 5
    elif mutation == 'duplicate':
        report['columns'][1]['canonical_field'] = report['columns'][0]['canonical_field']
    elif mutation == 'old_template':
        report['source_template'] = 'template(1).xlsx'
    with pytest.raises(ValueError, match=expected):
        validate_manifest(manifest)


def test_auxiliary_term_and_unconfirmed_formulas_stay_explicit():
    column = next(c for c in get_report_manifest(2)['columns'] if c['canonical_field'] == 'kit_minimum_pack_demand_qty')
    assert column['classification'] == 'auxiliary'
    assert column['business_status'] == 'AUXILIARY_ONLY'
    assert column['business_confirmation_id'].startswith('DC-07-')
    assert any(c['business_status'] == 'DEFERRED_BUSINESS_FORMULA' for c in get_report_manifest(6)['columns'])


def test_manifest_has_no_answer_or_internal_display_columns():
    forbidden = {'expected_action', 'true_cause', 'causal_project_id', 'scenario_pattern',
                 'scenario_generation_key', 'dataset_version_id', 'content_hash'}
    for rid in range(1, 7):
        assert not forbidden.intersection(ordered_fields(rid))
