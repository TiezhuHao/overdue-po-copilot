from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.reporting.report_header_manifest import get_report_manifest
from app.schemas.evidence import evidence_fields
from app.services.evidence_queries import enriched_source, HISTORICAL_STOCKPILE_SOURCE, weekly_details


class ReportQueryError(ValueError):
    pass


@dataclass(frozen=True)
class SelectedDataset:
    dataset_version_id: UUID
    dataset_version_name: str
    snapshot_date: Any
    status: str
    generation_signature: str
    business_content_hash: str | None


REPORTS = {
    1: {
        "view": "report1_overdue_po_detail",
        "order": "overdue_days DESC, po_number, po_line_number, shipment_number, po_line_schedule_id",
        "filters": {
            "material_code": "material_code = :material_code",
            "supplier": "(supplier_code = :supplier OR supplier_name ILIKE :supplier_like)",
            "buyer": "(order_buyer_name ILIKE :buyer_like OR default_buyer_name ILIKE :buyer_like)",
            "project": "(reference_project_code = :project OR reference_project_name ILIKE :project_like)",
            "po_number": "po_number = :po_number",
        },
    },
    2: {
        "view": "report2_material_supply_demand",
        "order": "material_code, material_id",
        "filters": {
            "material_code": "material_code = :material_code",
            "mpm": "(mpm_code = :mpm OR mpm_name ILIKE :mpm_like)",
        },
    },
    3: {
        "view": "report3_forecast_history",
        "order": "po_line_schedule_id, window_position, forecast_version_date, project_name, forecast_month, project_id, forecast_version_id",
        "filters": {
            "material_code": "r.material_code = :material_code",
            "project": "r.project_name ILIKE :project_like",
            "forecast_version": "(r.forecast_version_name = :forecast_version OR r.forecast_version_date::text = :forecast_version)",
            "window_role": "r.window_role = :window_role",
            "po_number": "EXISTS (SELECT 1 FROM reporting.report1_overdue_po_detail p WHERE p.dataset_version_id=r.dataset_version_id AND p.po_line_schedule_id=r.po_line_schedule_id AND p.po_number=:po_number)",
        },
    },
    4: {
        "view": "report4_latest_13w_forecast",
        "order": "material_code, material_id",
        "filters": {"material_code": "material_code = :material_code"},
    },
    5: {
        "view": "report5_product_configuration",
        "order": "project_name, product_config_name, product_config_version, material_code, product_config_id, material_id",
        "filters": {
            "project": "project_name ILIKE :project_like",
            "material_code": "material_code = :material_code",
            "business_unit": "business_unit_name ILIKE :business_unit_like",
            "planning_department": "planning_department_name ILIKE :planning_department_like",
            "lifecycle": "lifecycle_stage = :lifecycle",
        },
    },
    6: {
        "view": "report6_stockpile_detail",
        "order": "material_code, stockpile_record_id",
        "filters": {"material_code": "material_code = :material_code"},
    },
}

# Stable selectors supplement, never replace, display filters.
for report_id, names in {
    1: ("material_id", "po_line_schedule_id", "po_header_id", "po_line_id", "po_reference_project_id"),
    2: ("material_id",), 3: ("material_id", "project_id", "po_line_schedule_id", "forecast_version_id"),
    4: ("material_id",), 5: ("material_id", "project_id"), 6: ("material_id",),
}.items():
    prefix = "r." if report_id == 3 else ""
    REPORTS[report_id]["filters"].update({key: f"{prefix}{key}=:{key}" for key in names})


