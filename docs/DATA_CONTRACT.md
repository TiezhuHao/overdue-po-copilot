# System A 数据契约

## 1. 文档状态与基线

本文件固化 System A 六类最终 Report 的展示契约、规范化存储关系、时间口径与跨表约束。依据仅包括 V2.0 Word 方案和六个“最终模板”Excel；模板内的业务字段均保留。无法从基线确定的定义使用 `NEEDS_BUSINESS_CONFIRMATION`，不得在实现时自行补全。

## 2. 全局约定

### 2.1 类型与标记

| 记号 | 含义 |
|---|---|
| `uuid` | 内部稳定 ID；业务报表一般不展示 |
| `text` | 可变长度文本或业务编码 |
| `date` / `timestamptz` | 日期 / 带时区时间戳 |
| `qty` | `numeric(20,4)`，数量 |
| `money` | `numeric(20,4)`，金额；必须同时有货币代码或明确报表单位 |
| `ratio` | `numeric(12,6)`，比率以 0～1 保存 |
| `bool` | 布尔值 |
| `list<text>` | API 数组；Excel 中按确定分隔符拼接展示 |
| `R` / `D` | 原始或直接映射字段 / 派生字段 |
| Nullable `N` | Report View 必须非空；数量类通常以 0 输出 |
| Nullable `Y` | 允许为空 |
| Nullable `C` | 条件可空，条件见来源/约束 |
| API `Y` | 可通过普通业务 API 暴露 |

所有 Report View 必须带有或接受 `dataset_version_id` 上下文。模板未展示的内部 ID 可以在机器 API 中作为中性关联字段返回，但 Excel 导出默认只还原模板业务列。`scenario_truth` 及其字段永远 API=`N`。

### 2.2 全局业务时间

```text
current_business_date = dataset_versions.snapshot_date

overdue_threshold_date = order_date + material_lt_days + 240 days
overdue_days = snapshot_date - order_date - material_lt_days - 240
is_overdue = overdue_days > 0

forecast_anchor_date = order_date + material_lt_days
stockpile_as_of_date = order_date
```

- 禁止使用运行机器当前日期参与业务计算。
- `due_date` 只做交付展示/追踪；不是本项目的超期定义。
- Forecast Version 默认每周生成一版；同日存在补发/修订时，只保留 `is_valid=true` 且 `sequence_no` 最大的版本作为该日最终版本，`is_valid=false` 永远跳过。
- Forecast Baseline 是 Anchor **之前**最近一个有效最终版本；再选 Anchor **之后** 2～5 个有效最终版本，总窗口 3～6 版，默认 Baseline + 后 3 版。Anchor 同日版本既不属于 Baseline，也不属于“Anchor 之后”。

### 2.3 跨报表稳定关系

| 关系 | 规则 |
|---|---|
| Material | Report 1 的 `material_id` 必须可关联 Report 2/3/4/6 的同一主数据 |
| Project | Report 3 的 `project_id` 必须可关联 Report 5；名称不得作为数据库 Join 键 |
| PO Project | `po_reference_project_id` 可以与 Evaluation-only 的 `causal_project_id` 不同 |
| MPM | `material_id → employee_id(role=MPM)`；不是 Project → MPM |
| LT | 超期和 Forecast Anchor 使用同一个 `materials.material_lt_days` |
| Forecast | Report 3/4/6 必须可追溯到同一 Underlying Demand Signal |
| Lifecycle | Report 5 在 `snapshot_date` 返回时点有效生命周期 |
| Stockpile | Report 6 按 `order_date` 选择当天或之前最近的有效版本 |

---

## 3. Report 1：超期 PO 明细

### 3.1 目的、粒度与键

- **目的**：System A 的分析入口，返回满足项目超期定义的采购订单未交记录，不泄漏诊断答案。
- **数据关系**：PO Header → PO Line → PO Line Schedule / Shipment。
- **Excel 与事实粒度**：`PO号 + PO行 + 发运号`，即每个 PO Line Schedule / Shipment 一行。
- **数据库粒度与 Primary Key**：`po_line_schedules`，主键 `po_line_schedule_id`；一个 PO 行可有多个发运号。Generator V1 默认每个 PO Line 生成 1 个 Shipment，但 Schema 和 Report 契约不得退化，必须支持多个。
- **Foreign Keys**：`dataset_version_id`、`po_line_id`、`material_id`、`supplier_id`、`organization_id`、`business_entity_id`、`po_reference_project_id`、采购/计划责任人的 `employee_id`。
- **普通 API**：所有下列模板业务字段可暴露；禁止加入原因、超期类型、项目 EOL、根因项目、责任路径和期望对策。

### 3.2 字段契约

| 中文字段 | 内部字段 | 类型 | Null | R/D | 来源、公式与约束 | API |
|---|---|---:|:---:|:---:|---|:---:|
| 库存组织 | `inventory_organization_code` | text | N | R | `organizations.organization_code` | Y |
| 库存组织类型 | `inventory_organization_type` | text | N | R | 受控值至少含 `TRIAL`、`MASS_PRODUCTION`；Excel 显示试产/量产 | Y |
| 业务实体 | `business_entity_name` | text | N | R | 业务实体组织主数据 | Y |
| 订单号 | `po_number` | text | N | R | PO 业务键组成部分 | Y |
| 订单行 | `po_line_number` | integer | N | R | 同订单内唯一 | Y |
| 订单行发运号 | `shipment_number` | integer | N | R | 同订单行内唯一 | Y |
| 关闭状态 | `close_status` | text | N | R | PO 状态受控值，字典待实现时固定 | Y |
| 项目名称 | `reference_project_name` | text | C | R | `po_reference_project_id` 的展示名称；不是根因项目 | Y |
| 物料编码 | `material_code` | text | N | R | `materials.material_code` | Y |
| 物料描述 | `material_description` | text | Y | R | 物料主数据 | Y |
| 规格型号 | `specification_model` | text | Y | R | 物料主数据 | Y |
| 供应商编码 | `supplier_code` | text | N | R | 供应商主数据 | Y |
| 供应商名称 | `supplier_name` | text | N | R | 供应商主数据 | Y |
| 数量 | `schedule_qty` | qty | N | R | 该发运/计划行数量，`schedule_qty >= 0` | Y |
| 接收数量 | `schedule_received_qty` | qty | N | R | 该发运/计划行累计接收数量，`schedule_received_qty >= 0` | Y |
| 超期未交数量 | `overdue_open_qty` | qty | N | D | `greatest(schedule_qty-schedule_received_qty,0)` | Y |
| 物料属性 | `material_attribute` | text | Y | R | 物料分类辅助字段 | Y |
| 物料大类 | `material_category_level_1` | text | Y | R | 物料分类 | Y |
| 物料中类 | `material_category_level_2` | text | Y | R | 物料分类 | Y |
| 订单下达日期 | `order_date` | date | N | R | 超期、Forecast Anchor、历史囤料查询的基准 | Y |
| 应交日期 | `due_date` | date | N | D | Mock V1：`order_date + material_lt_days`；不参与超期定义 | Y |
| 数据快照日期 | `snapshot_date` | date | N | R | 等于 `dataset_versions.snapshot_date` | Y |
| 物料LT | `material_lt_days` | integer | N | R | 物料主数据，单位天，`>=0` | Y |
| 超期天数 | `overdue_days` | integer | N | D | `snapshot_date-order_date-material_lt_days-240`，返回行必须 `>0` | Y |
| 是否超期 | `is_overdue` | bool | N | D | `overdue_days > 0`；本 Report 固定为 true | Y |
| 订单采购员 | `order_buyer_name` | text | N | R | PO 下单时采购员 | Y |
| 默认采购员 | `default_buyer_name` | text | Y | R | 物料/组织默认采购员 | Y |
| 物控员 | `material_controller_name` | text | Y | R | 物料责任人 | Y |
| 计划经理 | `planning_manager_name` | text | Y | R | 责任链辅助字段 | Y |
| 计划总监 | `planning_director_name` | text | Y | R | 责任链辅助字段 | Y |
| 采购经理 | `purchasing_manager_name` | text | Y | R | 责任链辅助字段 | Y |
| 采购总监 | `purchasing_director_name` | text | Y | R | 责任链辅助字段 | Y |
| 通知接收人 | `notification_recipient_name` | text | Y | R | 通知辅助字段；试产主责任仍取 Material → MPM | Y |
| 参考编号（项目） | `reference_project_code` | text | C | R | `po_reference_project_id` 的业务编码 | Y |
| 是否可关闭 | `can_close` | bool | N | R | PO 执行状态字段 | Y |
| 完成时间 | `completion_at` | timestamptz | C | R | 未完成时为空 | Y |
| PO状态 | `po_status` | text | N | R | PO 状态受控值 | Y |

