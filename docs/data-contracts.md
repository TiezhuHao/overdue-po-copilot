# System A REST → System B canonical contract

Phase 1A–1C 消费端契约；不替代 `DATA_CONTRACT.md` 的业务基线。来源是实际 route/schema、report queries 及 reporting views。Phase 1C 增加中性身份/时间证据，部署需要新增 migration `012_evidence_contract`；001–011、Generator、业务事实及 Excel manifest 不变。

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
| R3.po_line_schedule_id, material_code, project_name | ForecastSnapshot 同名 | UUID, str, str；schedule 关联 R1，稳定物料/项目 ID 见增量表 |
| R3.forecast_version_name/date, window_role | 同名 | str, date, BASELINE/POST；预选窗口元数据不是分析结论 |
| R3.forecast_month, forecast_qty, forecast_total_qty, cumulative_shipped_qty | 同名 | date（自然月首日）, Decimal ×3；total 和累计发货在月行重复，不得跨月份求和 |
| R4.material_code, organization_code, snapshot_date | WeeklyForecastSnapshot 同名 | str, str, date；snapshot 与 envelope 一致 |
| R4.week_01_forecast_qty … week_13_forecast_qty | weeks[].week_index, forecast_qty | 13 个 WeekForecast；索引 1–13、Decimal，按索引顺序解宽，不在 Adapter 聚合 |
| R4.thirteen_week_demand_qty, weekly_average_demand_qty | 同名 | Decimal；零需求保持 0，不计算 consumption |
| R4.open_po_qty, advance_shipping_notice_qty, open_purchase_requisition_qty, good_subinventory_qty, defective_subinventory_qty | 同名 | Decimal?；未实现 ASN/PR 保持 null，不能替换为 IN_TRANSIT |
| R4.top_project | 同名 | str?；仅 top 1 展示名称，无项目贡献量 |
| R5.material_code, project_name, product_config_type/name/version/status, business_unit_name, planning_department_name, lifecycle_stage | ProductConfig 同名 | str；lifecycle enum NPI/MASS_PRODUCTION/EOL；一行 Config × Material，不能按项目去重 |
| R5.customer_code, customer_project_name, modified_at | 同名 | str?, str?, timezone-aware datetime? |
| R6.material_code, stockpile_version_name/date | StockpileRecord 同名 | str, str, date；默认当前有效版本，也可显式历史 as-of/version，不等于 dataset version |
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

R4 保留 Material 总量及13周宽槽位，新增 `weeks` 日期长数组及 `project_contributions` 项目周事实数组。项目事实不排名、不输出责任，不把 Top 1 名称当稳定键。Adapter 解包源日期，不按 envelope 日期猜测周历。旧 REST 无新增字段时仍兼容，日期/身份保留 null。

### Phase 1C additive identity / time mapping

所有稳定键以 `dataset_version_id` 为作用域；不能跨 dataset 仅按实体 UUID 关联。编码和名称是 display/business key，不能替代稳定 ID。API 新字段独立于 Excel manifest，旧列不删除/重命名。新增字段在 Schema/DTO 中 nullable 以兼容旧响应；真实012投影的必需身份由集成测试核验非空。源明确可空的 PO reference project 不补造。

| REST additions | Canonical / join meaning |
|---|---|
| 六报表 material_id | 原 Material master UUID，同 dataset 复用；不为报表单独造 ID |
| R1 po_header_id, po_line_id, po_line_schedule_id, po_reference_project_id, supplier_id, organization_id | 同名；Header→Line→Schedule。material/reference project 属于 Line，供应商属于 Header；project 仅参考项目 |
| R2 organization_id, supply_demand_snapshot_id, inventory_snapshot_id, supply_snapshot_date, inventory_snapshot_date | 同名；明确来源快照，不能将 dataset 日期无条件当事实快照日期 |
| R2 mpm_employee_id | mpm.employee_id；通过 Inventory 引用的 Material MPM assignment，仍是物料关系 |
| R3 material_id, project_id, forecast_version_id, forecast_version_sequence | 同名；版本顺序为日期 + 同日 sequence；投影只包含有效最终版本 |
| R3 forecast_anchor_date, window_position, horizon_start_month, horizon_end_month_exclusive | 同名；窗口位置0是 baseline，1–3是 post；horizon 为版本月起7个月的半开区间，不是全部存储月事实 |
| R4 organization_id, weekly_forecast_snapshot_id, forecast_snapshot_date, source_forecast_version_id | 同名；weekly snapshot 与 forecast version、dataset 是三种不同身份 |
| R4 weeks[].week_index/week_start_date/forecast_qty | Canonical weeks；13个唯一连续 Monday-start 槽位，与旧宽槽数量逐项一致，否则 Adapter 拒绝 |
| R4 project_contributions[].project_id/week_index/week_start_date/forecast_qty | 同名；上层 material/organization/weekly snapshot 提供共同作用域；复合键为 scope + project + week；空数组与 null 不同 |
| R5 project_id, product_config_id | 同名；Config×Material 粒度不变，lifecycle_stage 为 dataset snapshot 时项目生命周期，不是历史全轨迹 |
| R6 organization_id, stockpile_version_id, stockpile_record_id, stockpile_version_sequence, actual_stockpile_qty | 同名；直接公开原始实际数量，绝不从 inventory/gap 推算；R6 没有真实 project FK，不增加 project_id |
| R6 envelope.stockpile_selection | CanonicalPage.stockpile_selection：as_of_date、选中 version ID/date/sequence；默认无此元数据的旧响应只支持当前查询 |

