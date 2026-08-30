from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from uuid import UUID

from sqlalchemy import text

from app.reporting.report_header_manifest import get_report_manifest
from app.services.report_queries import REPORTS, ReportQueryService


REPORT_FILENAMES = {
    1: "report1_overdue_po_detail.xlsx",
    2: "report2_material_supply_demand.xlsx",
    3: "report3_forecast_history.xlsx",
    4: "report4_latest_13w_forecast.xlsx",
    5: "report5_product_configuration.xlsx",
    6: "report6_stockpile_detail.xlsx",
}


class ReportExcelExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExportResult:
    report_id: int
    output_path: Path
    row_count: int
    sheet_count: int


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _month_add(day, offset):
    month = day.month - 1 + offset
    return date(day.year + month // 12, month % 12 + 1, 1)


class ReportExcelExporter:
    def __init__(self, executor, *, node_executable=None, node_modules=None):
        self.executor = executor
        self.node_executable = node_executable or os.getenv("REPORT_EXPORT_NODE") or shutil.which("node")
        configured_modules = node_modules or os.getenv("REPORT_EXPORT_NODE_MODULES")
        local_modules = Path(__file__).with_name("node_modules")
        self.node_modules = configured_modules or (str(local_modules) if local_modules.is_dir() else None)

    def _dataset(self, name):
        return ReportQueryService(self.executor).select_dataset(None, name)

    def _static_rows(self, report_id, dataset_id):
        definition = REPORTS[report_id]
        return [dict(row) for row in self.executor.execute(text(
            f"SELECT * FROM reporting.{definition['view']} WHERE dataset_version_id=:did ORDER BY {definition['order']}"
        ), {"did": dataset_id}).mappings()]

    def _report3_sheets(self, dataset):
        rows = self._static_rows(3, dataset.dataset_version_id)
        fields = [column["canonical_field"] for column in get_report_manifest(3)["columns"]]
        static = [field for field in fields if not field.startswith("forecast_qty_m")]
        grouped = {}
        for row in rows:
            key = (row["po_line_schedule_id"], row["material_id"], row["project_id"], row["forecast_version_id"])
            item = grouped.setdefault(key, {field: row.get(field) for field in static})
            index = (row["forecast_month"].year - row["forecast_version_date"].year) * 12 + row["forecast_month"].month - row["forecast_version_date"].month
            if 0 <= index <= 6:
                item[f"forecast_qty_m{index}"] = row["forecast_qty"]
        by_version = defaultdict(list)
        for item in grouped.values():
            by_version[(item["forecast_version_date"], item["forecast_version_name"])].append(item)
        sheets = []
        for (version_date, version_name), values in sorted(by_version.items()):
            overrides = {f"forecast_qty_m{i}": _month_add(version_date.replace(day=1), i).strftime("%Y%m") for i in range(7)}
            safe_name = f"{version_date:%Y%m%d}-{version_name}"[:31].replace("/", "-").replace("\\", "-")
            sheets.append(self._sheet_payload(3, safe_name, values, overrides))
        return sheets

    def _report6_rows(self, dataset):
        rows = self._static_rows(6, dataset.dataset_version_id)
        forecasts = defaultdict(dict)
        for row in self.executor.execute(text(
            "SELECT material_id,month_index,forecast_month,forecast_qty FROM reporting.report6_stockpile_forecast_long "
            "WHERE dataset_version_id=:did ORDER BY material_id,month_index"
        ), {"did": dataset.dataset_version_id}).mappings():
            forecasts[row["material_id"]][row["month_index"]] = row
        ages = defaultdict(dict)
        for row in self.executor.execute(text(
            "SELECT material_id,age_threshold_days,age_qty FROM reporting.report6_stockpile_age_long "
            "WHERE dataset_version_id=:did ORDER BY material_id,age_threshold_days"
        ), {"did": dataset.dataset_version_id}).mappings():
            ages[row["material_id"]][row["age_threshold_days"]] = row["age_qty"]
        for row in rows:
            for index, item in forecasts[row["material_id"]].items():
                row[f"future_month_{index:02d}_demand_qty"] = item["forecast_qty"]
            for threshold in (30, 60, 90, 120, 150, 180, 270, 365):
                row[f"inventory_age_over_{threshold}d_qty"] = ages[row["material_id"]].get(threshold)
        return rows

    def _sheet_payload(self, report_id, sheet_name, rows, header_overrides=None):
        manifest = get_report_manifest(report_id)
        columns = manifest["columns"]
        return {
            "name": sheet_name,
            "fields": [column["canonical_field"] for column in columns],
            "rows": [[_json_value(row.get(column["canonical_field"])) for column in columns] for row in rows],
            "header_overrides": header_overrides or {},
        }

    def prepare(self, report_id, dataset_version_name):
        dataset = self._dataset(dataset_version_name)
        manifest = get_report_manifest(report_id)
        if report_id == 3:
            sheets = self._report3_sheets(dataset)
        elif report_id == 6:
            rows = self._report6_rows(dataset)
            version_date = rows[0]["stockpile_version_date"] if rows else dataset.snapshot_date
            overrides = {f"future_month_{i:02d}_demand_qty": _month_add(version_date.replace(day=1), i).strftime("%Y%m") for i in range(1, 7)}
            sheets = [self._sheet_payload(6, manifest["sheet_name"], rows, overrides)]
        else:
            rows = self._static_rows(report_id, dataset.dataset_version_id)
            overrides = {}
            if report_id == 4:
                start = dataset.snapshot_date + timedelta(days=(7 - dataset.snapshot_date.weekday()) % 7)
                overrides = {f"week_{i:02d}_forecast_qty": (start + timedelta(days=7 * (i - 1))).isoformat() for i in range(1, 14)}
            sheets = [self._sheet_payload(report_id, manifest["sheet_name"], rows, overrides)]
        return {"report_id": report_id, "manifest": manifest, "sheets": sheets}

    def export(self, report_id, dataset_version_name, output_dir):
        if report_id not in REPORT_FILENAMES:
            raise ReportExcelExportError("UNKNOWN_REPORT")
        if not self.node_executable:
            raise ReportExcelExportError("XLSX_NODE_RUNTIME_NOT_CONFIGURED")
        payload = self.prepare(report_id, dataset_version_name)
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / REPORT_FILENAMES[report_id]
        runtime_script = Path(__file__).with_name("xlsx_runtime.mjs")
        with tempfile.TemporaryDirectory(prefix="system-a-xlsx-") as temp_name:
            temp = Path(temp_name)
            if self.node_modules:
                try:
                    os.symlink(Path(self.node_modules), temp / "node_modules", target_is_directory=True)
                except OSError:
                    link = subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(temp / "node_modules"), str(Path(self.node_modules))],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                    )
                    if link.returncode:
                        raise ReportExcelExportError("XLSX_NODE_MODULE_LINK_FAILED")
            shutil.copy2(runtime_script, temp / runtime_script.name)
            input_path = temp / "input.json"
            input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [self.node_executable, str(temp / runtime_script.name), "build", str(input_path), str(output_path)],
                cwd=temp, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
            )
            if result.returncode:
                raise ReportExcelExportError("XLSX_BUILD_FAILED")
        return ExportResult(report_id, output_path, sum(len(sheet["rows"]) for sheet in payload["sheets"]), len(payload["sheets"]))

    def inspect(self, report_id, dataset_version_name, workbook_path):
        if not self.node_executable:
            raise ReportExcelExportError("XLSX_NODE_RUNTIME_NOT_CONFIGURED")
        payload = self.prepare(report_id, dataset_version_name)
        specification = {
            "workbook_path": str(Path(workbook_path).resolve()),
            "manifest": payload["manifest"],
            "sheets": [{"name": sheet["name"], "row_count": len(sheet["rows"])} for sheet in payload["sheets"]],
        }
        runtime_script = Path(__file__).with_name("xlsx_runtime.mjs")
        with tempfile.TemporaryDirectory(prefix="system-a-xlsx-inspect-") as temp_name:
            temp = Path(temp_name)
            if self.node_modules:
                try:
                    os.symlink(Path(self.node_modules), temp / "node_modules", target_is_directory=True)
                except OSError:
                    link = subprocess.run(["cmd", "/c", "mklink", "/J", str(temp / "node_modules"), str(Path(self.node_modules))],
                                          capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
                    if link.returncode:
                        raise ReportExcelExportError("XLSX_NODE_MODULE_LINK_FAILED")
            shutil.copy2(runtime_script, temp / runtime_script.name)
            input_path, result_path = temp / "inspect.json", temp / "result.json"
            input_path.write_text(json.dumps(specification, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([self.node_executable, str(temp / runtime_script.name), "inspect", str(input_path), str(result_path)],
                                    cwd=temp, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            if result.returncode:
                raise ReportExcelExportError("XLSX_INSPECTION_FAILED")
            return json.loads(result_path.read_text(encoding="utf-8"))
