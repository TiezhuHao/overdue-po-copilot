"""Single ordered display contract shared by future views, APIs and exporters.

The JSON is authoritative. Markdown is generated from it; neither source facts
nor a database connection are needed to inspect or validate this contract.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re


MANIFEST_PATH = Path(__file__).with_suffix('.json')


def _coordinate(address):
    match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', address)
    if not match:
        raise ValueError('INVALID_HEADER_COORDINATE')
    column = 0
    for letter in match[1]:
        column = column * 26 + ord(letter) - ord('A') + 1
    return column, int(match[2])


def _column_name(index):
    result = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(ord('A') + remainder) + result
    return result


def _source_path(sheet, column):
    path, references = [], []
    merges = [tuple(map(_coordinate, value.split(':'))) for value in sheet['merges']]
    for row in sheet['header_rows']:
        address = f'{_column_name(column)}{row}'
        for start, end in merges:
            if start[0] <= column <= end[0] and start[1] <= row <= end[1]:
                address = f'{_column_name(start[0])}{start[1]}'
                break
        value = sheet['header_cells'].get(address)
        if value and (not path or value != path[-1]):
            path.append(value)
            references.append(address)
    return path, references


def validate_manifest(manifest):
    if manifest['manifest_version'] != 1:
        raise ValueError('UNSUPPORTED_HEADER_MANIFEST_VERSION')
    reports = manifest['reports']
    if [report['report_id'] for report in reports] != list(range(1, 7)):
        raise ValueError('INCOMPLETE_REPORT_HEADER_MANIFEST')
    approved_counts = {1: 37, 2: 106, 3: 23, 4: 44, 5: 22}
    for report in reports:
        rid = report['report_id']
        filename = report['source_template']
        if not filename.endswith('_最终模板.xlsx') or '(1)' in filename:
            raise ValueError('FINAL_TEMPLATE_REQUIRED')
        sheets = report['sheet_structure']
        raw = json.dumps(sheets, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if hashlib.sha256(raw.encode('utf-8')).hexdigest() != report['source_header_structure_sha256']:
            raise ValueError('SOURCE_HEADER_STRUCTURE_CHANGED')
        sheet = sheets[0]
        if sheet['sheet_name'] != report['sheet_name'] or sheet['header_rows'] != report['header_rows']:
            raise ValueError('HEADER_SHEET_MISMATCH')
        columns = report['columns']
        source_count = max(_coordinate(address)[0] for address in sheet['header_cells'])
        if len(columns) != report['column_count'] or len(columns) != source_count:
            raise ValueError('HEADER_COLUMN_COUNT_MISMATCH')
        if rid in approved_counts and len(columns) != approved_counts[rid]:
            raise ValueError('APPROVED_COLUMN_COUNT_MISMATCH')
        if len({column['canonical_field'] for column in columns}) != len(columns):
            raise ValueError('DUPLICATE_CANONICAL_FIELD')
        for index, column in enumerate(columns, 1):
            if column['column_index'] != index or column['excel_column'] != _column_name(index):
                raise ValueError('HEADER_COLUMN_ORDER_CHANGED')
            path, references = _source_path(sheet, index)
            if column['header_path'] != path or column['display_name'] != path[-1] or column['source_header_cells'] != references:
                raise ValueError('EXACT_TEMPLATE_HEADER_MISMATCH')
            if not re.fullmatch(r'[a-z][a-z0-9_]*', column['canonical_field']):
                raise ValueError('INVALID_CANONICAL_FIELD')
            if column['classification'] not in {'core', 'auxiliary'}:
                raise ValueError('INVALID_HEADER_CLASSIFICATION')
            if column['business_status'] not in manifest['status_definitions']:
                raise ValueError('INVALID_HEADER_BUSINESS_STATUS')
            if column['temporal_type'] != ('dynamic' if column['slot'] else 'static'):
                raise ValueError('HEADER_SLOT_TYPE_MISMATCH')
        dynamic = [column for column in columns if column['slot']]
        expected = {3: 7, 4: 13, 6: 6}.get(rid, 0)
        if [column['slot']['slot_index'] for column in dynamic] != list(range(1, expected + 1)):
            raise ValueError('INCOMPLETE_DYNAMIC_HEADER_SLOTS')
        for column in dynamic:
            slot = column['slot']
            anchor = {3: 'forecast_version_month', 4: 'monday_on_or_after_dataset_snapshot', 6: 'stockpile_version_month'}[rid]
            offset = slot['slot_index'] - (0 if rid == 6 else 1)
            if slot['semantic_anchor'] != anchor or slot['offset'] != offset:
                raise ValueError('DYNAMIC_HEADER_ANCHOR_MISMATCH')
            if slot['kind'] != ('week' if rid == 4 else 'month'):
                raise ValueError('DYNAMIC_HEADER_KIND_MISMATCH')
            if slot['header_cell'] != column['excel_column'] + ('4' if rid == 6 else '3'):
                raise ValueError('DYNAMIC_HEADER_CELL_MISMATCH')
            if slot['date_format'] != ('yyyy-mm-dd' if rid == 4 else 'YYYYMM'):
                raise ValueError('DYNAMIC_HEADER_FORMAT_MISMATCH')
    return manifest


_MANIFEST = validate_manifest(json.loads(MANIFEST_PATH.read_text(encoding='utf-8')))


def get_report_manifest(report_id):
    """Return an isolated copy so callers cannot mutate the shared contract."""
    if type(report_id) is not int or not 1 <= report_id <= 6:
        raise ValueError('UNKNOWN_REPORT_ID')
    return deepcopy(_MANIFEST['reports'][report_id - 1])


def ordered_fields(report_id):
    return tuple(column['canonical_field'] for column in get_report_manifest(report_id)['columns'])


def manifest_content_hash():
    payload = json.dumps(_MANIFEST, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def render_markdown():
    """Documentation projection only; this is not an Excel exporter."""
    lines = [
        '# 六报表精确表头清单', '',
        '唯一机器契约：`backend/app/reporting/report_header_manifest.json`。本文件由同名Python模块的render_markdown生成，不单独维护列序。', '',
        '仅提取明确标记“最终模板”的sheet结构、表头单元格和合并关系；未提取业务行，未把模板作为事实数据源。', '',
        'column_index从1开始。display_name为叶子标题；完整header_path保留多级结构、原始文字及标点。canonical_field取自DATA_CONTRACT，不按文档分组推断Excel顺序。', '',
        '动态槽位：Report 3为版本月M0～M+6；Report 4为snapshot当日或之后最近星期一起连续13周；Report 6为版本月下一自然月起连续6月。实际年月/日期由Phase6B exporter填充，manifest不固定未来日期。', '',
        'Report 2实际需求合计位于DA/DB；Report 6囤料消耗预警位于AM，在结余预测与库龄之间。Report 2标题合并只到CZ，但业务表头延伸到DB；以实际叶子列为准，不据标题宽度截列。', '',
        'CONFIRMED表示字段含义已固化，不保证可空来源一定有值；DEFERRED_BUSINESS_FORMULA保持空值，不编造辅助公式；AUXILIARY_ONLY只作展示，术语释义确认状态另行保留。core/auxiliary为字段用途，不是根因答案。', '',
        '后续Semantic View、API、Excel必须通过同一manifest取得字段顺序；长表以动态slot元数据定位透视列，不另建字段顺序清单。', '',
        '辅助sheet只登记结构与表头，不读取说明正文，也不将其当业务事实。Report 3版本日历原模板为4列；日内sequence是内部选择字段，不擅自增加模板列。', '',
        f'Manifest hash：`{manifest_content_hash()}`。', '',
    ]
    for report in _MANIFEST['reports']:
        lines += [f"## Report {report['report_id']}：{report['sheet_name']}", '',
                  f"来源：`{report['source_template']}`；业务列数：{report['column_count']}；表头行：{report['header_rows']}。", '',
                  f"只读表头结构指纹：`{report['source_header_structure_sha256']}`。", '',
                  '| Sheet | 表头行 | 角色 |', '|---|---|---|']
        for index, sheet in enumerate(report['sheet_structure']):
            lines.append(f"| {sheet['sheet_name']} | {sheet['header_rows']} | {'业务主表' if index == 0 else '辅助结构'} |")
        lines += ['', '| 列号 | Excel列 | display_name / 完整层级 | canonical_field | dynamic/static | core/auxiliary | business_status |',
                  '|---:|---|---|---|---|---|---|']
        for column in report['columns']:
            display = ' → '.join(column['header_path'])
            temporal = column['temporal_type']
            if column['slot']:
                temporal += f" ({column['slot']['kind']} {column['slot']['slot_index']})"
            lines.append(f"| {column['column_index']} | {column['excel_column']} | {display} | `{column['canonical_field']}` | {temporal} | {column['classification']} | {column['business_status']} |")
        lines.append('')
    return '\n'.join(lines)
