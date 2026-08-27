# System A PostgreSQL Schema 设计

## 1. 状态与设计目标

本文件只定义建议的规范化 PostgreSQL Schema，不包含迁移或业务实现。目标是：

- 一个 Synthetic Enterprise World 派生六张 Report；
- 所有业务事实按 `dataset_version` 隔离；
- 动态月份、周次、版本和库龄使用长表；
- 内部 ID 稳定，名称只用于展示；
- Ground Truth 在数据库权限和应用模块两层隔离；
- 相同确定性输入得到相同业务内容和稳定 ID。

## 2. Schema 与角色边界

建议使用以下 PostgreSQL namespaces：

| Schema | 内容 | 普通 API 角色 |
|---|---|:---:|
| `platform` | dataset、主数据、业务事实、版本、Report Views | 只读 View/受控函数 |
| `evaluation` | `scenario_truth` 与评测辅助对象 | 无权限 |
| `alembic` | 迁移版本（可沿用默认） | 无权限 |

建议角色：

- `system_a_owner`：DDL/迁移所有者，不用于运行 API。
- `system_a_generator`：写 `platform`，写 `evaluation.scenario_truth`。
- `system_a_api`：仅 `SELECT` 六个公开 View 和 dataset 元数据白名单。
- `system_a_evaluator`：只读公开 View 与 `evaluation`，用于自动评测。

禁止向 `PUBLIC` 授予 `evaluation` 的 USAGE/SELECT。普通 API 连接字符串不得使用 owner/generator/evaluator 角色。

## 3. 通用列与隔离模式

除版本头等特殊表外，每个 dataset-scoped 表至少包含：

```text
dataset_version_id uuid not null
<entity_id> uuid not null
created_at timestamptz not null
```

推荐主键为 `(dataset_version_id, <entity_id>)`，所有外键同时携带 `dataset_version_id`，从数据库层阻止跨数据集误连。例如：

```text
(dataset_version_id, material_id)
  → materials(dataset_version_id, material_id)
```

生成器对业务实体 ID 使用确定性命名空间 UUID（例如 dataset signature + entity type + stable ordinal/business code），不能使用每次运行随机 UUID。`generated_at` 等运行元数据不参与业务内容哈希。

数量统一 `numeric(20,4)`；金额统一 `numeric(20,4)` 并带 `currency_code char(3)`；日期用 `date`；审计时间用 `timestamptz`；自然月存月首日并加 `CHECK (forecast_month = date_trunc('month', forecast_month)::date)`。

---

## 4. 版本与生成元数据

### 4.1 `platform.dataset_versions`

| 列 | 类型 | Null | 约束/用途 |
|---|---|:---:|---|
| `dataset_version_id` | uuid | N | PK；由确定性签名生成 |
| `version_name` | text | N | 业务名称，唯一 |
| `random_seed` | bigint | N | Generator seed |
| `snapshot_date` | date | N | 企业世界“当前日期” |
| `generator_version` | text | N | Generator 语义版本 |
| `schema_version` | text | N | 数据契约/Schema 版本 |
| `generation_config` | jsonb | N | 规模、场景占比、阈值配置等；键顺序标准化后参与签名 |
| `generation_signature` | text | N | seed + snapshot + versions + canonical config 的哈希；UNIQUE |
| `business_content_hash` | text | Y | 生成完成后写入的规范化业务内容哈希 |
| `status` | text | N | `GENERATING/READY/FAILED/RETIRED` |
| `generated_at` | timestamptz | N | 运行审计；不参与业务哈希 |

`dataset_version` 与 `forecast_version`、`stockpile_version` 不得共用 ID 或含义。

### 4.2 可选 `platform.generation_runs`

若需要保存同一签名的多次执行日志，新增 run 表而不是复制业务数据集：`generation_run_id`、`dataset_version_id`、started/finished、status、error、runtime_hash。该表不属于六张 Report。

---

## 5. 组织、人员与主数据

### 5.1 `platform.organizations`

```text
PK  (dataset_version_id, organization_id)
UQ  (dataset_version_id, organization_code)
FK  parent_organization_id → organizations
```

核心列：`organization_code`、`organization_name`、`organization_type`（INVENTORY_ORG/BUSINESS_ENTITY/BUSINESS_UNIT/PLANNING_DEPARTMENT/DEPARTMENT 等）、`inventory_organization_type`（TRIAL/MASS_PRODUCTION，仅适用库存组织）、`parent_organization_id`、`effective_from/to`。

