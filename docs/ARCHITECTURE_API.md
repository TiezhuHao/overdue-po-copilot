# System A Architecture & API 规划

## 1. 范围

本文件规划未来 System A 的组件、数据流和 REST API 契约。本轮不实现 PostgreSQL、SQLAlchemy、Alembic、Generator、FastAPI、Agent、前端或 Docker 业务逻辑。

## 2. 目标架构

```text
Generation Config + random_seed + snapshot_date
                    │
                    ▼
       Synthetic Enterprise World
       ├─ Master Data
       ├─ PO / Supply / Inventory
       ├─ Underlying Demand Signal
       ├─ Forecast / Lifecycle / Stockpile History
       └─ Evaluation-only Scenario Truth
                    │
                    ▼
          Normalized PostgreSQL
       ├─ platform schema
       └─ evaluation schema (isolated)
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
 Report View / Query      Evaluation only
        Service          (separate DB role)
          │
          ▼
        FastAPI
          │
          ▼
  Overdue PO Copilot (future system)
```

核心规则：普通 API 的依赖图只能到 `platform`；Evaluation 依赖可以读公开 Report 和 `evaluation.scenario_truth`，但反向依赖禁止。

## 3. 模块边界

建议未来代码结构：

```text
app/
├─ api/
│  ├─ routes/             # dataset、六类 report、health
│  ├─ schemas/            # 公开请求/响应；禁止 truth 字段
│  └─ dependencies/       # dataset context、认证、分页
├─ db/
│  ├─ session.py
│  └─ migrations hooks
├─ models/
│  ├─ platform/           # 普通业务模型
│  └─ evaluation/         # 只供 generator/evaluator 导入
├─ repositories/
│  ├─ reports/            # 只读公开 View
│  └─ generation/         # 写入规范化事实
├─ services/
│  ├─ report_queries/
│  ├─ dataset_management/
│  └─ exports/
├─ generators/
│  ├─ master_data/
│  ├─ scenarios/
│  ├─ demand_world/
│  ├─ purchasing/
│  ├─ forecasts/
│  ├─ stockpile/
│  └─ validation/
└─ evaluation/            # 独立入口，不被 api 包导入
```

依赖方向：API → Service → Repository → View/DB。Generator 可以依赖规范化模型和 Scenario Rules，但 Report 代码不得依赖 Generator 内部真值。Evaluation 代码不得注册到公开 FastAPI router。

## 4. 数据生成流水线

1. 验证 `generation_config`，计算 canonical signature。
2. 建立 `dataset_version`，固定 `snapshot_date`。
3. 生成组织、人员、物料、供应商、客户、项目及稳定关系。
4. 为目标样本分配隐藏 Scenario Pattern 与 Truth。
5. 生成合法超期 PO 骨架；区分参考项目和根因项目。
6. 生成生命周期时间线。
7. 生成统一 Underlying Demand Signal。
8. 从 Demand Signal 派生 Forecast Version/月预测、最新周预测和历史囤料未来需求。
9. 生成 Stockpile Version/Record、当前库存和供需组件。
10. 构建/刷新公开 View，运行全部一致性和泄漏测试。
11. 计算业务内容哈希，将 dataset 标记为 `READY`。

写入应在数据库事务或可恢复的阶段边界内执行。状态为 `GENERATING/FAILED` 的 dataset 不得被普通 Report API 查询。

## 5. API 通用约定

### 5.1 Base URL 与版本

```text
/api/v1
```

API 版本独立于 `dataset_version`。破坏性响应变更通过 `/api/v2` 管理；生成器和 Schema 版本记录在 dataset 元数据。

### 5.2 Dataset Context

每个 Report 请求必须明确 dataset：

- 推荐 query：`dataset_version_id=<uuid>`；
- 若允许 `version_name`，服务端先唯一解析为 ID；
- 不建议隐式“最新”；如提供，必须显式 `dataset=latest` 且只选择最新 READY dataset。

响应元数据统一：