### 3.3 业务约束

```text
snapshot_date = dataset_version.snapshot_date
is_overdue = true
overdue_days > 0
schedule_qty >= 0
schedule_received_qty >= 0
overdue_open_qty = greatest(schedule_qty - schedule_received_qty, 0)
```

Report 1 禁止出现：`cause_type`、`true_cause`、原因/进展、项目是否 EOL、`causal_project_id`、`responsibility_type`、`expected_action`。

Ground Truth / Evaluation Sample 应绑定 `po_line_schedule_id`，使每个 Report 1 行与评测样本一一对应；可同时保留其父级 `po_line_id` 作为 lineage，但不得用行级 ID 替代 schedule 级评测键。

---

## 4. Report 2：物料供需汇总

### 4.1 目的、粒度与键

- **目的**：给出物料当前供应/需求、供需盈余、项目集合和 Material → MPM 责任关系。
- **模板声明粒度**：每个物料编码一行。
- **Primary Key**：`(dataset_version_id, material_id)`。System A V1 一个 Material 绑定一个 Primary Inventory Organization，因此 Report 2 保持 `1 Material = 1 Row`；`organization_id` 仍保留以支持未来 Material × Organization 扩展。
- **Foreign Keys**：`material_id`、`organization_id`、主供应商 `supplier_id`、采购/物控/MPM 的 `employee_id`。
- **核心公式**：`supply_demand_surplus_qty = all_supply_qty - actual_demand_total_qty`；正数表示供应超过实际需求。
- **普通 API**：模板所有字段可暴露。项目/客户集合在 JSON API 中为数组，不用名称字符串 Join。

### 4.2 身份、责任与主数据字段

| 中文字段 | 内部字段 | 类型 | Null | R/D | 来源/约束 | API |
|---|---|---:|:---:|:---:|---|:---:|
| 库存组织 | `inventory_organization_code` | text | N | R | 组织主数据 | Y |
| 计划方法 | `planning_method` | text | Y | R | 物料-组织计划属性 | Y |
| 物料编码 | `material_code` | text | N | R | 物料主数据 | Y |
| 物料描述 | `material_description` | text | Y | R | 物料主数据 | Y |
| 采购类别 | `purchasing_category` | text | Y | R | 物料采购属性 | Y |
| 替代组 | `substitute_group_code` | text | Y | R | 物料替代关系 | Y |
| 供应商 | `supplier_code` | text | Y | R | 主供应商业务编码 | Y |
| 供应商名称(英文) | `supplier_name_en` | text | Y | R | 供应商主数据 | Y |
| 物料类别 | `material_category_code` | text | Y | R | 物料分类 | Y |
| 类别说明 | `material_category_description` | text | Y | R | 物料分类 | Y |
| 采购员 | `buyer_name` | text | Y | R | 物料-组织责任关系 | Y |
| 物控员 | `material_controller_account` | text | Y | R | 责任人账号/标识 | Y |
| 物控员名字 | `material_controller_name` | text | Y | R | 员工主数据 | Y |
| 物控员代码 | `material_controller_code` | text | Y | R | 员工业务编码 | Y |
| 主物控员名称 | `primary_material_controller_name` | text | Y | R | 物料主责任人 | Y |
| MPM编号 | `mpm_code` | text | N | R | `material_mpm_assignments` 当前有效记录 | Y |
| MPM姓名 | `mpm_name` | text | N | R | 员工主数据 | Y |
| MPM部门 | `mpm_department_name` | text | N | R | 组织主数据 | Y |
| 物料提前期 | `material_lt_days` | integer | N | R | 超期和 Anchor 主用 LT，单位天 | Y |
| 原厂LT | `manufacturer_lt_days` | integer | Y | R | 辅助 LT，单位天；不得替代主用 LT | Y |

### 4.3 供应、需求与汇总字段

除特别说明外，下表数量均为 `qty`、Null=`N`、API=`Y`，原始组件缺失时 View 输出 0。System A 超期分析真正依赖的核心字段仅为 `all_supply_qty`、`actual_demand_total_qty` 和 `supply_demand_surplus_qty`，其中 `supply_demand_surplus_qty = all_supply_qty - actual_demand_total_qty`。其余供需汇总、多余库存/采购/工单/PR 等字段只用于辅助展示，不参与根因判断；辅助字段的最终 Mock 公式延后至 Generator 阶段固定，不阻塞 Phase 1。