### 5.2 `platform.employees`

核心列：`employee_id`、`employee_code`、`account_name`、`employee_name`、`organization_id`、`manager_employee_id`、`director_employee_id`、`is_active`。业务码在 dataset 内唯一。

### 5.3 `platform.employee_role_assignments`（新增）

用于买手、物控、研发代表等随时间变化的角色，不把角色硬编码进 employee 表。

```text
PK (dataset_version_id, employee_role_assignment_id)
FK employee_id → employees
FK organization_id → organizations nullable
role_type text not null
effective_from date not null
effective_to date null
```

### 5.4 `platform.materials`

核心列：

- `material_id`、`material_code`（dataset 内唯一）；
- `material_description`、`specification_model`、`model`；
- 分类、采购类别、替代组、品牌；
- `material_lt_days`（主用 LT，`>=0`）；
- `manufacturer_lt_days`；
- `minimum_pack_qty`、`minimum_order_qty`；
- `non_cancelable_non_returnable_flag`。
- `primary_inventory_organization_id`，FK → `organizations`；V1 每个 Material 必须且只能绑定一个 Primary Inventory Organization。

### 5.5 `platform.projects`

核心列：`project_id`、`project_code`、`project_name`、`customer_project_name`、`brand_name`、`product_type`、`shipment_type`、`business_mode`。`project_code` dataset 内唯一，名称不要求唯一。

### 5.6 `platform.customers`

核心列：`customer_id`、`customer_code`、`customer_short_code`、`customer_name`。业务码 dataset 内唯一。

### 5.7 `platform.suppliers`

核心列：`supplier_id`、`supplier_code`、`supplier_name`、`supplier_name_en`、`currency_code`、`is_active`。业务码 dataset 内唯一。

---

## 6. 主数据关系

### 6.1 `platform.material_projects`

Material ↔ Project 多对多关系：

```text
PK  (dataset_version_id, material_project_id)
FK  material_id → materials
FK  project_id → projects
FK  organization_id → organizations nullable
effective_from date
effective_to date nullable
relationship_type text
```

同一 Material/Project/Organization 的有效区间不得重叠。Report 2/4 的项目集合从此表按 snapshot 聚合。

### 6.2 `platform.material_mpm_assignments`

```text
PK  (dataset_version_id, material_mpm_assignment_id)
FK  material_id → materials
FK  employee_id → employees
effective_from date not null
effective_to date null
UQ/EXCLUDE 同一 material 的有效区间不得有两个主 MPM
```

这是唯一正式 Material → MPM 来源。不得创建 Project → MPM 替代关系。

### 6.3 `platform.material_supplier_assignments`（新增）

保存主/候选供应商、协议价、有效期：`material_id`、`supplier_id`、`organization_id`、`assignment_type`、`agreement_unit_price`、`currency_code`、`effective_from/to`。

### 6.4 `platform.project_customers`（新增）

保存 Project ↔ Customer 关系，支持主客户和历史有效区间。

### 6.5 `platform.material_responsibility_assignments`（新增）

保存物料-组织下的 BUYER、MATERIAL_CONTROLLER、PRIMARY_MATERIAL_CONTROLLER 等责任关系。MPM 仍使用专表以强化唯一性规则。

---

## 7. PO 事实

### 7.1 `platform.po_headers`（新增）

核心列：`po_header_id`、`po_number`、`business_entity_id`、`inventory_organization_id`、`supplier_id`、`order_buyer_employee_id`、`po_status`、`close_status`。`(dataset_version_id, po_number)` 唯一。

### 7.2 `platform.po_lines`

核心列：

| 列 | 用途 |
|---|---|
| `po_line_id` | 稳定事实 ID |
| `po_header_id` | PO 头 FK |
| `po_line_number` | 同 PO 内唯一 |
| `material_id` | Material FK |
| `po_reference_project_id` | 参考项目 FK，可空；绝不是 Ground Truth |
| `ordered_qty` | `>=0` |
| `received_qty` | `0 <= received_qty <= ordered_qty`（若接收在 schedule 级则行级为汇总） |
| `order_date` | 超期、Anchor、Stockpile as-of 基准 |
| `due_date` | Mock V1 为 order_date + LT；不用于超期定义 |
| `material_lt_days_at_order` | 下单时冻结 LT；与主数据一致性策略见说明 |
| `can_close`、`completion_at`、`line_status` | 执行状态 |