class ReportQueryService:
    def __init__(self, executor):
        self.executor = executor

    def select_dataset(self, dataset_version_id=None, dataset_version_name=None) -> SelectedDataset:
        if dataset_version_id and dataset_version_name:
            raise ReportQueryError("MULTIPLE_DATASET_SELECTORS")
        params = {}
        if dataset_version_id:
            predicate, params = "dataset_version_id=:did", {"did": dataset_version_id}
        elif dataset_version_name:
            predicate, params = "version_name=:name", {"name": dataset_version_name}
        else:
            predicate = "status='READY'"
        row = self.executor.execute(text(
            "SELECT dataset_version_id,version_name,snapshot_date,status,generation_signature,business_content_hash "
            f"FROM platform.dataset_versions WHERE {predicate} ORDER BY snapshot_date DESC,generated_at DESC,dataset_version_id DESC LIMIT 1"
        ), params).mappings().first()
        if row is None:
            raise ReportQueryError("NO_READY_DATASET" if not (dataset_version_id or dataset_version_name) else "DATASET_NOT_FOUND")
        return SelectedDataset(row["dataset_version_id"], row["version_name"], row["snapshot_date"], row["status"],
                               row["generation_signature"], row["business_content_hash"])

    def list_datasets(self):
        return list(self.executor.execute(text(
            "SELECT dataset_version_id,version_name dataset_version_name,snapshot_date,status,generation_signature,business_content_hash "
            "FROM platform.dataset_versions ORDER BY snapshot_date DESC,generated_at DESC,dataset_version_id DESC"
        )).mappings())

    def get_dataset(self, dataset_id):
        return self.executor.execute(text(
            "SELECT dataset_version_id,version_name dataset_version_name,snapshot_date,status,generation_signature,business_content_hash "
            "FROM platform.dataset_versions WHERE dataset_version_id=:did"
        ), {"did": dataset_id}).mappings().first()

    def page(self, report_id, dataset, page, page_size, filters, *, source_override=None):
        definition = REPORTS[report_id]
        alias = "r" if report_id == 3 else ""
        source = source_override or enriched_source(report_id, definition["view"])
        clauses = [(("r." if alias else "") + "dataset_version_id=:did")]
        params: dict[str, Any] = {"did": dataset.dataset_version_id, "limit": page_size, "offset": (page - 1) * page_size}
        if report_id == 6 and filters.get("_selected_version") is not None:
            clauses.append("stockpile_version_id=:selected_version")
            params["selected_version"] = filters["_selected_version"]
        for key, value in filters.items():
            if value is None or key not in definition["filters"]:
                continue
            clauses.append(definition["filters"][key])
            params[key] = value
            params[key + "_like"] = f"%{value}%"
        if report_id == 2 and filters.get("surplus_sign"):
            signs = {"positive": "> 0", "zero": "= 0", "negative": "< 0"}
            sign = filters["surplus_sign"]
            if sign not in signs:
                raise ReportQueryError("INVALID_SURPLUS_SIGN")
            clauses.append(f"supply_demand_surplus_qty {signs[sign]}")
        where = " AND ".join(clauses)
        total = self.executor.scalar(text(f"SELECT count(*) FROM {source} WHERE {where}"), params)
        rows = list(self.executor.execute(text(
            f"SELECT * FROM {source} WHERE {where} ORDER BY {definition['order']} LIMIT :limit OFFSET :offset"
        ), params).mappings())
        public = [self._public_row(report_id, dict(row)) for row in rows]
        if report_id == 4:
            weekly_details(self.executor, dataset.dataset_version_id, public)
        return total, public

    @staticmethod
    def _public_row(report_id, row):
        fields = [column["canonical_field"] for column in get_report_manifest(report_id)["columns"]
                  if not column["slot"] or report_id == 4]
        result = {field: row.get(field) for field in fields}
        result.update({field: row.get(field) for field in evidence_fields(report_id)})
        if report_id == 3:
            result.update({key: row[key] for key in ("po_line_schedule_id", "forecast_month", "forecast_qty", "window_role")})
        return result

    def report6_page(self, dataset, page, page_size, filters):
        as_of = filters.get("as_of_date") or dataset.snapshot_date
        if as_of > dataset.snapshot_date:
            raise ReportQueryError("AS_OF_AFTER_DATASET_SNAPSHOT")
        params = {"did": dataset.dataset_version_id, "as_of": as_of}
        predicate = ""
        if filters.get("stockpile_version_id") is not None:
            predicate = " AND stockpile_version_id=:vid"
            params["vid"] = filters["stockpile_version_id"]
        version = self.executor.execute(text(
            "SELECT DISTINCT stockpile_version_id,version_date,sequence_no FROM reporting.report6_stockpile_history "
            "WHERE dataset_version_id=:did AND is_valid AND version_date<=:as_of" + predicate +
            " ORDER BY version_date DESC,sequence_no DESC LIMIT 1"
        ), params).mappings().first()
        self.stockpile_selection = {"as_of_date": as_of, "stockpile_version_id": None,
                                    "stockpile_version_date": None, "sequence_no": None}
        if version is None:
            if filters.get("stockpile_version_id") is not None:
                raise ReportQueryError("STOCKPILE_VERSION_NOT_AVAILABLE")
            return 0, []
        self.stockpile_selection.update(stockpile_version_id=version["stockpile_version_id"],
                                        stockpile_version_date=version["version_date"], sequence_no=version["sequence_no"])
        historical = filters.get("as_of_date") is not None or filters.get("stockpile_version_id") is not None
        total, rows = self.page(6, dataset, page, page_size, filters | {"_selected_version": version["stockpile_version_id"]},
                                source_override=HISTORICAL_STOCKPILE_SOURCE if historical else None)
        for row in rows:
            params = {"did": dataset.dataset_version_id, "mid": row["material_id"], "vid": row["stockpile_version_id"]}
            dynamic = list(self.executor.execute(text(
                "SELECT forecast_month period,forecast_qty quantity FROM reporting.stockpile_forecast_evidence "
                "WHERE dataset_version_id=:did AND stockpile_version_id=:vid AND material_id=:mid ORDER BY forecast_month"
            ), params).mappings())
            ages = list(self.executor.execute(text(
                "SELECT age_threshold_days threshold_days,age_qty quantity FROM reporting.stockpile_age_evidence "
                "WHERE dataset_version_id=:did AND stockpile_version_id=:vid AND material_id=:mid ORDER BY age_threshold_days"
            ), params).mappings())
            row["future_months"], row["inventory_age_quantities"] = dynamic, ages
        return total, rows
