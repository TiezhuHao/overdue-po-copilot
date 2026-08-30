# System A REST → System B canonical contract

Phase 1A 消费端契约；不替代 `DATA_CONTRACT.md` 的业务基线。来源是实际 `api/reports.py`、`schemas/reports.py`、`services/report_queries.py` 和 `reporting/view_definitions.py`。本阶段不修改 System A。

## Actual REST inventory

统一前缀默认 `/api/v1`；B 的 base URL 包含此前缀，可随 A 部署配置变化。

| GET relative path | A response | B model / method | 已有过滤参数（除分页和 dataset 外） |
|---|---|---|---|
| `datasets` | DatasetListResponse: items, total | DatasetMetadata / list_datasets | 无 |
| `datasets/{dataset_version_id}` | DatasetResponse | DatasetMetadata / get_dataset | 无 |
| `reports/overdue-pos` | Report1Page / Report1Item | PurchaseOrder / purchase_orders | material_code, supplier, buyer, project, po_number |
| `reports/material-supply-demand` | Report2Page / Report2Item | MaterialSupplyDemand / material_supply_demand | material_code, mpm, surplus_sign |
| `reports/forecast-history` | Report3Page / Report3Item | ForecastSnapshot / forecast_history | po_number, material_code, project, forecast_version, window_role |
| `reports/latest-13w-forecast` | Report4Page / Report4Item | WeeklyForecastSnapshot / latest_13w_forecast | material_code |
| `reports/product-configurations` | Report5Page / Report5Item | ProductConfig / product_configurations | project, material_code, business_unit, planning_department, lifecycle |
| `reports/stockpile` | Report6Page / Report6Item | StockpileRecord / stockpile | material_code |

Report envelope 为 `{dataset_version_id, snapshot_date, page, page_size, total, items}`，不是 `{meta, data}`。page 从 1 开始，page_size 1–500，默认 100。404 使用 `{detail: {code: ...}}`，例如 DATASET_NOT_FOUND / NO_READY_DATASET。正常无匹配项为 200、total=0、items=[]。B 拒绝错误页码、跨 dataset、短页/total 矛盾及消费字段类型损坏。

A 允许 UUID 或名称选择 dataset；无选择器时取最新 READY，显式选择时可读取 GENERATING。B 只接受显式 UUID，响应 UUID 必须一致；保留元数据 status，不将 GENERATING 冒充 READY。Dataset 的 generation_signature 与 business_content_hash 是不同字段，不充当 schema version。

## Mapping, types and nullability

以下列出 B 消费的全部业务字段；未列出的宽报表辅助列不透传。`?` 表示字段必须存在但值可为 null；“缺口”字段只在 canonical 中保留为 null，不在 DTO 中假装存在。所有 canonical 行另外注入 envelope 的 UUID `dataset_version_id` 与 date `snapshot_date`。字段缺失不等于明确 null，核心数量不以零补缺。