唯一约束 `(dataset_version_id, po_header_id, po_line_number)`。

### 7.3 `platform.po_line_schedules`

正式关系为 PO Header → PO Line → PO Line Schedule / Shipment。核心列：`po_line_schedule_id`、`po_line_id`、`shipment_number`、`schedule_qty`、`schedule_received_qty`、`due_date`、`close_status`。唯一 `(dataset_version_id, po_line_id, shipment_number)`。

Report 1 的事实主键固定为 `po_line_schedule_id`，展示粒度为 `PO号 + PO行 + 发运号`。Generator V1 默认每个 PO Line 生成 1 个 Shipment，但 Schema 不得施加“一行只能一个 Shipment”的约束。

### 7.4 Report 1 派生

```text
snapshot_date = dataset_versions.snapshot_date
material_lt_days = materials.material_lt_days
overdue_days = snapshot_date - order_date - material_lt_days - 240
overdue_open_qty = greatest(schedule_qty - schedule_received_qty, 0)
filter overdue_days > 0
```

PO 表不得包含 `true_cause`、`causal_project_id`、EOL 真值或期望对策。

---

## 8. 当前供需

### 8.1 `platform.supply_demand_snapshots`

每个 dataset 当前快照的物料头：

```text
PK  (dataset_version_id, supply_demand_snapshot_id)
FK  material_id → materials
FK  organization_id → organizations
UQ  (dataset_version_id, material_id)
snapshot_date date = dataset_versions.snapshot_date
```

`organization_id` 必须等于该 Material 的 `primary_inventory_organization_id`。V1 Report 2/4 均保持 `1 Material = 1 Row`；保留 organization FK 只为未来 Material × Organization 扩展。

### 8.2 `platform.supply_demand_components`（新增）

将 Report 2 大量供应/需求/试产组件规范化：

| 列 | 说明 |
|---|---|
| `supply_demand_component_id` | PK |
| `supply_demand_snapshot_id` | FK |
| `organization_type_scope` | MASS_PRODUCTION/TRIAL/ALL |
| `component_side` | SUPPLY/DEMAND/PLAN/EXCESS/RESULT |
| `component_type` | 例如 GOOD_VMI_INVENTORY、OPEN_PO、STANDARD_WORK_ORDER_DEMAND |
| `quantity` | 数量 |
| `source_domain` | 模拟源系统域 |

唯一 `(snapshot, scope, component_type)`。Report 2 通过条件聚合展开。根因分析只依赖 `all_supply_qty`、`actual_demand_total_qty` 和 `supply_demand_surplus_qty = all_supply_qty - actual_demand_total_qty`；其他供需汇总和“多余”字段为辅助展示，其 Mock 公式延后到 Generator 阶段固定，不阻塞 Phase 1。

### 8.3 `platform.inventory_age_buckets`（新增）

保存 Report 2 库龄数量与抵扣后剩余：`snapshot_id`、`bucket_start_days`、`bucket_end_days`、`inventory_qty`、`remaining_inventory_qty`。唯一 `(snapshot,bucket_start,bucket_end)`。

---

## 9. Underlying Demand Signal 与 Forecast

### 9.1 `platform.demand_signals`（新增且必要）

Demand World 头：`demand_signal_id`、`material_id`、`project_id`、可选 `organization_id`、`signal_kind`、`scenario_generation_key`。不得存最终 cause。

### 9.2 `platform.demand_signal_points`（新增且必要）

建议以日或周的可聚合粒度保存底层需求：

```text
PK (dataset_version_id, demand_signal_point_id)
FK demand_signal_id → demand_signals
demand_date date not null
demand_qty numeric >= 0
UQ (demand_signal_id, demand_date)
```

Report 3/4/6 均必须保存到 `demand_signal_id` 或可验证 lineage 的引用。

### 9.3 `platform.forecast_versions`

| 列 | 说明 |
|---|---|
| `forecast_version_id` | PK |
| `version_name` | dataset 内唯一 |
| `version_date` | Anchor 比较日期 |
| `is_valid` | 选择版本时过滤 |
| `sequence_no` | 同日补发/修订稳定顺序；同日最大有效值为最终版本 |
| `description` | 可空 |