```json
{
  "meta": {
    "dataset_version_id": "uuid",
    "version_name": "demo-v1",
    "snapshot_date": "2026-08-01",
    "schema_version": "...",
    "page": 1,
    "page_size": 100,
    "total": 123
  },
  "data": []
}
```

### 5.3 分页与排序

- 列表默认 `page=1&page_size=100`；`page_size` 上限在 Phase 1 配置固定。
- 高数据量接口可升级 cursor pagination，但一个 API 版本内不得同时返回不稳定排序。
- 排序字段使用白名单；必须追加稳定 ID 作为最后 tie-breaker。
- 数量在 JSON 中使用十进制定点的字符串或 OpenAPI `number` 的一致策略；Phase 1 必须固定，避免精度漂移。

### 5.4 时间与动态序列

- 日期输出 ISO `YYYY-MM-DD`，时间输出 ISO 8601 带时区。
- API 不使用动态 JSON 属性名表示月份/周次；用数组保持 OpenAPI 稳定。
- Excel 导出再将数组透视成模板的真实月份/第 1～13 周列。

### 5.5 错误格式

```json
{
  "error": {
    "code": "DATASET_NOT_FOUND",
    "message": "Dataset version was not found or is not ready.",
    "details": {}
  }
}
```

建议状态码：400 参数错误、404 dataset/业务对象不存在、409 生成签名冲突或状态冲突、422 业务校验失败、500 未预期错误。错误响应不得包含 SQL、连接信息或 Truth。

## 6. Dataset 与健康检查 API

### `GET /api/v1/datasets`

列出允许查询的 dataset，默认只返回 READY。字段：ID、名称、snapshot、generator/schema 版本、status、generated_at；不返回 generation_config 中的敏感/内部 Scenario 分配。

### `GET /api/v1/datasets/{dataset_version_id}`

查询单个 dataset 元数据和公开统计；不返回 Truth 分布，除非未来管理端另有授权接口。

### `POST /api/v1/datasets/generate`

仅开发/管理权限。输入：version_name、random_seed、snapshot_date、generator_version、schema_version、generation_config。相同 signature 的幂等策略在 Phase 1 固定：建议返回已有 dataset，而不是生成第二套不同 ID 数据。

### `GET /api/v1/health`

进程存活检查，不依赖数据库深查询。

### `GET /api/v1/ready`

检查数据库连接、迁移版本、至少一个 READY dataset（若配置要求）。不得运行耗时全量 Report 查询。

## 7. 六类 Report API

### 7.1 Report 1 — `GET /api/v1/reports/overdue-po`

**目的**：列出项目定义的超期 PO。

建议过滤：`material_code`、`supplier_code`、`buyer_code/name`、`organization_code`、`inventory_organization_type`、`po_number`、`po_status`、`min_overdue_days`、`order_date_from/to`。

排序默认：`overdue_days desc, po_number, po_line_number, shipment_number`。

响应：`DATA_CONTRACT.md` Report 1 字段；一行固定对应 `PO号 + PO行 + 发运号`，`po_line_schedule_id` 为事实 ID，可附父级 `po_line_id`、`material_id`、`po_reference_project_id`。`overdue_open_qty=greatest(schedule_qty-schedule_received_qty,0)`。禁止原因、EOL、根因项目、责任路径、期望对策。

### 7.2 Report 2 — `GET /api/v1/reports/supply-demand/{material_code}`

**目的**：查询物料当前供需、项目集合与 MPM。

建议参数：`organization_code`（可选，仅校验/过滤该 Material 的 Primary Inventory Organization）、`include_components=true|false`。V1 响应保持每 Material 一条，不按组织拆行。

响应核心：

```json
{
  "material_id": "uuid",
  "material_code": "...",
  "all_supply_qty": "...",
  "actual_demand_total_qty": "...",
  "supply_demand_surplus_qty": "...",
  "organization_active_projects": [{"project_id": "uuid", "project_name": "..."}],
  "enterprise_active_projects": [],
  "mpm": {"employee_id": "uuid", "code": "...", "name": "...", "department": "..."},
  "components": []
}
```