| 中文字段 | 内部字段 | R/D | 来源/公式 |
|---|---|:---:|---|
| 良品VMI库存数量 | `good_vmi_inventory_qty` | R | 当前供需组件 |
| 良品非VMI库存数量 | `good_non_vmi_inventory_qty` | R | 当前供需组件 |
| 不良品库存数量 | `defective_inventory_qty` | R | 当前供需组件 |
| 不参与MRP库存数量 | `non_mrp_inventory_qty` | R | 当前供需组件 |
| 虚拟不良品库存 | `virtual_defective_inventory_qty` | R | 当前供需组件 |
| VMI在途订单数量 | `vmi_in_transit_order_qty` | R | 当前供需组件 |
| 非VMI在途订单数量 | `non_vmi_in_transit_order_qty` | R | 当前供需组件 |
| VMI在途送货数量 | `vmi_in_transit_delivery_qty` | R | 当前供需组件 |
| 非VMI在途送货数量 | `non_vmi_in_transit_delivery_qty` | R | 当前供需组件 |
| 采购申请数量 | `purchase_requisition_qty` | R | 当前供需组件 |
| 量产工单在制数量 | `mass_production_wip_qty` | R | 当前供需组件 |
| 非标工单在制数量 | `nonstandard_wip_qty` | R | 当前供需组件 |
| 虚拟计划单 | `virtual_planned_order_qty` | R | 当前供需组件 |
| 标准工单需求数量 | `standard_work_order_demand_qty` | R | 当前需求组件 |
| 非标准工单需求数量 | `nonstandard_work_order_demand_qty` | R | 当前需求组件 |
| 计划单需求数量 | `planned_order_demand_qty` | R | 当前需求组件 |
| 安全库存需求数量 | `safety_stock_demand_qty` | R | 当前需求组件 |
| 人工需求数量 | `manual_demand_qty` | R | 当前需求组件 |
| 长期预测需求 | `long_term_forecast_demand_qty` | R | 当前需求组件 |
| 所有供应 | `all_supply_qty` | D | 超期分析核心供应总量；Generator 阶段按显式配置生成 |
| 供需盈余量 | `supply_demand_surplus_qty` | D | `all_supply_qty - actual_demand_total_qty` |
| 供需汇总 | `supply_demand_summary_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 不参与MRP供需汇总 | `non_mrp_supply_demand_summary_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 计划单 | `planned_order_qty` | R | 当前计划结果 |
| 已到期预测计划单 | `expired_forecast_planned_order_qty` | R | 辅助展示；Mock 到期口径延后至 Generator 阶段 |
| 未到期预测计划单 | `unexpired_forecast_planned_order_qty` | R | 辅助展示；Mock 到期口径延后至 Generator 阶段 |
| 多余不参与MRP库存 | `excess_non_mrp_inventory_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 多余库存 | `excess_inventory_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 多余采购数量 | `excess_purchase_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 多余工单数量 | `excess_work_order_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 多余pr数量 | `excess_purchase_requisition_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 实际需求合计 | `actual_demand_total_qty` | D | 超期分析核心需求总量；Generator 阶段按显式配置生成 |

### 4.4 包装、项目、客户、库龄与采购结果

| 中文字段 | 内部字段 | 类型 | Null | R/D | 来源/约束 | API |
|---|---|---:|:---:|:---:|---|:---:|
| 最小包装 | `minimum_pack_qty` | qty | Y | R | 物料采购属性 | Y |
| 最小订单量 | `minimum_order_qty` | qty | Y | R | 物料采购属性 | Y |
| ncnr | `non_cancelable_non_returnable_flag` | bool | Y | R | 行业属性；Excel 保留模板标签 | Y |
| 组织在用项目 | `organization_active_projects` | list<text> | Y | D | 由有效 `material_projects` 按组织汇总 | Y |
| 集团在用项目 | `enterprise_active_projects` | list<text> | Y | D | 跨组织有效项目集合 | Y |
| 最多项目 | `top_project` | text | Y | D | snapshot 最新 13 周 Forecast 中该 Material 各 Project 需求贡献量最大的 Project；并列按稳定 `project_id` 排序 | Y |
| 所有项目 | `all_projects` | list<text> | Y | D | 辅助展示；历史/当前范围延后至 Generator 阶段配置 | Y |
| 组织在用客户 | `organization_active_customers` | list<text> | Y | D | 由项目/客户关系汇总 | Y |
| 集团在用客户 | `enterprise_active_customers` | list<text> | Y | D | 跨组织客户集合 | Y |
| 所有客户 | `all_customers` | list<text> | Y | D | 辅助展示；历史/当前范围延后至 Generator 阶段配置 | Y |
| 0~90天库存 | `inventory_age_0_90_qty` | qty | N | R | 库龄桶 | Y |
| 90～180天库存 | `inventory_age_90_180_qty` | qty | N | R | 库龄桶 | Y |
| 180～360天库存 | `inventory_age_180_360_qty` | qty | N | R | 库龄桶 | Y |
| 360～540天库存 | `inventory_age_360_540_qty` | qty | N | R | 库龄桶 | Y |
| 540+天库存 | `inventory_age_540_plus_qty` | qty | N | R | 库龄桶 | Y |
| 0~90天库存剩余 | `remaining_inventory_age_0_90_qty` | qty | N | D | 辅助展示；Mock 抵扣顺序延后至 Generator 阶段 | Y |
| 90～180天库存剩余 | `remaining_inventory_age_90_180_qty` | qty | N | D | 同上 | Y |
| 180～360天库存剩余 | `remaining_inventory_age_180_360_qty` | qty | N | D | 同上 | Y |
| 360～540库存剩余 | `remaining_inventory_age_360_540_qty` | qty | N | D | 同上 | Y |
| 540+库存剩余 | `remaining_inventory_age_540_plus_qty` | qty | N | D | 同上 | Y |
| 规格型号 | `specification_model` | text | Y | R | 物料主数据 | Y |
| 累计下单 | `cumulative_ordered_qty` | qty | N | D | 辅助展示；Mock 起始范围延后至 Generator 阶段 | Y |
| 累计交付 | `cumulative_delivered_qty` | qty | N | D | 辅助展示；Mock 起始范围延后至 Generator 阶段 | Y |
| OPEN PO | `open_po_qty` | qty | N | D | snapshot 时仍开放的 PO 数量 | Y |
| LT内需求数量 | `demand_within_lt_qty` | qty | N | D | 从 snapshot 起主用 LT 窗口需求 | Y |
| 超物料LT Excess PO | `excess_po_beyond_material_lt_qty` | qty | N | D | 辅助展示；Mock 公式延后至 Generator 阶段（DC-03） | Y |
| KD最小包需求 | `kit_minimum_pack_demand_qty` | qty | Y | R | 仅辅助展示，不进入核心业务判断；`KD` 完整业务释义仍为 `NEEDS_BUSINESS_CONFIRMATION`，不阻塞 Phase 1 | Y |

### 4.5 试产字段

下列字段均保留模板的“(试产)”展示标签，数据库内部使用独立 `organization_type=TRIAL` 维度，不建议复制物理列。数量均为 `qty`、Null=`N`、API=`Y`。

| 中文字段 | 内部字段 | R/D | 来源/公式 |
|---|---|:---:|---|
| 良品VMI库存数量(试产) | `trial_good_vmi_inventory_qty` | R | 试产供需组件 |
| 良品非VMI库存数量(试产) | `trial_good_non_vmi_inventory_qty` | R | 试产供需组件 |
| 不良品库存数量(试产) | `trial_defective_inventory_qty` | R | 试产供需组件 |
| 虚拟不良品库存(试产) | `trial_virtual_defective_inventory_qty` | R | 试产供需组件 |
| VMI在途订单数量(试产) | `trial_vmi_in_transit_order_qty` | R | 试产供需组件 |
| 非VMI在途订单数量(试产) | `trial_non_vmi_in_transit_order_qty` | R | 试产供需组件 |
| VMI在途送货数量(试产) | `trial_vmi_in_transit_delivery_qty` | R | 试产供需组件 |
| 非VMI在途送货数量(试产) | `trial_non_vmi_in_transit_delivery_qty` | R | 试产供需组件 |
| 采购申请数量(试产) | `trial_purchase_requisition_qty` | R | 试产供需组件 |
| 量产工单在制数量(试产) | `trial_mass_production_wip_qty` | R | 模板原名保留；辅助 Mock 语义延后至 Generator 阶段 |
| 非标工单在制数量(试产) | `trial_nonstandard_wip_qty` | R | 试产供需组件 |
| 标准工单需求数量(试产) | `trial_standard_work_order_demand_qty` | R | 试产需求组件 |
| 非标准工单需求数量(试产) | `trial_nonstandard_work_order_demand_qty` | R | 试产需求组件 |
| 计划单需求数量(试产) | `trial_planned_order_demand_qty` | R | 试产需求组件 |
| 人工需求数量(试产) | `trial_manual_demand_qty` | R | 试产需求组件 |
| 长期预测需求(试产) | `trial_long_term_forecast_demand_qty` | R | 试产需求组件 |
| 所有供应(试产) | `trial_all_supply_qty` | D | 试产辅助供应汇总；Mock 包含项延后至 Generator 阶段 |
| 供需盈余量(试产) | `trial_supply_demand_surplus_qty` | D | `trial_all_supply_qty-trial_actual_demand_total_qty` |
| 供需汇总(试产) | `trial_supply_demand_summary_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 计划单(试产) | `trial_planned_order_qty` | R | 试产计划结果 |
| 已到期预测计划单(试产) | `trial_expired_forecast_planned_order_qty` | R | 辅助展示；Mock 到期口径延后至 Generator 阶段 |
| 未到期预测计划单(试产) | `trial_unexpired_forecast_planned_order_qty` | R | 辅助展示；Mock 到期口径延后至 Generator 阶段 |
| 多余库存(试产) | `trial_excess_inventory_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 多余采购数量(试产) | `trial_excess_purchase_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 多余工单数量(试产) | `trial_excess_work_order_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 多余pr数量(试产) | `trial_excess_purchase_requisition_qty` | D | 辅助展示；Mock 公式延后至 Generator 阶段 |
| 实际需求合计(试产) | `trial_actual_demand_total_qty` | D | 试产辅助需求汇总；Mock 包含项延后至 Generator 阶段 |

### 4.6 Excel 与数据库

- `supply_demand_snapshots` 保存物料/组织/快照头；`supply_demand_components` 以组件类型长表保存数量。
- 项目/客户集合由关系表聚合，避免在数据库中保存分隔字符串。
- 库龄使用 bucket 长表；Report View 再展开为模板列。
- 试产与量产优先用组织类型维度，而不是复制一套物理列。

---

## 5. Report 3：计划备料半年预测

### 5.1 目的、粒度与键

- **目的**：提供 Material × Project 跨 Forecast Version 的历史月预测，支持后续推断最可能项目及 REDUCTION/DELAY/MIXED/NONE。
- **数据库粒度**：`material_id × project_id × forecast_version_id × forecast_month`。
- **Excel 粒度**：每个物料-项目-预测版本一行，版本月 M0 到 M+6 共 7 个自然月横向展开。
- **Primary Key**：`(dataset_version_id, forecast_version_id, material_id, project_id, forecast_month)`。
- **Foreign Keys**：`forecast_version_id`、`material_id`、`project_id`、客户/组织维度 ID。
- **普通 API**：源字段与月预测可暴露；需求变化类型不是源字段，不得预填在 Report API。

### 5.2 字段契约

| 中文字段 | 内部字段 | 类型 | Null | R/D | 来源/公式与时间口径 | API |
|---|---|---:|:---:|:---:|---|:---:|
| 物料编码 | `material_code` | text | N | R | 物料主数据 | Y |
| BG | `business_group_name` | text | Y | R | 允许保留的模板展示术语；内部使用可解释英文名 | Y |
| 事业部 | `business_unit_name` | text | N | R | 项目有效配置 | Y |
| 计划部 | `planning_department_name` | text | N | R | 项目有效配置 | Y |
| 项目 | `project_name` | text | N | R | 通过 `project_id` 关联 | Y |
| 客户项目 | `customer_project_name` | text | Y | R | 展示字段，不作为 Join 键 | Y |
| 客户 | `customer_name` | text | Y | R | 客户主数据 | Y |
| 品牌 | `brand_name` | text | Y | R | 项目/产品属性 | Y |
| 产品类型 | `product_type` | text | Y | R | 项目/产品属性 | Y |
| 出货类型 | `shipment_type` | text | Y | R | 业务属性 | Y |
| 业务模式 | `business_mode` | text | Y | R | 业务属性 | Y |
| 数据来源 | `forecast_source` | text | N | R | Forecast 来源受控值 | Y |
| 数据版本 | `forecast_version_name` | text | N | R | 企业世界共享版本日历 | Y |
| 版本日期 | `forecast_version_date` | date | N | R | Anchor/Baseline 选择依据 | Y |
| 预测月1 | `forecast_qty_m0` | qty | N | D | 版本月；从长表透视 | Y |
| 预测月2 | `forecast_qty_m1` | qty | N | D | 版本月后第 1 月 | Y |
| 预测月3 | `forecast_qty_m2` | qty | N | D | 版本月后第 2 月 | Y |
| 预测月4 | `forecast_qty_m3` | qty | N | D | 版本月后第 3 月 | Y |
| 预测月5 | `forecast_qty_m4` | qty | N | D | 版本月后第 4 月 | Y |
| 预测月6 | `forecast_qty_m5` | qty | N | D | 版本月后第 5 月 | Y |
| 预测月7 | `forecast_qty_m6` | qty | N | D | 版本月后第 6 月 | Y |
| 汇总 | `forecast_total_qty` | qty | N | D | `sum(M0..M+6)` | Y |
| 累计发货 | `cumulative_shipped_qty` | qty | Y | D | Material × Project 从当前 dataset 历史起点至该 `forecast_version_date`（含）的累计发货数量 | Y |

### 5.3 版本日历辅助 Sheet

| 中文字段 | 内部字段 | 类型 | Null | 约束 |
|---|---|---:|:---:|---|
| 数据版本 | `forecast_version_name` | text | N | dataset 内唯一 |
| 版本日期 | `forecast_version_date` | date | N | 全体 PO 共享 |
| 是否有效 | `is_valid` | bool | N | Baseline/后续版本只选有效记录 |
| 日内序号 | `sequence_no` | integer | N | 同日补发/修订顺序；最大有效值为该日最终版本 |
| 说明 | `description` | text | Y | 版本说明 |

Mock Enterprise Platform V1 的 Forecast Version 默认每周生成一版。同日可有补发/修订版本；选择窗口前先按 `version_date` 过滤 `is_valid=true` 并取最大 `sequence_no`，得到每日唯一有效最终版本。

### 5.4 宽表/长表

数据库不得创建 `预测月1` 或 `202606` 等事实列。`monthly_forecasts.forecast_month` 统一存月首日；Excel 导出时用真实 `YYYYMM` 替换“预测月1～7”，API 使用 `months: [{forecast_month, forecast_qty}]`。

---

## 6. Report 4：最新版 13 周预测

### 6.1 目的、粒度与键

- **目的**：提供物料未来 13 周最新需求，用于后续计算预计消耗时间。
- **数据库粒度**：`material_id × weekly_forecast_snapshot_id × week_start_date`。
- **Excel 粒度**：每物料一行。V1 每个 Material 绑定一个 Primary Inventory Organization；`organization_id` 为未来扩展保留。
- **Primary Key**：底表 `(weekly_forecast_snapshot_id, material_id, week_start_date)`；View 当前按 `(dataset_version_id, material_id)` 唯一。
- **Foreign Keys**：`material_id`、`weekly_forecast_snapshot_id`、可选 `organization_id`。
- **普通 API**：模板字段均可暴露；预计消耗时间不在源表，由 Analytics 使用 Report 1 数量计算。

### 6.2 字段契约

| 中文字段 | 内部字段 | 类型 | Null | R/D | 来源/公式 | API |
|---|---|---:|:---:|:---:|---|:---:|
| 物料编码 | `material_code` | text | N | R | 物料主数据 | Y |
| 组织编码 | `organization_code` | text | N | R | 组织主数据 | Y |
| 规格型号 | `specification_model` | text | Y | R | 物料主数据 | Y |
| 组织在用项目 | `organization_active_projects` | list<text> | Y | D | 与 Report 2 一致 | Y |
| 集团在用项目 | `enterprise_active_projects` | list<text> | Y | D | 与 Report 2 一致 | Y |
| 最多项目 | `top_project` | text | Y | D | 与 Report 2 一致：最新 13 周中各 Project 需求贡献最大的 Project | Y |
| 品牌 | `brand_name` | text | Y | R | 物料/项目属性 | Y |
| 物料说明 | `material_description` | text | Y | R | 物料主数据 | Y |
| 替代组 | `substitute_group_code` | text | Y | R | 替代关系 | Y |
| 供应商 | `supplier_code` | text | Y | R | 供应商业务编码 | Y |
| 供应商(英文) | `supplier_name_en` | text | Y | R | 供应商主数据 | Y |
| 在用配置 | `active_configurations` | list<text> | Y | D | 有效产品配置集合 | Y |
| PCBA配置 | `assembled_board_configurations` | list<text> | Y | D | 允许保留的模板展示术语；内部使用可解释英文名 | Y |
| 采购员 | `buyer_name` | text | Y | R | 责任信息 | Y |
| 物控员 | `material_controller_account` | text | Y | R | 责任信息 | Y |
| 物控员名字 | `material_controller_name` | text | Y | R | 员工主数据 | Y |
| 物控员代码 | `material_controller_code` | text | Y | R | 员工主数据 | Y |
| MPQ | `minimum_pack_qty` | qty | Y | R | 最小包装量；缩写显示保留 | Y |
| 加工中提前期 | `in_process_lt_days` | integer | Y | R | 单位天 | Y |
| OPEN PR | `open_purchase_requisition_qty` | qty | N | R | snapshot 时开放采购申请 | Y |
| OPEN PO | `open_po_qty` | qty | N | R | snapshot 时开放 PO | Y |
| ASN | `advance_shipping_notice_qty` | qty | N | R | 在途通知数量 | Y |
| 其他供应 | `other_supply_qty` | qty | N | R | 辅助展示；Mock 组成范围延后至 Generator 阶段 | Y |
| 不良品子库 | `defective_subinventory_qty` | qty | N | R | 当前库存 | Y |
| 虚拟不良品库存 | `virtual_defective_inventory_qty` | qty | N | R | 当前库存 | Y |
| 良品子库 | `good_subinventory_qty` | qty | N | R | 当前库存 | Y |
| 库存已抵扣需求 | `inventory_net_of_demand_qty` | qty | N | D | 抵扣规则未定义 | Y |
| 历史累计下单总量 | `historical_cumulative_ordered_qty` | qty | N | D | 辅助展示；Mock 起算范围延后至 Generator 阶段 | Y |
| 数据快照日期 | `snapshot_date` | date | N | R | 等于 dataset snapshot | Y |
| 第1周 | `week_01_forecast_qty` | qty | N | D | 长表第 1 个周桶 | Y |
| 第2周 | `week_02_forecast_qty` | qty | N | D | 长表第 2 个周桶 | Y |
| 第3周 | `week_03_forecast_qty` | qty | N | D | 长表第 3 个周桶 | Y |
| 第4周 | `week_04_forecast_qty` | qty | N | D | 长表第 4 个周桶 | Y |
| 第5周 | `week_05_forecast_qty` | qty | N | D | 长表第 5 个周桶 | Y |
| 第6周 | `week_06_forecast_qty` | qty | N | D | 长表第 6 个周桶 | Y |
| 第7周 | `week_07_forecast_qty` | qty | N | D | 长表第 7 个周桶 | Y |
| 第8周 | `week_08_forecast_qty` | qty | N | D | 长表第 8 个周桶 | Y |
| 第9周 | `week_09_forecast_qty` | qty | N | D | 长表第 9 个周桶 | Y |
| 第10周 | `week_10_forecast_qty` | qty | N | D | 长表第 10 个周桶 | Y |
| 第11周 | `week_11_forecast_qty` | qty | N | D | 长表第 11 个周桶 | Y |
| 第12周 | `week_12_forecast_qty` | qty | N | D | 长表第 12 个周桶 | Y |
| 第13周 | `week_13_forecast_qty` | qty | N | D | 长表第 13 个周桶 | Y |
| 13周需求合计 | `thirteen_week_demand_qty` | qty | N | D | 13 个周桶之和 | Y |
| 周均需求 | `weekly_average_demand_qty` | qty | N | D | `thirteen_week_demand_qty / 13` | Y |

### 6.3 Analytics 计算（不属于源表字段）

```text
if thirteen_week_demand_qty = 0:
    estimated_consumption_months = null
    consumption_status = NO_FORECAST_DEMAND