所有 PO 共享这张版本日历，PO 表不得有专属 Forecast Version。V1 默认每周生成一版；同日最终版本选择为 `is_valid=true` 中最大 `sequence_no`，无效版本永远跳过。Anchor 窗口在每日最终版本集合上取 Anchor 前最近 Baseline，再取 Anchor 后 2～5 版。

### 9.4 `platform.monthly_forecasts`

```text
PK/UQ (dataset_version_id, forecast_version_id, material_id, project_id, forecast_month)
FK forecast_version_id → forecast_versions
FK material_id → materials
FK project_id → projects
FK demand_signal_id → demand_signals
forecast_qty numeric(20,4) not null check >= 0
forecast_source text not null
```

不得存 `demand_change_type`；该类型属于 Analytics/Truth，而不是源 Forecast。

### 9.5 `platform.material_project_shipments`

保存当前 dataset 历史窗口内 Material × Project 的实际发货事实：`material_project_shipment_id`、`material_id`、`project_id`、`shipment_date`、`shipped_qty`。Report 3 的 `cumulative_shipped_qty` 固定为从该 dataset 历史起点至 `forecast_version_date`（含）按 Material × Project 累计。

### 9.6 `platform.weekly_forecast_snapshots`

核心列：`weekly_forecast_snapshot_id`、`snapshot_date`、`source_forecast_version_id`、`is_latest`。一个 dataset 只能有一个 `is_latest=true`。

### 9.7 `platform.weekly_project_forecasts`

保存 `weekly_forecast_snapshot_id × material_id × project_id × week_start_date` 的项目级 13 周贡献，关联 `demand_signal_id`。它是计算“最多项目”的 V1 必要事实：对最新 13 周按 Project 求和，取贡献最大者；并列按稳定 `project_id` 排序。

### 9.8 `platform.weekly_forecasts`

```text
PK/UQ (weekly_forecast_snapshot_id, material_id, week_start_date)
FK material_id → materials
FK demand_signal_id → demand_signals nullable only if lineage bridge exists
forecast_qty numeric >= 0
week_index smallint check 1..13 for report snapshot
```

Report 4 从 `weekly_project_forecasts` 聚合到物料级。周历统一 Monday-start：snapshot 为星期一时第 1 周从 snapshot 开始，否则从其后最近星期一开始；随后每 7 天一个桶，共 13 周。

---

## 10. 产品配置与生命周期

### 10.1 `platform.product_configs`

核心列：

- `product_config_id`、`product_config_type`、`product_config_name`、`product_name`、`config_version`；
- `project_id`（N:1，V1 每个 Product Config 只属于一个 Project）、`customer_id`；
- `customer_material_code`、产品一/二/三级分类；
- `business_unit_id`、`planning_department_id`、`research_representative_employee_id`；
- `product_config_status`、`product_team_name`；
- `modified_by_employee_id`、`modified_at`。

一个 Project 可关联多个 Product Config。`product_configs` 不保存单值 `material_id`。

### 10.2 `platform.product_config_materials`

Product Config ↔ Material 规范化关联表：

```text
PK  (dataset_version_id, product_config_material_id)
FK  product_config_id → product_configs
FK  material_id → materials
UQ  (dataset_version_id, product_config_id, material_id)
```

一个 Product Config 可关联多个 Material；同一 Material 也可出现在多个 Product Config 中。

### 10.3 `platform.project_lifecycle_history`

V1 正式使用项目级生命周期历史：

```text
PK (dataset_version_id, project_lifecycle_id)
FK project_id → projects
lifecycle_stage text not null check (lifecycle_stage in ('NPI', 'MASS_PRODUCTION', 'EOL'))
effective_from date not null
effective_to date null
```

同一项目有效区间不得重叠，采用 `[effective_from,effective_to)`。受控值至少包括 `NPI`、`MASS_PRODUCTION`、`EOL`，后续增加值必须走契约变更。After-sales 不是 lifecycle stage，不得加入此字典。

---

## 11. 囤料历史

### 11.1 `platform.stockpile_versions`

核心列：`stockpile_version_id`、`version_name`、`version_date`、`is_valid`、`sequence_no`、`description`。dataset 内版本名唯一；同日优先规则与 Forecast 分开管理。

### 11.2 `platform.stockpile_records`