新筛选均为精确匹配 UUID，与旧筛选 AND 组合：R1 material_id/po_header_id/po_line_id/po_line_schedule_id/po_reference_project_id；R2 material_id；R3 material_id/project_id/po_line_schedule_id/forecast_version_id；R4 material_id；R5 material_id/project_id；R6 material_id/stockpile_version_id，另加 ISO date `as_of_date`。其余旧参数保持。不存在对应事实则为空页，不回退名称。

### Version and temporal semantics

- Dataset version 是固定合成世界的身份；envelope snapshot_date 是业务截止日，不是 Forecast revision。既有 dataset provenance 不因仅增加 view 的迁移而改写。
- Forecast version 的 `forecast_version_date` 与 `forecast_version_sequence` 明确时间。R3 沿用 daily-final-valid：同日选最大有效 sequence，无效版本跳过；不以数组顺序、UUID 或 created_at 排序。默认仍为严格 Anchor 前 baseline + 后3版、每版7个月；不宣称覆盖全版本目录或任意 horizon。
- R4 的 forecast_snapshot_date 来自 Weekly Snapshot，周日期来自对应公开长表；source_forecast_version_id 是其实际来源 FK。项目周事实以同一 weekly snapshot、物料、主组织为 scope，不把 dataset 当预测版本。
- R6 默认 as_of=dataset.snapshot_date；指定 as_of 时只选 version_date<=as_of 的有效最大日期/sequence。显式 version ID 可查看某个有效历史修订，不自动升级为同日最终版，仍必须 <=as_of<=dataset.snapshot_date；跨 dataset、无效/未来/不存在的显式版本返回422。as_of 晚于 dataset snapshot 同样422，不自动截断。
- 选中版本的 ID/date/sequence 即使无匹配物料也保留；没有有效版本则三者均 null。空页必须结合 selection 和 total 解读，不能把分页越界当成无记录。Adapter 校验请求/页/行版本一致性；历史请求遇到旧响应缺 selection 明确失败。
- 历史 R6 的数量、未来六个月和累计库龄均绑定选中 version + material，不混入当前版本。历史模式不附当前协议价或无历史证明的辅助展示值，保留 null；material_code 仅使用稳定主数据展示。默认当前模式旧展示值不变。stockpile version_date 表示证据版本生效日，不等于 Forecast 月份或 PO 下单日。

## Contract gaps and follow-up gates

| ID | Evidence / impact | Required future action |
|---|---|---|
| B-G01 | 已解决核心六表身份与 R1/R4 Join；所有关联限定同dataset | 实际REST→Adapter跨报表验证；B仍不读DB |
| B-G02 | R1 没有 PO unit_price/currency，PoLine 也未建订单价格字段 | 后续明确采购价格来源与货币契约；超期金额目前不可算；不能借用 R6 agreement price |
| B-G03 | 已解决 R6 as_of/version 与选中版本元数据 | 按 PO.order_date 显式调用；本轮不生成囤料诊断 |
| B-G04 | actual quantity、record/version ID 已解决；currency仍缺 | 不借协议价计算PO金额；R6是Material粒度，不强加project |
| B-G05 | 版本ID/sequence/horizon/物料项目ID已解决；仍只有默认baseline+3的7月投影 | 全版本目录、任意Anchor/2–5 post/额外重叠月份及历史lifecycle查询仍为候选；当前范围可显式比较同月，不实现自动选择算法 |
| B-G06 | 已解决 weekly snapshot ID/date、周历、项目周贡献 | Top 3计算本轮未实现；新增事实不等于已做排名或归因 |
| B-G07 | R2/4 的 ASN、PR 与多个辅助字段可空，UOM/货币及 Dataset schema/generator version 不完整 | 保留 null 与来源名，不把 IN_TRANSIT 伪装 ASN，不假设金额单位；由后续契约确定 |
| B-G08 | 旧展示字段多数为 Any；新增UUID/date/周Decimal为显式类型 | 旧展示字段全面强类型化仍候选，B继续独立校验 |

这是已实现 API 与设计覆盖度的工程缺口，不是授权更改业务公式。涉及正式业务含义的既有 KD 释义、售后对策等继续 `NEEDS_BUSINESS_CONFIRMATION`；不阻塞本阶段 Adapter，但不能宣称后续全部 Analytics 已具备数据。

## Phase 1B consumption note

Phase 1C 不增加 Analytics 算法；已有算法通过增强 Canonical 输入解除部分身份/周日期阻塞，见 [analytics-metrics.md](analytics-metrics.md)。
R4 同行 open PO/available inventory 与13周桶可用于物料级消耗/覆盖；跨 PO/R4 不用名称或编码替代稳定 ID。
现有 all_supply 是 System A 源供需总量，不能自行更名为 confirmed supply；PR 不自动加入 confirmed/planned 汇总。
confirmed/planned 的供应承诺、排重及组成定义列为 B-G07 的 System A Contract Enrichment candidate。
显式同月 Forecast 比较纯函数的存在不表示当前 REST 已具备自动版本比较能力。