模板的 106 个展示字段均由合同覆盖；是否默认返回全部辅助字段可通过 `fields=core|all` 控制，但 Excel 导出必须还原全部模板字段。根因分析只依赖三个数量核心字段；其他供需汇总和“多余”字段均为辅助展示，其 Mock 公式延后至 Generator 阶段。

### 7.3 Report 3 — `GET /api/v1/reports/forecast-history/{material_code}`

**目的**：返回物料-项目历史 Forecast Version 与月预测。

参数：

- `anchor_date`（可选；通常由调用方传 `order_date+LT`）；
- `project_id` 或 `project_code`；
- `version_from/to`；
- `window=default`（Baseline + 后 3 版）或显式 `after_versions=2..5`。

响应采用稳定数组：

```json
{
  "material_id": "uuid",
  "projects": [
    {
      "project_id": "uuid",
      "project_name": "...",
      "versions": [
        {
          "forecast_version_id": "uuid",
          "version_name": "...",
          "version_date": "2026-01-05",
          "window_role": "BASELINE",
          "months": [{"forecast_month": "2026-01-01", "forecast_qty": "10"}],
          "forecast_total_qty": "...",
          "cumulative_shipped_qty": "..."
        }
      ]
    }
  ]
}
```

`window_role` 是查询选择标记，不是根因答案；可以返回。不得返回 REDUCTION/DELAY/MIXED 的预判标签或 `causal_project_id`。

V1 Forecast Version 默认每周一版。窗口选择必须先按日期过滤 `is_valid=true` 并取最大 `sequence_no` 作为该日最终版本，再取 Anchor 前最近 Baseline 和 Anchor 后 2～5 个版本。`cumulative_shipped_qty` 按 Material × Project 从 dataset 历史起点累计至该版本日期。

### 7.4 Report 4 — `GET /api/v1/reports/forecast-13w/{material_code}`

**目的**：返回最新 13 周物料需求。

参数：`organization_code`（可选 Primary Inventory Organization 校验/过滤）、`snapshot_id`（默认 dataset 最新有效 weekly snapshot）。V1 每 Material 一行。

响应：模板主数据/供应辅助字段，加：

```json
{
  "snapshot_date": "2026-08-01",
  "weeks": [
    {"week_index": 1, "week_start_date": "2026-08-03", "forecast_qty": "12"}
  ],
  "thirteen_week_demand_qty": "...",
  "weekly_average_demand_qty": "..."
}
```

`week_index=1` 使用 Monday-start：snapshot 为星期一时从 snapshot 开始，否则从其后最近星期一开始，后续每 7 天一个桶。`top_project` 为该最新 13 周内 Material 各 Project 需求贡献最大的 Project。模板“供应商”返回 `supplier_code`，“供应商(英文)”返回 `supplier_name_en`。

预计消耗月数不属于源 Report 4。未来若建立 Analytics endpoint，必须同时输入 `po_line_schedule_id` 或显式 `overdue_open_qty`，并对零需求返回 null + `NO_FORECAST_DEMAND`。

### 7.5 Report 5 — `GET /api/v1/reports/product-config/{project_code}`

**目的**：按稳定项目查询 snapshot 时有效产品配置、组织与生命周期。

参数：`as_of_date` 默认 dataset snapshot；不得超出 dataset 可表达历史范围而静默回退。

响应包含 `project_id`、该 Project 的多个 Product Config、每个 Config 的 Material 列表、模板全部字段和规范化 `lifecycle_stage`。每个 Product Config 在 V1 只属于一个 Project；Project 可以有多个 Config，Config 可以有多个 Material。生命周期来自项目级 `project_lifecycle_history`，受控值至少为 `NPI/MASS_PRODUCTION/EOL`；After-sales 不是 lifecycle。`is_eol` 若返回，只能由 `lifecycle_stage=EOL` 派生，而不是 Truth。

### 7.6 Report 6 — `GET /api/v1/reports/stockpile/{material_code}`

**目的**：按历史时点查询囤料版本及记录。