```text
PK/UQ (dataset_version_id, stockpile_version_id, material_id)
FK stockpile_version_id → stockpile_versions
FK material_id → materials
stockpile_nature text not null
planned_stockpile_qty numeric >= 0
inventory_qty numeric >= 0
inventory_unit_price numeric null
agreement_unit_price numeric null
currency_code char(3) null
seven_day_demand_qty numeric >= 0
owner_employee_id uuid null
owner_department_id uuid null
```

其余 GAP、完成率、预警和金额为辅助模拟字段，不参与五类超期根因判断，优先在 View/服务计算；具体 Mock 公式延后至 Generator 阶段固定，不阻塞 Phase 1，也不得在此之前以正式派生列落库。

### 11.3 `platform.stockpile_forecasts`

```text
PK/UQ (stockpile_version_id, material_id, forecast_month)
FK demand_signal_id → demand_signals
forecast_qty numeric >= 0
```

这是 Report 6 未来半年需求的长表来源，与 Report 3/4 同源。第一个 `forecast_month` 固定为 `stockpile_version_date` 所在自然月的下一自然月，随后连续 6 个自然月。

### 11.4 `platform.stockpile_balance_projections`（新增）

保存 30/60/90/120/150/180 天结余：`stockpile_version_id`、`material_id`、`horizon_days`、`remaining_qty`、`remaining_amount`、`currency_code`。它是辅助模拟事实，只在 Generator 阶段固定 Mock 公式后生成。

### 11.5 `platform.stockpile_inventory_age_buckets`（新增）

保存 30/60/90/120/150/180/270/365 天库龄数量与金额。`bucket_semantics` 固定为 `CUMULATIVE`；每条记录表示累计超过该阈值，不能按互斥区间解释。

### 11.6 历史匹配查询

选择：`is_valid=true AND version_date<=order_date`，按 `version_date desc, sequence_no desc` 取一版，再以 `(version_id,material_id)` 查记录。不能跨 dataset，不能用当前最新版本替代。

---

## 12. 隐藏 Ground Truth

### 12.1 `evaluation.scenario_truth`

| 列 | 类型 | Null | 约束 |
|---|---|:---:|---|
| `scenario_truth_id` | uuid | N | PK |
| `dataset_version_id` | uuid | N | FK dataset |
| `po_line_schedule_id` | uuid | N | FK platform.po_line_schedules；Report 1 事实行一一对应 |
| `po_line_id` | uuid | N | FK platform.po_lines；dataset 一致 |
| `scenario_pattern` | text | N | 八种已定义 Pattern |
| `true_cause` | text | N | 五类枚举 |
| `true_cause_subtype` | text | Y | REDUCTION/DELAY/MIXED/NONE 等 |
| `causal_project_id` | uuid | C | Project FK；TRIAL 可按评测策略为空 |
| `demand_change_type` | text | N | REDUCTION/DELAY/MIXED/NONE |
| `lifecycle_state` | text | N | 必须等于 causal project 在 snapshot 的 `NPI/MASS_PRODUCTION/EOL` 有效记录 |
| `stockpile_flag` | bool | N | order_date as-of 真值 |
| `responsibility_type` | text | Y | CUSTOMER_SIDE/INTERNAL_SIDE/MPM 等 |
| `expected_action` | text | Y | 售后细化确认前可空 |

每个 `(dataset_version_id, po_line_schedule_id)` 只能有一条最终真值；`po_line_id` 必须等于该 schedule 的父行。表名、列名不得出现在普通 API 代码的 response schema、OpenAPI examples 或 Report Views。

---

## 13. Report Views

| View | 来源 | 主要动态处理 |
|---|---|---|
| `platform.view_report_1_overdue_po` | PO Header + Line + Schedule/Shipment + Master + dataset | schedule 开放数量、超期公式、只筛 `overdue_days>0` |
| `platform.view_report_2_supply_demand` | snapshot + components + mappings | 组件聚合、项目/客户集合、MPM |
| `platform.view_report_3_half_year_forecast_long` | monthly_forecasts + config | API 长表/数组来源 |
| `platform.view_report_3_half_year_forecast_export` | 同上 | 动态 M0～M+6 或真实 YYYYMM 透视 |
| `platform.view_report_4_13_week_forecast_long` | weekly forecasts + master | 13 周长表 |
| `platform.view_report_4_13_week_forecast_export` | 同上 | 第1～13周透视、合计、周均 |
| `platform.view_report_5_product_config` | config + lifecycle + master | snapshot 时点有效记录 |
| `platform.view_report_6_stockpile_long` | stockpile versions/records/forecast | as-of 与未来月长表 |
| `platform.view_report_6_stockpile_export` | 同上 | 六个月、结余、库龄透视 |