| A DTO fields | Canonical fields | Type / null / semantics |
|---|---|---|
| DatasetResponse.dataset_version_id, dataset_version_name, snapshot_date, status, generation_signature, business_content_hash | 同名 DatasetMetadata 字段 | UUID, str, date, status enum, str, str?；hash 在开发状态可空 |
| R1.po_number, po_line_number, shipment_number | PurchaseOrder 同名 | str, positive int, positive int；一行一个 shipment，不是整单 |
| R1.material_code, supplier_code, supplier_name, inventory_organization_code, inventory_organization_type | 同名 | str；类型是源组织信息，不是原因标签 |
| R1.reference_project_code/name | 同名 | str?；仅 PO 参考项目，不代表根因项目 |
| R1.order_date, due_date, material_lt_days | 同名 | date, date, nonnegative int（天）；due_date 不作超期阈值 |
| R1.schedule_qty, schedule_received_qty, overdue_open_qty | 同名 | Decimal；发运行数量，不替换为行/订单数量 |
| R1.overdue_days, is_overdue, po_status, close_status, can_close, completion_at | 同名 | int, bool, str, str, bool, timezone-aware datetime?；现有源值直接保留，不重算 |
| R1.snapshot_date | canonical snapshot_date | 必须与 envelope 相同 |
| R2.material_code, inventory_organization_code, material_lt_days | MaterialSupplyDemand 同名 | str, str, int |
| R2.all_supply_qty, actual_demand_total_qty, supply_demand_surplus_qty | 同名 | Decimal；盈余为供应减需求，允许负值，不重算、不反转为 gap |
| R2.good_non_vmi_inventory_qty, defective_inventory_qty, non_mrp_inventory_qty | 同名 | Decimal?；分别 available、quality_hold、blocked，不混成总库存 |
| R2.non_vmi_in_transit_order_qty, non_vmi_in_transit_delivery_qty, open_po_qty, purchase_requisition_qty | 同名 | Decimal?；第一项为 OPEN_PO 组件、第二项为 IN_TRANSIT；open_po_qty 已含二者，禁止重复求和；IN_TRANSIT 不是 ASN |
| R2.organization_active_projects, enterprise_active_projects, top_project | 同名 | tuple[str, ...]?、tuple[str, ...]?、str?；展示名称，禁止当稳定 Join 键 |
| R2.mpm_code, mpm_name, mpm_department_name | mpm.employee_code, employee_name, department_name | MaterialMpmContact；str；仅挂在物料对象，不挂项目 |
| R3.po_line_schedule_id, material_code, project_name | ForecastSnapshot 同名 | UUID, str, str；schedule 是唯一额外公开的事实 ID |
| R3.forecast_version_name/date, window_role | 同名 | str, date, BASELINE/POST；预选窗口元数据不是分析结论 |
| R3.forecast_month, forecast_qty, forecast_total_qty, cumulative_shipped_qty | 同名 | date（自然月首日）, Decimal ×3；total 和累计发货在月行重复，不得跨月份求和 |
| R4.material_code, organization_code, snapshot_date | WeeklyForecastSnapshot 同名 | str, str, date；snapshot 与 envelope 一致 |
| R4.week_01_forecast_qty … week_13_forecast_qty | weeks[].week_index, forecast_qty | 13 个 WeekForecast；索引 1–13、Decimal，按索引顺序解宽，不在 Adapter 聚合 |
| R4.thirteen_week_demand_qty, weekly_average_demand_qty | 同名 | Decimal；零需求保持 0，不计算 consumption |
| R4.open_po_qty, advance_shipping_notice_qty, open_purchase_requisition_qty, good_subinventory_qty, defective_subinventory_qty | 同名 | Decimal?；未实现 ASN/PR 保持 null，不能替换为 IN_TRANSIT |
| R4.top_project | 同名 | str?；仅 top 1 展示名称，无项目贡献量 |
| R5.material_code, project_name, product_config_type/name/version/status, business_unit_name, planning_department_name, lifecycle_stage | ProductConfig 同名 | str；lifecycle enum NPI/MASS_PRODUCTION/EOL；一行 Config × Material，不能按项目去重 |
| R5.customer_code, customer_project_name, modified_at | 同名 | str?, str?, timezone-aware datetime? |
| R6.material_code, stockpile_version_name/date | StockpileRecord 同名 | str, str, date；当前 snapshot 时有效的 stockpile version，不等于 dataset version |
| R6.stockpile_nature | stockpile_tag | str；直接保留公开标签，不推断业务原因 |
| R6.planned_stockpile_qty | target_stockpile_qty | Decimal |
| R6.inventory_qty, seven_day_demand_qty, stockpile_qty_gap, stockpile_completion_ratio | 同名 | Decimal, Decimal, Decimal, Decimal?；target 为 0 时 ratio=null，不重算；ratio 是倍数，1 表示 100%，不强制上限 1 |
| R6.agreement_unit_price | agreement_unit_price | Decimal?；不是 PO 单价，币种未公开，不用于 PO 金额 |
| R6.future_months[].period/quantity | future_months[].period/quantity | date / Decimal；版本月之后六个自然月，保留上游日期 |
| R6.inventory_age_quantities[].threshold_days/quantity | inventory_age_quantities[].threshold_days/quantity | int / Decimal；累计超过阈值，不是互斥桶 |

数量使用 Decimal，日期使用 ISO date，时间戳要求时区；数字 JSON 字符串与 JSON number 都接受，JSON number 用 Decimal 解码避免先转 float 损失。拒绝 bool 作为数量/整数、非有限值与错误日期，不擅自 round 或量化。源数量按 A 的 numeric(20,4) 口径，物料 UOM 未公开；不能跨物料盲目相加。未消费的金额“万元”列不进入 B，避免币种/单位不明时混算。