else:
    estimated_consumption_months = overdue_open_qty / weekly_average_demand_qty * 12 / 52
    consumption_status = FORECAST_AVAILABLE
```

周历统一 Monday-start：若 `snapshot_date` 为星期一，则 `week_1_start=snapshot_date`；否则 `week_1_start` 为 snapshot 之后最近一个星期一。后续每周间隔 7 天，共 13 周。数据库存 `week_start_date`；API 返回 `weeks: [{week_start_date, forecast_qty}]`；Excel 再展开为第 1～13 周并建议同时显示实际日期。

---

## 7. Report 5：产品配置查询

### 7.1 目的、粒度与键

- **目的**：从最可能项目查询事业部、计划部门、生命周期与客户/产品背景。
- **模板粒度**：项目/产品配置/物料展开记录。一个 Project 可关联多个 Product Config；每个 Product Config 在 V1 只属于一个 Project；一个 Product Config 可关联多个 Material。
- **数据库主键**：`product_configs.product_config_id`；关联表使用 `product_config_material_id`；生命周期历史使用 `project_lifecycle_id`。Report 5 展开行以 `(product_config_id, material_id)` 稳定识别。
- **Foreign Keys**：`product_configs.project_id`、`product_config_materials.material_id`、`customer_id`、组织与员工 ID。
- **普通 API**：模板字段可暴露；EOL 原始生命周期字段可查询，但 Report 1 不得提前带出。

### 7.2 字段契约

| 中文字段 | 内部字段 | 类型 | Null | R/D | 来源/约束 | API |
|---|---|---:|:---:|:---:|---|:---:|
| 行号 | `row_number` | integer | N | D | 导出序号，不是稳定键 | Y |
| 产品配置类型 | `product_config_type` | text | N | R | 产品配置主数据 | Y |
| 产品配置名 | `product_config_name` | text | N | R | 产品配置主数据 | Y |
| 产品名称 | `product_name` | text | N | R | 产品主数据 | Y |
| 版本 | `product_config_version` | text | N | R | 配置业务版本 | Y |
| 物料编码 | `material_code` | text | C | R | 通过 `product_config_materials.material_id` 关联；同一配置可展开多行物料 | Y |
| 客户料号 | `customer_material_code` | text | Y | R | 客户侧展示 | Y |
| 所属事业部 | `business_unit_name` | text | N | R | snapshot 时有效组织归属 | Y |
| 计划部门 | `planning_department_name` | text | N | R | snapshot 时有效组织归属 | Y |
| 项目 | `project_name` | text | N | R | 通过 `project_id` 关联 | Y |
| 客户项目名 | `customer_project_name` | text | Y | R | 展示字段，不作 Join 键 | Y |
| 研发代表 | `research_representative_name` | text | Y | R | 员工责任关系 | Y |
| 修改者 | `modified_by_name` | text | Y | R | 维护审计 | Y |
| 修改时间 | `modified_at` | timestamptz | Y | R | 维护审计 | Y |
| 状态 | `product_config_status` | text | N | R | 配置状态受控值 | Y |
| 产品一级 | `product_category_level_1` | text | Y | R | 产品分类 | Y |
| 产品二级 | `product_category_level_2` | text | Y | R | 产品分类 | Y |
| 产品三级 | `product_category_level_3` | text | Y | R | 产品分类 | Y |
| 产品生命周期阶段 | `lifecycle_stage` | text | N | R | 项目级历史在 snapshot 时的有效值；至少 `NPI`、`MASS_PRODUCTION`、`EOL` | Y |
| 客户ID | `customer_code` | text | C | R | 模板业务 ID；数据库另用 `customer_id` | Y |
| 客户代号 | `customer_short_code` | text | Y | R | 客户展示 | Y |
| PDT团队名 | `product_team_name` | text | Y | R | 允许保留的模板展示术语；内部使用可解释英文名 | Y |

V1 生命周期底表固定为项目级 `project_lifecycle_history`，必须有 `effective_from`、`effective_to`，以 `[from,to)` 区间判定有效；同一项目在任一时点不得存在两条有效生命周期。After-sales 不是 `lifecycle_stage`，而是由 EOL、无明显需求变化和未来持续少量非零需求共同判断。

---

## 8. Report 6：囤料明细

### 8.1 目的、粒度与键

- **目的**：回答“PO 下单当时，物料是否处于主动囤料计划中”。
- **数据库粒度**：`stockpile_version_id × material_id`；未来月需求、结余预测和库龄分开存长表。
- **Excel 粒度**：每个历史囤料版本-物料一行，多级表头横向展开。
- **Primary Key**：`(stockpile_version_id, material_id)`。
- **Foreign Keys**：`stockpile_version_id`、`material_id`、责任员工/组织 ID。
- **普通 API**：模板字段可暴露；`stockpile_flag` 若只是“是否存在有效记录”的查询结果可返回，但不得返回 `scenario_truth.stockpile_flag`。

### 8.2 基础与计划字段

| 中文字段 | 内部字段 | 类型 | Null | R/D | 来源/公式 | API |
|---|---|---:|:---:|:---:|---|:---:|
| 数据版本 | `stockpile_version_name` | text | N | R | 与 dataset_version 不同 | Y |
| 版本日期 | `stockpile_version_date` | date | N | R | 生效/快照日期 | Y |
| 囤料性质 | `stockpile_nature` | text | N | R | 主动囤料辅助展示；Mock 字典在 Generator 阶段固定 | Y |
| 采购类别 | `purchasing_category` | text | Y | R | 业务分类 | Y |
| 分析类别 | `analysis_category` | text | Y | R | 业务分类 | Y |
| 料号 | `material_code` | text | N | R | 等同其他 Report 的物料编码 | Y |
| 型号 | `model` | text | Y | R | 物料主数据 | Y |
| 物料描述 | `material_description` | text | Y | R | 物料主数据 | Y |
| 库存单价 | `inventory_unit_price` | money | Y | R | 货币见 `DC-12` | Y |
| 协议单价 | `agreement_unit_price` | money | Y | R | 货币见 `DC-12` | Y |
| 计划囤料数量 | `planned_stockpile_qty` | qty | N | R | `>=0`；是否命中的数量依据之一 | Y |
| 计划囤料金额(万元) | `planned_stockpile_amount_ten_thousand` | money | N | D | 辅助展示；Mock 价格/币种公式延后至 Generator 阶段 | Y |
| 库存数量 | `inventory_qty` | qty | N | R | 该版本库存 | Y |
| 七天需求数量 | `seven_day_demand_qty` | qty | N | D | 版本日起 7 天需求，同源 Demand Signal | Y |
| 总囤料数量（扣除7天需求） | `net_stockpile_qty_after_7d_demand` | qty | N | D | 名义公式 `inventory_qty-seven_day_demand_qty`；是否截断为 0 见 `DC-12` | Y |
| 总囤料金额(万元) | `total_stockpile_amount_ten_thousand` | money | N | D | 辅助展示；Mock 价格/币种公式延后至 Generator 阶段 | Y |
| 囤料数量GAP分析(计划-实际) | `stockpile_qty_gap` | qty | N | D | `planned_stockpile_qty - actual_stockpile_qty`；“实际”字段映射见 `DC-12` | Y |
| 囤货完成率 | `stockpile_completion_ratio` | ratio | C | D | 辅助展示；分母为 0 时 null，Mock 映射延后至 Generator 阶段 | Y |
| 超目标囤料金额(万元) | `excess_target_stockpile_amount_ten_thousand` | money | N | D | 辅助展示；Mock 公式延后至 Generator 阶段 | Y |
| 囤料不足预警 | `stockpile_shortage_warning` | text | Y | D | 辅助展示；Mock 阈值/字典延后至 Generator 阶段 | Y |

### 8.3 需求预测数量-未来半年

下列字段均为 `qty`、Null=`N`、D、API=`Y`，由 `stockpile_forecasts` 长表透视。实际 Excel 列标题应显示真实月份。

| 中文字段 | 内部字段 | 时间口径 |
|---|---|---|
| 未来第1月 | `future_month_01_demand_qty` | `stockpile_version_date` 所在自然月的下一自然月 |
| 未来第2月 | `future_month_02_demand_qty` | 连续第 2 月 |
| 未来第3月 | `future_month_03_demand_qty` | 连续第 3 月 |
| 未来第4月 | `future_month_04_demand_qty` | 连续第 4 月 |
| 未来第5月 | `future_month_05_demand_qty` | 连续第 5 月 |
| 未来第6月 | `future_month_06_demand_qty` | 连续第 6 月 |

### 8.4 结余预测（库存-消耗）(万元)

每个期限有“数量”和“金额”两个子列；数量为 `qty`，金额为 `money`（模板组标题单位万元），Null=`N`、D、API=`Y`。金额、GAP、完成率、结余、预警均为辅助模拟字段，不参与五类超期根因判断；具体 Mock 公式延后至 Generator 阶段固定，不阻塞 Phase 1。

| 中文层级字段 | 数量内部字段 | 金额内部字段 |
|---|---|---|
| 超30天未消耗 | `remaining_after_30d_qty` | `remaining_after_30d_amount_ten_thousand` |
| 超60天未消耗 | `remaining_after_60d_qty` | `remaining_after_60d_amount_ten_thousand` |
| 超90天未消耗 | `remaining_after_90d_qty` | `remaining_after_90d_amount_ten_thousand` |
| 超120天未消耗 | `remaining_after_120d_qty` | `remaining_after_120d_amount_ten_thousand` |
| 超150天未消耗 | `remaining_after_150d_qty` | `remaining_after_150d_amount_ten_thousand` |
| 超180天未消耗 | `remaining_after_180d_qty` | `remaining_after_180d_amount_ten_thousand` |

### 8.5 库龄分布(万元)与责任链

库龄每个阈值有数量/金额子列；数量 `qty`、金额 `money`（万元），Null=`N`、R/D=`D`、API=`Y`。所有“超30/60/90/120/150/180/270/365天”均为累计超过阈值，不是互斥区间；因此较高阈值的数量/金额不得大于较低阈值。

| 中文层级字段 | 数量内部字段 | 金额内部字段 |
|---|---|---|
| 超30天 | `inventory_age_over_30d_qty` | `inventory_age_over_30d_amount_ten_thousand` |
| 超60天 | `inventory_age_over_60d_qty` | `inventory_age_over_60d_amount_ten_thousand` |
| 超90天 | `inventory_age_over_90d_qty` | `inventory_age_over_90d_amount_ten_thousand` |
| 超120天 | `inventory_age_over_120d_qty` | `inventory_age_over_120d_amount_ten_thousand` |
| 超150天 | `inventory_age_over_150d_qty` | `inventory_age_over_150d_amount_ten_thousand` |
| 超180天 | `inventory_age_over_180d_qty` | `inventory_age_over_180d_amount_ten_thousand` |
| 超270天 | `inventory_age_over_270d_qty` | `inventory_age_over_270d_amount_ten_thousand` |
| 超365天 | `inventory_age_over_365d_qty` | `inventory_age_over_365d_amount_ten_thousand` |

| 中文字段 | 内部字段 | 类型 | Null | R/D | 来源 | API |
|---|---|---:|:---:|:---:|---|:---:|
| 囤料消耗预警 | `stockpile_consumption_warning` | text | Y | D | 辅助展示；Mock 状态/阈值延后至 Generator 阶段 | Y |
| 囤料呆滞预警 | `stockpile_obsolescence_warning` | text | Y | D | 辅助展示；Mock 状态/阈值延后至 Generator 阶段 | Y |
| 责任人 | `owner_name` | text | Y | R | 员工主数据 | Y |
| 责任人部门 | `owner_department_name` | text | Y | R | 组织主数据 | Y |
| 责任经理 | `owner_manager_name` | text | Y | R | 员工关系 | Y |
| 责任总监 | `owner_director_name` | text | Y | R | 员工关系 | Y |

### 8.6 历史版本选择

```sql
version_date <= order_date
AND is_valid = true
ORDER BY version_date DESC, sequence_no DESC
LIMIT 1
```

选中版本内存在该 `material_id` 的有效记录，且满足最终确认的有效条件，才返回业务查询 `stockpile_flag=true`。不能用当前最新版本替代历史版本。

---

## 9. 普通 API 与 Ground Truth 暴露矩阵

| 数据 | Report/API | Generator | Evaluation/Test |
|---|:---:|:---:|:---:|
| 六张模板原始/报表派生字段 | Y | Y | Y |
| 内部稳定 ID | Y（中性关联用，可按响应层级控制） | Y | Y |
| `scenario_truth.true_cause` | N | 写入 | Y |
| `true_cause_subtype` / `demand_change_type` | N | 写入 | Y |
| `causal_project_id` | N | 写入 | Y |
| `responsibility_type` / `expected_action` | N | 写入 | Y |
| 由 Report 证据即时算出的分析结果 | 不属于 System A 源 Report；由后续 Analytics API 管理 | N | Y |

---

## 10. Phase 0.1 决议状态与剩余确认项

| ID | 状态 | 固化结果 / 后续边界 |
|---|---|---|
| `DC-01/DC-02` | RESOLVED | Report 1 固定为 Header → Line → Schedule/Shipment，事实粒度为 PO号+PO行+发运号；开放数量按 schedule 级公式计算，评测绑定 `po_line_schedule_id`。 |
| `DC-03` | DEFERRED_TO_REPORT_VIEW（不阻塞 Phase 5C） | 根因分析只依赖三个核心字段及固定盈余公式；其余辅助展示字段的最终 Mock 映射留待 Report View 阶段固定。 |
| `DC-04` | RESOLVED | V1 一个 Material 一个 Primary Inventory Organization，Report 2/4 每物料一行；最多项目按最新 13 周 Project 贡献量。 |
| `DC-05/DC-06` | RESOLVED | Monday-start；Forecast 默认每周一版；同日取最大有效 `sequence_no`，无效版本跳过。 |
| `DC-07` | PARTIALLY_RESOLVED（不阻塞 Phase 1） | `BG/PDT/PCBA` 可保留；内部使用可解释英文名。仅 `KD` 完整释义仍为 `NEEDS_BUSINESS_CONFIRMATION`，且 KD 只作辅助展示。 |
| `DC-08/DC-09` | RESOLVED | 累计发货按 Material × Project 从 dataset 历史起点累计至版本日；Report 4 供应商字段为 code，英文列为 `supplier_name_en`。 |
| `DC-10/DC-11` | RESOLVED | Project 1:N Product Config、Product Config N:M Material；V1 生命周期为项目级历史，至少 NPI/MASS_PRODUCTION/EOL，After-sales 不是 lifecycle。 |
| `DC-12` | DEFERRED_TO_REPORT_VIEW（不阻塞 Phase 5C） | Report 6 金额、GAP、完成率、结余和预警为辅助模拟字段；底层数量与连续结余公式已固定，最终展示 Mock 映射留待 Report View 阶段。 |
| `DC-13/DC-14` | RESOLVED | 未来第 1 月为版本月下一自然月；库龄阈值为累计超过。 |
| `DC-15` | `RESOLVED_AS_SYNTHETIC_CONFIG` | Phase 4 已通过 `ScenarioGenerationConfig` 固定需求变化与 After-sales 默认 Mock 阈值，完整参数见 `SCENARIO_RULES.md`；参数可配置并进入 Scenario signature，不是企业真实硬规则。 |
| `DC-16` | `NEEDS_BUSINESS_CONFIRMATION`（不阻塞 Phase 1） | 正式售后处置、保留量与保供周期仍待确认；不得自行生成正式 `expected_action`。 |

Phase 1 已无业务阻塞项。以上延后项不得被当作正式企业规则，但不影响基础设施骨架和规范化 Schema 建设；`DC-16` 只阻塞后续售后正式对策与相应评测完成。

## 11. Phase 5A 基础证据实现说明

不改变六个最终模板字段。Report 5 的 Project/Config/Material 关系和项目级时效 Lifecycle 已落库；`config_version` 未来映射展示字段 `product_config_version`。

Report 3/4/6 未来统一由 `demand_signals` 的日点及 `demand_signal_revisions` 的中性数量修订派生。`demand_date` 是需求发生日，`observed_on` 是企业需求源修订观察日，两者不能混用；读取 as-of 数量必须跳过未来修订。源观测长表不是 Forecast Version，也不是额外报表字段。

Phase 5A 只验证实体 lineage、可观察数量形态与生命周期，正式 Forecast 周版本、月周聚合报表及 Stockpile 版本匹配仍由后续阶段实现。`DC-15` 状态不变；`DC-16` 正式售后处置仍不生成。

Phase 5A.1 将临时预算恢复/扣减改为持续有效的源计划状态，并增加七种周度发布偏移与无效版本 dry-run。报表粒度、Anchor、严格前后版本选择、Monday-start、七个月/13周契约及 Scenario 阈值全部不变；实际 Forecast facts 仍由 Phase 5B 生成。

## 12. Phase 5B Forecast facts 实现口径

- Forecast Calendar 从共享 Demand 历史起点之后的首个星期一至 dataset snapshot，默认每周发布，所有 PO 共用；ID 由 dataset signature + 日期 + sequence 确定。
- Report 3 的展示窗口仍为版本月 M0～M+6。月事实额外保留最多前2个月、后1个月的重叠桶（历史起点前不补造），以支持跨月版本在同一 Anchor 七个月窗口比较；这些不是新增 Excel 列，也不改变展示汇总的七个月口径。
- 月事实逐日汇总该版本日 `observed_on <= version_date` 的共享源数量；同日修订版可有相同数量，不为演示修订而重新随机需求。
- Weekly Project Facts 使用 snapshot 当日源观测、Monday-start 连续13周。Material Weekly Facts 必须逐周等于全部 Project 贡献之和；保留主组织 FK，仍一物料一组13周。最多项目并列按稳定 project ID 排序。
- Weekly Snapshot 指向当时最新有效最终 Forecast Version；对完整覆盖自然月核对月/周来源数量，容差只用 Scenario config 中的 `forecast_rounding_tolerance`。
- Synthetic 项目发货是独立于 PO receipt 的履约事实：每周一记录截至当天的最近7日（截断至源历史起点）源计划数量 × 配置履约比例，默认0.8，以当日源观测生成并固定，不因未来修订重算历史实际发货。累计发货按 Material×Project 从历史起点累加至版本日（含）。这只是 Mock 履约策略，不是企业硬规则。
- 正式 Report 3/4 Views、API、Excel 与 PO consumption action 未实现。

## 13. Phase 5C Operational facts（纠偏后）

- 供需快照仍为 Dataset × Material × Primary Organization × snapshot_date，V1每物料一行。组件保留来源域、SUPPLY/DEMAND、TRIAL/MASS_PRODUCTION和来源键；三个核心字段只由组件聚合。
- OPEN PO仅取未关闭/取消的Header、Line与Schedule，数量为schedule未收货量。该量按配置拆成OPEN_PO和IN_TRANSIT，两者相加等于原未收货量；IN_TRANSIT是synthetic component，不是ASN事实，也不重复计入received。
- 当前实际需求使用snapshot起连续、不重叠的7日工单、14日计划、7日近端预测窗口，源数量分别乘0.85/0.75/0.60并四位Decimal舍入。参数可配置；这是Mock变换，不等同未来13周Forecast。
- 库存以共享近端需求和seeded覆盖比例派生，on_hand = available + quality_hold + blocked。试产来自组件组织主数据类型，试产合计是组件子集；不读取Cause设置试产字段。MPM直接引用已有material_mpm_assignments的snapshot有效记录；material_responsibility_assignments保持既有采购/物控责任用途。
- 两类库龄统一保存累计大于阈值：30/60/90/120/150/180/270/360/365/540。额外360/540阈值支持Report2后续区间差分；不能直接把累计值当成互斥桶。
- Stockpile Version共享历史日历，默认7日间隔（不依赖Forecast weekday），含同日修订和无效版本夹具、snapshot及snapshot+7日反例。历史选择先限制dataset与version_date<=order_date，再取有效最大日期/sequence；有版本无记录和无有效版本分别表达。
- Stockpile forecast保持Version×Material×Month六个自然月，汇总该物料所有Project在version_date的有效日需求。demand_lineage JSON数组保存每个Project、Signal和数量；Validator逐项验证完整性、dataset归属、as-of修订和数量，不选任意单个Signal充当物料总量。
- target_stockpile_qty对应后续planned_stockpile_qty，stockpile_tag对应stockpile_nature；inventory_qty与actual_stockpile_qty在Mock V1相等。target是囤料周期内预测之和，actual按配置完成比例派生；target=0的基础完成率返回null。
- 月结余首期为inventory减版本日至本月末需求；后续opening等于上月closing，closing=opening+inbound-demand。净结余允许为负并保留缺口，不截断；这不是最终模板30/60/...天或金额公式。
- DC-03辅助汇总/excess及DC-12金额、GAP、预警和最终展示完成率映射状态为DEFERRED_TO_REPORT_VIEW；不阻塞核心事实。DC-16仍为NEEDS_BUSINESS_CONFIRMATION。