`evaluation` Schema 不能被任一公开 View 引用。可用数据库依赖扫描作为验收门禁。

## 14. 枚举/受控值建议

优先用 CHECK + 受控字典表，避免 PostgreSQL enum 难以演进。已确认集合：

- `cause_type`: TRIAL/STOCKPILE/DEMAND_ADJUSTMENT/AFTER_SALES/PROJECT_OBSOLESCENCE（仅 Evaluation/Analytics）；
- `demand_change_type`: REDUCTION/DELAY/MIXED/NONE；
- `responsibility_type`: CUSTOMER_SIDE/INTERNAL_SIDE/MPM，可按确认扩展非最终分类责任角色；
- `inventory_organization_type`: TRIAL/MASS_PRODUCTION；
- `project_lifecycle_stage`: NPI/MASS_PRODUCTION/EOL；
- `consumption_status`: FORECAST_AVAILABLE/NO_FORECAST_DEMAND。

状态、预警和辅助供需组件字典在相应 Generator 阶段按 Data Contract 固定；不影响已确认生命周期受控值。

## 15. 关键 CHECK、唯一性与排他约束

- 所有数量 `>=0`，除明确允许为正负净额/Gap 的字段。
- `schedule_qty >= 0`、`schedule_received_qty >= 0`，开放数量使用 `greatest(schedule_qty-schedule_received_qty,0)`。
- `effective_to IS NULL OR effective_to > effective_from`。
- 项目生命周期、Material→MPM 等时效区间不得重叠；可使用 GiST exclusion constraint。
- 月份为月首日；Report 4 的周起始日为 Monday-start，连续 13 周。
- `forecast_version.dataset_version_id`、`stockpile_version.dataset_version_id` 与所有子事实一致。
- `scenario_truth.causal_project_id` 必须与同 dataset 的 project 关联。
- 同 dataset 仅一个最新 weekly snapshot。

## 16. 索引建议

- 所有 FK 建前导索引，优先 `(dataset_version_id, fk_id)`。
- PO 查询：`(dataset_version_id, material_id, order_date)`、`po_number`、supplier/buyer/organization。
- Forecast：`(dataset_version_id, material_id, project_id, version_date)`；月事实按 `(material_id,project_id,forecast_version_id)`。
- Weekly：`(dataset_version_id, material_id, week_start_date)`。
- Lifecycle：`(dataset_version_id, project_id, effective_from, effective_to)`。
- Stockpile as-of：`(dataset_version_id, version_date desc) WHERE is_valid`；record `(version_id,material_id)`。
- Report 2：`(dataset_version_id, material_id)`；`organization_id` 指向 Material 的 Primary Inventory Organization。

## 17. 分区策略

Phase 1 不必过早物理分区。先用 dataset 前导索引和完整约束；当数据量证明需要时，对高容量事实表按 `dataset_version_id` hash/list 分区，或按日期 range 分区。分区不能削弱复合外键和 dataset 隔离。

## 18. Schema 决议状态

Phase 1 的 Schema 建设已无业务阻塞项。`DC-01/02/04/05/06/08/09/10/11/13/14` 已按本文件固化；以下事项仅影响后续阶段：

- `DC-03`：Report 2 辅助展示字段的 Mock 公式延后至 Generator 阶段，不改变三个核心字段合同；
- `DC-07-KD`：KD 完整业务释义仍为 `NEEDS_BUSINESS_CONFIRMATION`，但 KD 不进入任何核心判断；
- `DC-12`：Report 6 金额、GAP、完成率、结余和预警 Mock 公式延后至 Generator 阶段；
- `DC-15`：`RESOLVED_AS_SYNTHETIC_CONFIG`；Generator/Evaluation 默认 Mock 阈值已在 Phase 4 配置化固定，不代表企业真实规则；
- `DC-16`：售后正式处置仍为 `NEEDS_BUSINESS_CONFIRMATION`，不影响 Phase 1 Schema。