消费端 DTO 与 canonical 独立定义，不继承 A 的动态 schema；canonical 禁止额外字段。未知上游字段被忽略，不随响应传播，新增消费字段必须更新本表与测试。所有 null 值保持 null，不把空字符串转 null 或把 null 转零。

## Forecast and identity semantics

R3 是 schedule × material × project × version × month 的长表，每个版本展示 M0…M+6 共 **7 个月**，不是机械假定六个月。A 已按日取最大有效 sequence，严格 Anchor 前 baseline 与后 3 版；B 不重选窗口或标注需求变化。一个 Forecast 可能为多个 PO schedule 重复出现，不得无键去重或全局累加。

R4 是 Material 总量及 13 周槽位，不能冒充 project-level Forecast。与 R3 分开模型，避免把汇总量用于项目 Top 3；`WeekForecast.week_start_date` 留 null，因为公开 API 未包含 weekly snapshot ID/原始日期。周历仍遵循已固化 Monday-start，但 B 不以 envelope 的 dataset 日期猜测源 weekly snapshot 日期。

缺口预留字段：所有物料行的 material_id；PO 的 po_line_schedule_id / po_line_id / po_reference_project_id / supplier_id / organization_id / unit_price / currency；R2 的 organization_id、MPM employee_id；R3 的 project_id / forecast_version_id；R4 的 organization_id / weekly_forecast_snapshot_id；R5 的 project_id / product_config_id；R6 的 stockpile_version_id / stockpile_record_id / actual_stockpile_qty / currency。这些均为 null，明确表示未通过 API 暴露；不生成替代 UUID、不由名称匹配、不由库存或 GAP 反推缺失实际量。

## Contract gaps and follow-up gates

| ID | Evidence / impact | Required future action |
|---|---|---|
| B-G01 | `_public_row` 丢弃内部关联 ID，R1 甚至没有 R3 使用的 schedule ID；R3/R5 只有项目名称 | 增补中性稳定 ID 的 REST 契约后才能做可靠跨表 Join；B 不直接读 View/DB 绕过边界 |
| B-G02 | R1 没有 PO unit_price/currency，PoLine 也未建订单价格字段 | 后续明确采购价格来源与货币契约；超期金额目前不可算；不能借用 R6 agreement price |
| B-G03 | R6 route 无 as_of_date 或 PO ID；公共接口只返回当前版本，也无 matched_version/record_found 包装 | 历史囤料按 order_date 查询的 API 尚缺；空列表不能区分无版本和无记录；禁止将当前囤料用于历史判断 |
| B-G04 | R6 未公开 actual_stockpile_qty、record/version ID、currency | 后续补中性字段；库存不等于正式 actual contract，B 不反推；无 project 是当前 Material 粒度本身，不强加项目 |
| B-G05 | R3 只有默认 baseline+3、7个月投影，无任意 Anchor、版本 ID/sequence/valid、长 horizon 或选择2–5版的 REST 参数 | 默认展示数据可用；完整、可审计的版本比较/延后识别仍受限，后续补 API 后再做完整 Analytics |
| B-G06 | R4 未公开 weekly snapshot ID、week dates 与 project weekly facts；snapshot 字段来自 dataset | 需要中性周长表和项目贡献 API 才能可靠填日期与计算项目 exposure Top 3 |
| B-G07 | R2/4 的 ASN、PR 与多个辅助字段可空，UOM/货币及 Dataset schema/generator version 不完整 | 保留 null 与来源名，不把 IN_TRANSIT 伪装 ASN，不假设金额单位；由后续契约确定 |
| B-G08 | A schema 多数为 Any 且默认 null；响应/OpenAPI 不保证数字类型，B 必须独立校验消费字段 | 本次消费端 validation 已落实；A 强类型化为后续独立改进，不扩大本次 scope |

这是已实现 API 与设计覆盖度的工程缺口，不是授权更改业务公式。涉及正式业务含义的既有 KD 释义、售后对策等继续 `NEEDS_BUSINESS_CONFIRMATION`；不阻塞本阶段 Adapter，但不能宣称后续全部 Analytics 已具备数据。
