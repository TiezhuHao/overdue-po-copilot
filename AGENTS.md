# System A 工程守则

## 1. 适用范围

本仓库当前建设 **Overdue PO Copilot 的 System A：Mock Enterprise Data Platform**。System A 模拟企业内部多源数据系统，提供稳定、可重复、可测试、跨源一致、支持历史版本的业务数据与 REST API。

System A **不负责** AI/LLM 推理、超期根因判断、Agent 编排或业务前端。除非任务明确进入相应阶段，不得提前实现后续 Copilot。

## 2. 唯一业务基线

- 总体设计基线：V2.0 Word 方案。
- 报表展示契约：六个文件名含“最终模板”的 Excel。
- 已固化规格：本文件及 `docs/` 下的工程规格。
- 不得引用、恢复或推测旧版本设计。
- Word、最终 Excel 与固化规格发生实质冲突时，停止猜测，标记 `NEEDS_BUSINESS_CONFIRMATION`。
- 不得自行改变已确认的业务判断顺序、五类 `cause_type`、时间公式或责任路径。

## 3. 技术方向

- 先建立统一的 **Synthetic Enterprise World**，再派生规范化 PostgreSQL 数据、六类 Report View / Query Service、FastAPI，最后由后续 Copilot 调用。
- Python 服务栈方向为 SQLAlchemy、Alembic、FastAPI、pytest；具体版本在 Phase 1 固定。
- Excel 是展示契约，不是物理数据库表。动态月、周、版本必须存成长表，并在 View/导出层透视。
- 当前阶段未明确授权时，不得实现数据库、Generator、API、Agent、前端或 Docker 业务逻辑。

## 4. 不可违反的数据原则

1. **先造世界，再出报表**：禁止六张报表各自随机造数。
2. **Forecast 同源**：Report 3、4、6 必须从同一个 Underlying Demand Signal 派生。
3. **固定业务时间**：所有“当前”均使用 `dataset_version.snapshot_date`，不得读取运行机器真实日期参与业务判断。
4. **版本分层**：`dataset_version`、`forecast_version`、`stockpile_version` 是不同概念；一个 dataset 可包含多个 Forecast/Stockpile 版本。
5. **确定性生成**：相同生成输入（至少 seed、snapshot_date、generator/schema 版本及生成配置）必须得到相同业务世界；`generated_at` 等运行元数据不参与业务内容哈希。
6. **稳定内部键**：Join 优先使用 `material_id`、`project_id`、`customer_id`、`supplier_id`、`employee_id`、`organization_id` 及各事实表 ID；名称和业务编码仅用于展示与查找。
7. **项目语义分离**：`po_reference_project_id` 只是 PO 参考项目；隐藏真值中的 `causal_project_id` 可以不同。
8. **MPM 是物料级关系**：使用 Material → MPM，不得改成 Project → MPM。
9. **历史囤料查询**：以 `order_date` 为 `stockpile_as_of_date`，选当天或之前最近的有效 Stockpile Version。
10. **Report 1 正式粒度**：数据关系固定为 PO Header → PO Line → PO Line Schedule / Shipment；Report 1 一行对应 `PO号 + PO行 + 发运号`。Generator V1 默认每个 PO Line 生成 1 个 Shipment，但 Schema 必须支持多个。
11. **V1 主库存组织**：一个 Material 只绑定一个 Primary Inventory Organization；Report 2 与 Report 4 均保持 `1 Material = 1 Row`，Schema 保留 `organization_id` 供未来扩展。
12. **周历与版本日历**：13 周预测使用 Monday-start；Forecast Version 默认每周一版。同日有效版本以最大 `sequence_no` 为最终版本，`is_valid=false` 永远跳过。
13. **项目生命周期**：V1 使用项目级 `project_lifecycle_history`，受控值至少为 `NPI`、`MASS_PRODUCTION`、`EOL`；After-sales 不是 lifecycle stage。

## 5. 固定业务公式

