import re

import pytest
from sqlalchemy.orm import Session

from app.reporting.excel_export import ReportExcelExporter
from app.reporting.report_header_manifest import get_report_manifest
from app.models.platform import DatasetVersion
from tests.test_forecast_integration import forecast_worlds
from tests.test_operational_integration import operational_worlds


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def excel_exports(migrated_database, operational_worlds, tmp_path_factory):
    world = operational_worlds[0]
    output = tmp_path_factory.mktemp("six-report-exports")
    results, inspections, prepared = {}, {}, {}
    with Session(migrated_database) as session:
        exporter = ReportExcelExporter(session)
        dataset_name = session.get(DatasetVersion, world.dataset_version_id).version_name
        for report_id in range(1, 7):
            prepared[report_id] = exporter.prepare(report_id, dataset_name)
            results[report_id] = exporter.export(report_id, dataset_name, output)
            inspections[report_id] = exporter.inspect(report_id, dataset_name, results[report_id].output_path)
    return results, inspections, prepared


@pytest.mark.parametrize("report_id,count", [(1, 37), (2, 106), (3, 23), (4, 44), (5, 22), (6, 60)])
def test_excel_headers_exact(report_id, count, excel_exports):
    _, inspections, prepared = excel_exports
    manifest = get_report_manifest(report_id)
    assert len(manifest["columns"]) == count
    for sheet, source in zip(inspections[report_id]["sheets"], prepared[report_id]["sheets"], strict=True):
        expected = [source["header_overrides"].get(column["canonical_field"], column["display_name"])
                    for column in manifest["columns"]]
        assert sheet["headers"] == expected


@pytest.mark.parametrize("report_id", range(1, 7))
def test_excel_row_counts_and_reopen(report_id, excel_exports):
    results, inspections, prepared = excel_exports
    rows = sum(len(sheet["rows"]) for sheet in prepared[report_id]["sheets"])
    assert results[report_id].output_path.is_file() and results[report_id].output_path.stat().st_size > 0
    assert results[report_id].row_count == rows
    assert sum(1 for sheet in inspections[report_id]["sheets"] if sheet["after_last_blank"]) == results[report_id].sheet_count
    assert all(sheet["preview_bytes"] > 1000 for sheet in inspections[report_id]["sheets"])
    assert "matched 0 entries" in inspections[report_id]["formula_error_scan"]


def test_report3_excel_pivot_and_dynamic_months(excel_exports):
    results, inspections, prepared = excel_exports
    assert results[3].sheet_count == len(prepared[3]["sheets"]) > 1
    for sheet in inspections[3]["sheets"]:
        assert all(re.fullmatch(r"\d{6}", value) for value in sheet["headers"][14:21])


def test_report4_excel_thirteen_monday_weeks(excel_exports):
    headers = excel_exports[1][4]["sheets"][0]["headers"][29:42]
    from datetime import date
    days = [date.fromisoformat(value) for value in headers]
    assert len(days) == 13 and all(day.weekday() == 0 for day in days)
    assert all((later - earlier).days == 7 for earlier, later in zip(days, days[1:]))


def test_report6_excel_six_natural_months(excel_exports):
    headers = excel_exports[1][6]["sheets"][0]["headers"][20:26]
    assert headers == ["202609", "202610", "202611", "202612", "202701", "202702"]


def test_excel_unknown_business_fields_remain_blank(excel_exports):
    _, inspections, prepared = excel_exports
    for report_id in (2, 4, 6):
        manifest = get_report_manifest(report_id)
        deferred = [index for index, column in enumerate(manifest["columns"])
                    if column["business_status"] == "DEFERRED_BUSINESS_FORMULA"]
        for sheet_index, sheet in enumerate(inspections[report_id]["sheets"]):
            if prepared[report_id]["sheets"][sheet_index]["rows"]:
                assert all(sheet["first_row"][index] in (None, "") for index in deferred)


def test_excel_roundtrip_representative_values(excel_exports):
    _, inspections, prepared = excel_exports
    for report_id in range(1, 7):
        expected = prepared[report_id]["sheets"][0]["rows"][0]
        actual = inspections[report_id]["sheets"][0]["first_row"]
        manifest = get_report_manifest(report_id)
        material_index = next((i for i, column in enumerate(manifest["columns"])
                               if column["canonical_field"] == "material_code"), None)
        if material_index is not None:
            assert actual[material_index] == expected[material_index]
        quantity_index = next((i for i, column in enumerate(manifest["columns"])
                               if column["canonical_field"].endswith("qty") and expected[i] is not None), None)
        if quantity_index is not None:
            assert float(actual[quantity_index]) == pytest.approx(float(expected[quantity_index]))
