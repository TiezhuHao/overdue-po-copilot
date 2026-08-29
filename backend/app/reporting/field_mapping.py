"""Human-readable field lineage generated from the ordered header contract."""
from app.reporting.report_header_manifest import get_report_manifest, manifest_content_hash


REPORT_SOURCES = {
    1: "reporting.report1_overdue_po_detail ← dataset_versions, PO Header/Line/Schedule, Material, Supplier, Project, responsibility assignments",
    2: "reporting.report2_material_supply_demand ← supply_demand_snapshots/components, inventory, Material, MPM/responsibility assignments, Forecast",
    3: "reporting.report3_forecast_history_long ← Report 1 anchor, daily-final-valid forecast_versions, monthly_forecasts, material_project_shipments",
    4: "reporting.report4_latest_13w_forecast / report4_weekly_forecast_long ← latest weekly snapshot, project weekly facts aggregated to Material",
    5: "reporting.report5_product_configuration ← Project, Product Config/Material bridge, lifecycle history, Organization, Customer, Employee",
    6: "reporting.report6_stockpile_detail + normalized long views ← latest final valid Stockpile Version <= dataset snapshot and operational facts",
}

FORMULAS = {
    "overdue_days": "snapshot_date - order_date - material_lt_days - 240; row included only when > 0",
    "is_overdue": "overdue_days > 0",
    "overdue_open_qty": "greatest(schedule_qty - schedule_received_qty, 0)",
    "all_supply_qty": "sum SUPPLY components; reconciled to snapshot total",
    "actual_demand_total_qty": "sum DEMAND components; reconciled to snapshot total",
    "supply_demand_surplus_qty": "all_supply_qty - actual_demand_total_qty",
    "trial_all_supply_qty": "SUPPLY components whose organization_type_scope = TRIAL",
    "trial_actual_demand_total_qty": "DEMAND components whose organization_type_scope = TRIAL",
    "trial_supply_demand_surplus_qty": "trial_all_supply_qty - trial_actual_demand_total_qty",
    "forecast_version_date": "daily-final-valid version: maximum valid sequence per date; baseline < anchor, post > anchor",
    "forecast_total_qty": "sum of seven normalized forecast-month quantities for Material × Project × Version",
    "cumulative_shipped_qty": "Material × Project shipments from dataset history start through version_date inclusive",
    "thirteen_week_demand_qty": "sum week_01 through week_13",
    "weekly_average_demand_qty": "thirteen_week_demand_qty / 13",
    "lifecycle_stage": "effective Project lifecycle at dataset snapshot; NPI/MASS_PRODUCTION/EOL only",
    "stockpile_version_date": "latest final valid version_date <= dataset snapshot_date",
    "stockpile_qty_gap": "planned_stockpile_qty - actual_stockpile_qty",
    "stockpile_completion_ratio": "actual_stockpile_qty / target_stockpile_qty; NULL when target is zero",
    "kit_minimum_pack_demand_qty": "NULL; template auxiliary label only; full business meaning remains NEEDS_BUSINESS_CONFIRMATION",
}


def _rule(report_id, column):
    field = column["canonical_field"]
    if column["business_status"] == "DEFERRED_BUSINESS_FORMULA":
        return "NULL; auxiliary formula intentionally deferred—no synthetic business rule invented"
    if column["slot"]:
        slot = column["slot"]
        return f"dynamic {slot['kind']} slot {slot['slot_index']} from normalized long view; Phase 6B supplies the dated display header"
    return FORMULAS.get(field, "direct or deterministic projection from the listed normalized facts; NULL only when the source fact is legitimately absent")


def render_markdown():
    lines = [
        "# 六报表字段映射", "",
        "本文件是机器可读表头清单的逐字段 lineage 投影。列序唯一来源为 `backend/app/reporting/report_header_manifest.json`；Semantic View、后续 API 与 Excel exporter 不得另建列序。", "",
        f"Header manifest hash：`{manifest_content_hash()}`。技术 lineage 键只存在于内部 View 尾部，不属于 Excel 展示列。", "",
        "可空性：`N` 表示核心/固定语义必须有值；`Y` 表示该字段被明确延后并在本阶段返回 NULL；`C` 表示允许源事实合法缺失。", "",
    ]
    for report_id in range(1, 7):
        report = get_report_manifest(report_id)
        lines += [f"## Report {report_id} — {report['sheet_name']}", "", f"来源链：{REPORT_SOURCES[report_id]}。", "",
                  "| # | display column | canonical field | source relation | formula / selection rule | nullable | core/auxiliary | business status |",
                  "|---:|---|---|---|---|:---:|---|---|"]
        for column in report["columns"]:
            status = column["business_status"]
            nullable = "Y" if status == "DEFERRED_BUSINESS_FORMULA" else ("N" if column["classification"] == "core" else "C")
            source = REPORT_SOURCES[report_id].split(" ← ", 1)[0]
            display = " → ".join(column["header_path"]).replace("|", "\\|")
            rule = _rule(report_id, column).replace("|", "\\|")
            lines.append(f"| {column['column_index']} | {display} | `{column['canonical_field']}` | `{source}` | {rule} | {nullable} | {column['classification']} | {status} |")
        lines.append("")
    lines += [
        "## 未决边界", "",
        "- DC-03 与 DC-12 中缺正式公式的辅助字段保持 `DEFERRED_BUSINESS_FORMULA` / NULL，不阻塞核心报表语义。",
        "- 模板中的该辅助术语仅为 `AUXILIARY_ONLY`；完整释义继续 `NEEDS_BUSINESS_CONFIRMATION`，不参与任何判断。",
        "- DC-16 售后正式处置继续 `NEEDS_BUSINESS_CONFIRMATION`；六张源报表不输出 expected_action。", "",
    ]
    return "\n".join(lines)