```text
overdue_threshold_date = order_date + material_lt_days + 240 days
overdue_days = snapshot_date - order_date - material_lt_days - 240
is_overdue = overdue_days > 0

forecast_anchor_date = order_date + material_lt_days

overdue_open_qty = max(schedule_qty - schedule_received_qty, 0)

supply_demand_surplus_qty = all_supply_qty - actual_demand_total_qty

weekly_average_demand_qty = thirteen_week_demand_qty / 13
estimated_consumption_months = overdue_open_qty / weekly_average_demand_qty * 12 / 52
```

`thirteen_week_demand_qty = 0` 时，预计消耗月数必须为 `null`，状态为 `NO_FORECAST_DEMAND`，禁止除零。应交日期不是本项目判断超期的核心依据。

Forecast Anchor 选择必须先将每个版本日归并为“最大 `sequence_no` 的有效最终版本”，再取 Anchor 之前最近一版作为 Baseline，并取 Anchor 之后 2～5 个有效最终版本。无明显需求下修/延后时，必须先判断 After-sales，再判断历史囤料；After-sales 被排除后，`STOCKPILE` 与 `PROJECT_OBSOLESCENCE / INTERNAL_SIDE` 的 lifecycle 均可为 `EOL` 或非 `EOL`。

## 6. Ground Truth 隔离与答案防泄漏

- `scenario_truth` 只允许 Generator、Evaluation 与测试访问。
- 普通业务数据库角色、Report View、Repository、Pydantic Schema、OpenAPI、REST 响应、Excel 导出均不得暴露 Ground Truth。
- Report 1 不得出现 `cause_type`、原因/进展、项目 EOL、`causal_project_id`、期望对策等诊断答案。
- 源 Forecast 不得预填 `REDUCTION` / `DELAY` / `MIXED` 等分析结论；这些由后续 Analytics/Copilot 计算。

## 7. 业务分类不可扩展

最终 `cause_type` 只能是：

```text
TRIAL
STOCKPILE
DEMAND_ADJUSTMENT
AFTER_SALES
PROJECT_OBSOLESCENCE
```

`DEMAND_ADJUSTMENT` 可用 `REDUCTION`、`DELAY`、`MIXED` 作为内部子类型。`PROJECT_OBSOLESCENCE` 可走 `CUSTOMER_SIDE` 或 `INTERNAL_SIDE` 两条责任路径。Scenario Pattern 可以更多，但不得新增最终业务类型。

## 8. 命名与中性化（禁止企业专有缩写）

- 项目业务字段中文统一为“项目”，英文统一为 `project`。
- 新增代码、SQL、字段、Mock 值、API、Excel、README、注释、测试与 Prompt 禁止使用企业专有缩写或企业前缀。
- `BG`、`PDT`、`PCBA` 允许作为模板展示术语保留，不属于禁止的企业名称缩写；内部字段仍使用可解释英文名。
- `KD` 只作为辅助展示字段，不进入核心业务判断；完整释义可标记 `NEEDS_BUSINESS_CONFIRMATION`，但不得阻塞 Phase 1。

## 9. 修改前的最小阅读集

- 任何修改：先读本文件。
- 报表字段、公式、键、宽/长表：读 `docs/DATA_CONTRACT.md`。
- Generator、场景、Ground Truth、Forecast 证据：读 `docs/SCENARIO_RULES.md`。
- 表、约束、索引、角色：读 `docs/DB_SCHEMA.md`。
- 模块、API、授权与返回结构：读 `docs/ARCHITECTURE_API.md`。
- 测试、验收或重构：读 `docs/ACCEPTANCE_TESTS.md`。

只读取当前任务需要的文档；若已固化规格足够，不要反复解析原始 Word/Excel。

## 10. 变更纪律

- 优先用测试固化规则；修改契约时同步更新相关规格和验收测试。
- 未获业务确认，不得把 `NEEDS_BUSINESS_CONFIRMATION` 事项悄悄转成实现假设。
- 发现规格不一致时，记录来源、影响范围与待确认问题，不得用“合理默认值”掩盖业务歧义。