必需参数之一：`as_of_date`、`po_line_schedule_id` 或 `po_line_id`。优先使用 schedule ID；服务端从同 dataset PO Line 读取 `order_date`。同时传入的日期/ID 若不一致则返回 422。

响应：

```json
{
  "as_of_date": "2024-05-12",
  "matched_version": {
    "stockpile_version_id": "uuid",
    "version_name": "...",
    "version_date": "2024-05-06"
  },
  "stockpile_record_found": true,
  "record": {
    "material_id": "uuid",
    "material_code": "...",
    "future_months": [],
    "balance_projections": [],
    "inventory_age_buckets": []
  }
}
```

`stockpile_record_found` 是基于普通历史记录的可验证查询结果，不是 Ground Truth 泄漏。若没有任何历史有效版本，需区分 `matched_version=null` 与“版本存在但物料未命中”。

`future_months` 从 `stockpile_version_date` 所在自然月的下一自然月开始，连续 6 个月。库龄 buckets 使用累计超过 30/60/90/120/150/180/270/365 天语义。金额、GAP、完成率、结余和预警只作辅助模拟，不参与根因判断，其 Mock 公式延后至 Generator 阶段。

## 8. Excel 导出规划

可选未来接口：

```text
GET /api/v1/exports/reports/{report_name}.xlsx?dataset_version_id=...
```

- 导出只使用公开 Report Service，不直接查询 `evaluation`。
- 列名、顺序、多级表头必须还原最终模板。
- Report 3 月标题使用真实 YYYYMM，M0～M+6 共 7 月。
- Report 4 显示第 1～13 周，并提供实际周起始日。
- Report 6 动态显示未来 6 月及模板的结余/库龄多级表头。
- 空数量按合同输出 0；辅助文本按 Nullable 规则留空。

## 9. Ground Truth 隔离门禁

### 数据库

- `system_a_api` 对 `evaluation` 无 USAGE/SELECT。
- 公开 View 依赖树不得引用 evaluation Schema。
- 数据库迁移分别管理 grants，测试每次验证。

### 代码

- 公开 Pydantic/OpenAPI Schema 禁止导入 evaluation models。
- `app/evaluation` 不注册 router。
- API 响应序列化采用字段白名单，不对 ORM 对象做无约束 dump。

### 测试与发布

- 扫描 OpenAPI JSON、API 示例、Excel 表头和响应 keys。
- 禁止字段至少包括 `true_cause`、`true_cause_subtype`、`causal_project_id`、`demand_change_type`、`responsibility_type`、`expected_action` 及同义中文字段。
- 任何 test-only truth 调试接口默认不设计；若未来确需，必须独立进程/配置、独立角色、默认关闭且不进入生产 OpenAPI。

## 10. 可观测性与审计

未来服务日志应记录：request_id、dataset_version_id、endpoint、过滤器摘要、耗时、行数；不得记录完整大响应、数据库凭证或 Truth。生成任务记录 signature、阶段、行数、内容哈希与失败原因。

建议指标：

- dataset generation duration / failed stage；
- Report query latency / returned rows；
- Forecast lineage validation failures；
- API leakage test status；
- READY dataset count。

## 11. 缓存策略

READY dataset 内容不可变，可使用 `(dataset_version_id, endpoint, normalized_query)` 作为缓存键。生成中/失败 dataset 不缓存。切换“latest”必须先解析具体 dataset ID，再生成缓存键，避免跨版本污染。

## 12. 安全与输入约束

- 查询过滤、排序、字段选择全部白名单化。
- 业务编码不拼接 SQL；Repository 使用参数化查询。
- 管理生成接口与普通查询接口分权。
- 生成规模、page_size、导出行数设上限，防止资源耗尽。
- 不通过错误信息暴露表名、SQL 或 evaluation Schema。

## 13. Phase 1 建议的最小架构交付

Phase 1 只建立可运行骨架：

1. 项目目录、配置与依赖锁定；
2. PostgreSQL 连接、角色/grant 基线；
3. SQLAlchemy Base 与 `dataset_versions` 及主数据骨架；
4. Alembic 初始化和首个迁移；
5. FastAPI `/health`、`/ready`；
6. pytest 数据库夹具、迁移 smoke test、权限 smoke test；
7. 不实现 Scenario、PO、Demand/Forecast、Report Views 或六类业务 endpoint。

## 14. API 决议状态

Phase 1 已无业务阻塞项。Report 1 粒度、Report 2/4 组织粒度、周历、Forecast 版本选择、Product Config/Lifecycle、Report 6 未来月和累计库龄语义均已固化。

以下仅影响后续 Generator/业务 API 完成度，不阻塞 Phase 1：Report 2 辅助字段 Mock 公式（`DC-03`）、KD 完整释义（`DC-07`）、Report 6 辅助字段 Mock 公式（`DC-12`）。量化阈值默认 Mock 参数（`DC-15`）已在 Phase 4 标记为 `RESOLVED_AS_SYNTHETIC_CONFIG`，通过 `ScenarioGenerationConfig` 配置并进入 Scenario signature，不代表企业真实规则。售后正式处置（`DC-16`）仍为 `NEEDS_BUSINESS_CONFIRMATION`，不得自行写入正式 `expected_action`。

## 15. Phase 5A 模块落地边界

`EvidenceFoundationGenerationService` 是 generator-only 事务入口，要求 Dataset 为 GENERATING，并只读验证完整 Master/Procurement/Scenario。`app/generators/evidence_foundation` 提供配置、日历、Generator、Validator、数量 as-of 投影与 CLI；公共 `services/__init__.py` 不导入该入口，公共应用不会加载 Evaluation 或 Generator。

输出为项目 Lifecycle、Product Config/Material 关联及一个共享 Demand World（初始日点 + 中性源修订长表）。服务保留明确事务边界，不修改既有 Truth，不写最终 Dataset hash，不将状态升级为 READY。只允许 generator 写入新 raw tables；API 继续仅访问原有健康/就绪所需白名单。未新增 Report endpoint、Forecast Version 或任何诊断接口。

Phase 5A.1 的 `EvidenceTimingCorrectionService` 只供显式 generator CLI 使用：锁定名为 `demo-master-v1` 的 GENERATING dataset，校验调用方提供的旧 hash、前置世界、保留实体 ID 与未变更的 Lifecycle/Config。仅更新变更日点和源 lineage，替换该 dataset 源修订；写入后重新验 hash 和上游内容，不触碰最终 Dataset hash。异常整体回滚、再次执行完整同 hash 则复用；其他名称、READY、错误旧 hash、已有 Forecast/Stockpile schema 均拒绝。无公开 reset endpoint。

## 16. Phase 5B 模块边界

`app/domain/forecasts.py` 是无数据库/Generator/Evaluation 依赖的纯查询计算器：Anchor、每日有效最终版、`ForecastWindowSelector`、13周合计/周均、最多项目与截至版本日累计发货。Selector 构造时注入共享版本集合，查询输入 dataset ID、Anchor、后版本数量，输出 baseline/post_versions/ordered_window；缺失完整窗口显式失败，无诊断返回值。

`app/generators/forecasts` 提供配置、日历/源聚合 Generator、独立 Validator、世界 hash 与 CLI；`ForecastGenerationService` 是 generator-only 事务入口。只读逐一核验完整 Master/Procurement/Scenario/Evidence，任何缺失或 hash 不符均失败；六张 Forecast 表全空才生成、完整同配置校验复用、部分存在拒绝，配置冲突不覆写。失败整阶段回滚，不写最终 Dataset hash、不升级 READY。

Phase 5B 兼容修复：旧 Evidence correction 的下游保护调整为“该 dataset 已有 Forecast/Stockpile facts”即拒绝；允许空009 schema 下的隔离修复测试，但有真实下游数据时不能使其失效。其他 dataset 的下游数据不影响本 dataset 的隔离门禁。

公开应用不导入上述 Generator/Truth；本阶段无 Report route/View/导出接口，也无 reset API。Forecast history and 13-week demand are two views of the same synthetic demand world.
