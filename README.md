# Overdue PO Copilot — System A

本仓库已完成 Phase 5A.1、Phase 5B、Phase 5C、Phase 6A 与 Phase 6B。System A 现在提供六张报表只读 API、统一 Manifest 驱动的 Excel 导出，以及 Dataset finalization（GENERATING → READY）。

## Implementation Status

- [x] Phase 0 / 0.1：业务规格固化与纠偏
- [x] Phase 1：PostgreSQL、SQLAlchemy、Alembic、FastAPI 基础骨架
- [x] Phase 1.1：真实 PostgreSQL 在线验收与仓库基础卫生
- [x] Phase 2：确定性主数据世界、关系、校验与演示数据集
- [x] Phase 3：PO Header、PO Line、PO Shipment / Schedule 采购事实世界
- [x] Phase 4：Scenario Planning 与隔离 Evaluation Truth
- [x] Phase 5A — Evidence Foundation
- [x] Phase 5B — Forecast Evidence World
- [x] Phase 5C — Supply/Demand & Stockpile Evidence
- [x] Phase 6A — Six Report Semantic Layer
- [x] Phase 6B — Report APIs / Excel / Finalization
- [ ] Phase 7：Copilot

当前已包含：

- PostgreSQL `platform` / `evaluation` schema 迁移；
- dataset 与核心主数据 SQLAlchemy 2.x 模型；
- Material ↔ Project、Material → MPM，以及供应商、客户、员工角色与物料责任关系；
- 基于 seed、snapshot date、版本和配置签名的稳定 UUID 与确定性主数据生成；
- 单事务 Dataset 生成服务、内存业务校验器、CLI 与演示摘要；
- 数据库角色与权限 bootstrap SQL；
- `GET /api/v1/health` 与 `GET /api/v1/ready`；
- unit tests 与真实 PostgreSQL integration tests。

当前已实现 Master Data、Procurement、隔离 Scenario Truth、Lifecycle/Product Config、共享需求、Forecast、Operational facts、六张 canonical Report Semantics、Report REST API、Manifest 驱动 Excel 与 Dataset finalization；Agent 与 AI 诊断属于 System B。

所有生成内容均为合成演示数据，不来源于真实企业数据，也不得用于真实企业运营。

### Architecture Snapshot

```text
Generation Config
      ↓
Dataset Version (GENERATING)
      ↓
Synthetic Enterprise World
      ↓
Master Data
├─ Organizations / Employees
├─ Customers / Suppliers
├─ Projects / Materials
└─ Effective-dated Relationships
      ↓
Procurement World
├─ PO Header
├─ PO Line
└─ PO Shipment / Schedule
      ↓
Scenario Plan (evaluation-only)
      ↓
Lifecycle + Product Config
      ↓
Underlying Demand Signal + dated source revisions
      ├─ Forecast Versions → Monthly Project Forecast
      └─ Latest Snapshot → Project 13W → Material 13W
      ↓
Supply-Demand / Stockpile
      ↓
Six Canonical Report Semantics
      ↓
REST API / Excel (next phase)
```

All report-facing demand data will be derived from one shared Underlying Demand Signal.

Report 1 将使用 Shipment / Schedule 级事实，一条 Schedule 对应一条事实行。超期判断是确定性计算，只使用 Dataset 的 `snapshot_date`、`order_date`、主用 Material LT 和固定 240 天，不读取运行机器日期，`due_date` 仅用于运营展示。

Synthetic data is generated cause-first. Hidden scenario plans are created before demand/forecast evidence, preventing independently randomized reports from contradicting one another. 每条隐藏真值仅存于权限隔离的 `evaluation` schema；普通业务 API、OpenAPI 和公开示例不会暴露逐条答案。

## 1. Python 环境

需要 Python 3.11+。Windows PowerShell 示例：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 2. 配置

复制根目录 `.env.example` 为 `.env`，替换所有 `change_me`。应用支持：

- `APP_ENV`、`APP_NAME`、`API_V1_PREFIX`、`LOG_LEVEL`；
- `DATABASE_URL_OWNER`、`DATABASE_URL_API`、`DATABASE_URL_GENERATOR`、`DATABASE_URL_EVALUATOR`。

连接字符串通过 `SecretStr` 管理，不会输出密码。`.env` 已被 Git 忽略。

## 3. PostgreSQL

如果本机已有 PostgreSQL 16，可直接创建开发数据库。若 Docker 可用，可只启动开发数据库：

```powershell
docker compose -f docker-compose.dev.yml up -d postgres
```

以 PostgreSQL 管理员连接目标数据库，依次执行角色脚本；密码必须在仓库外设置：

```powershell
psql -U postgres -d overdue_po_copilot -f backend/db/bootstrap/001_roles.sql
psql -U postgres -d overdue_po_copilot -c "ALTER ROLE system_a_owner PASSWORD '<local-secret>'"
psql -U postgres -d overdue_po_copilot -c "ALTER ROLE system_a_api PASSWORD '<local-secret>'"
psql -U postgres -d overdue_po_copilot -c "ALTER ROLE system_a_generator PASSWORD '<local-secret>'"
psql -U postgres -d overdue_po_copilot -c "ALTER ROLE system_a_evaluator PASSWORD '<local-secret>'"
```

## 4. Alembic

在 `backend/` 下使用 owner 连接执行：

```powershell
alembic -c alembic.ini upgrade head
psql -U system_a_owner -d overdue_po_copilot -f db/bootstrap/002_grants.sql
```

迁移链为：schema/extension → dataset/master/relationships → `006_procurement_facts` → `007_scenario_truth` → `008_evidence_foundation` → `009_forecast_evidence` → `010_operational_evidence` → `011_report_semantic_views`。`alembic downgrade base` 会按依赖逆序删除对象；共享的 `btree_gist` extension 不会在 downgrade 时删除。重建 Schema 后必须重放grants脚本；测试夹具已自动执行。

## 5. Phase 2 主数据生成

在仓库根目录执行一行 PowerShell 命令：

```powershell
cd backend; .\.venv\Scripts\python.exe -m app.generators.master_data.cli --seed 20260826 --snapshot-date 2026-08-26 --version-name demo-master-v1 --summary-output ..\examples\master_world_summary.json
```

CLI 使用 `DATABASE_URL_GENERATOR`，不会显示数据库密码。同一完整生成配置会得到相同 `generation_signature`、稳定实体 UUID 和相同 `master_content_hash`；同一 `GENERATING` 数据集可安全复用，不会重复写入。

Phase 2 完成后 Dataset 仍保持 `GENERATING`，且 `business_content_hash` 为 `null`。这是有意设计：主数据只完成了 Synthetic Enterprise World 的第一层，只有后续业务事实、Forecast、Stockpile 等全部生成并通过最终校验后，才允许将 Dataset 发布为 `READY`。

## 6. Phase 3 Procurement World

先完成 Phase 2 Demo Master World，再在同一个 `GENERATING` Dataset 上执行：

```powershell
cd backend; .\.venv\Scripts\python.exe -m app.generators.procurement.cli --dataset-version-name demo-master-v1 --seed 20260827 --summary-output ..\examples\procurement_world_summary.json
```

默认生成100个 Synthetic PO Header，每个1～3行，V1 每行默认生成一个 Shipment；数据库 Schema 仍允许一个 PO Line 拥有多个 Shipment。生成器只引用同 Dataset 已存在的主数据和有效供应商、项目、采购员关系，不生成或保存任何根因答案。

Phase 3 后 Dataset 继续保持 `GENERATING` 且最终 `business_content_hash` 仍为空，因为 Demand、Forecast、Lifecycle、Stockpile 和 Reports 尚未完成。

## 7. Phase 4 Hidden Scenario Planning

在同一个已完成 Procurement World 的 `GENERATING` Dataset 上执行：

```powershell
cd backend; .\.venv\Scripts\python.exe -m app.generators.scenarios.cli --dataset-version-name demo-master-v1 --seed 20260828 --summary-output ..\examples\scenario_world_summary.json
```

Planner 只为严格满足超期公式的 Schedule 创建隐藏 Truth，并优先按 Material 共享 Scenario Plan。公开摘要只包含聚合 Synthetic Generator 统计；逐条 Evaluation Truth 始终隔离在 `evaluation` schema。Phase 4 不生成 Demand、Forecast、Lifecycle 或 Stockpile 证据，Dataset 继续保持 `GENERATING`。

## 8. Phase 5A Evidence Foundation

先完成原 Demo 的 Master、Procurement 和 Scenario；在仓库根目录执行：

```powershell
cd backend; .\.venv\Scripts\python.exe -m app.generators.evidence_foundation.cli --dataset-version-name demo-master-v1 --seed 20260829 --summary-output ..\examples\evidence_foundation_summary.json
```

`--config` 支持 Evidence JSON 配置；上游非默认世界必须另外传入原始 `--procurement-config` / `--scenario-config`。服务只读校验完整前置世界，禁止静默补齐。所有 Evidence 在同一事务中落库；完整且同配置则复用，部分存在直接报错。仅输出聚合统计，不输出逐条 Truth。

六张基础表为项目生命周期、产品配置及关联、日需求 Signal/Point，以及中性的 `demand_signal_revisions`。最后一张保存企业需求源“在哪天修订哪个需求日的数量”，不是 Forecast Version。后续月/周报表必须按同一 as-of 源序列聚合，不能各自随机造数。

Demo：70 条生命周期（snapshot：NPI 4 / MASS_PRODUCTION 12 / EOL 14），60 个配置、272 条 Config-Material 关系、136 条 Signal、110840 个日点、130415 条持续状态日修订。需求窗口为 2025-02-01～2027-04-26，由 Dataset/PO 时间计算，并非硬编码窗口。Dataset 仍为 `GENERATING`，最终 `business_content_hash` 保持 null。

Phase 5A.1 消除临时预算恢复脉冲；source state 在 Anchor 当日生效并持续至下一事件。多 Anchor 联合构造非负数量状态，再按原 seeded 日权重分配；不依赖特定发布星期，不放宽 Scenario 阈值。构造器固定 NumPy/SciPy 版本，采用 [SciPy HiGHS 线性约束求解](https://docs.scipy.org/doc/scipy-1.15.3/reference/optimize.linprog-highs.html)，只在 Generator 中使用，不是运行时诊断引擎。

针对已审计的旧 demo，显式修复命令（不可用于 READY 或已有下游 Forecast/Stockpile 的世界）：

```powershell
python -m app.generators.evidence_foundation.correct_timing --expected-old-hash 762381c2296e7c684b3698bc669ed353f55bdb342edf8157fa4b96678d28c8a3 --summary-output ../examples/evidence_foundation_summary.json
```

该操作只修改受影响 Evidence，并保留 Master、Procurement、Truth、Lifecycle/Config 和既有实体 ID。无公开 reset API。新 Evidence hash：`d2ee070ef425915488b5281b244a234a24be0a9890598a2b2d48de1400cc868e`。

## 9. FastAPI

```powershell
cd backend
uvicorn app.main:app --reload
```

检查：

```powershell
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/ready
```

`/health` 仅检查进程存活。`/ready` 检查数据库连接和当前 Alembic revision 是否等于 head；Phase 4 不要求存在 READY dataset。
根路径 `/health`、`/ready` 与上述版本化健康接口均可使用；根路径兼容入口不加入 OpenAPI。

## 10. 测试

纯 unit tests 无需 PostgreSQL：

```powershell
cd backend
python -m pytest -m "not integration"
```

真实 PostgreSQL integration tests 只允许指向数据库名包含 `test` 的一次性数据库：

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://system_a_owner:<secret>@localhost:5432/overdue_po_copilot_test"
$env:TEST_DATABASE_ADMIN_URL = "postgresql+psycopg://postgres:<secret>@localhost:5432/overdue_po_copilot_test"
python -m pytest
```

Integration fixture 会先执行 `alembic downgrade base` 再执行 `upgrade head`，不得指向共享或生产数据库。

Phase 5A 全量验收：153 passed / 0 failed / 0 skipped。正式 Forecast 版本比较留待 Phase 5B；Source revision foundation 已验证 Reduction/Delay/Mixed、售后持续性及 EOL 负证据。

Phase 5A.1 修复后全量：191 passed / 0 failed / 0 skipped；12075 次多发布日历比较全部通过。测试库完成 `008 → base → 008`，历史迁移不变；正式 Forecast 表与选择服务仍待 Phase 5B。

Phase 5B：完整回归262项通过；全量启动后新增的1项“缺少 Demand 禁止随机回退”测试另外执行通过，当前263项均已验证，0 failed / 0 skipped。测试库完成 `009 → base → 009`，1条既有 Starlette/httpx 弃用警告。

禁止词扫描：

```powershell
python scripts/check_forbidden_terms.py
```

## 11. Phase 6B 报表交付

六张报表 API 均位于 `/api/v1/reports/`，支持 `dataset_version_id` 或
`dataset_version_name`、分页及白名单筛选；未指定 Dataset 时只选择最新 READY
版本。Dataset 元数据位于 `/api/v1/datasets`。公开 API、Schema 与 OpenAPI
不包含 `evaluation.scenario_truth` 或隐藏场景答案。

Excel 导出只消费 canonical reporting views，并以
`backend/app/reporting/report_header_manifest.json` 固化列序。需要 Node.js 与
`@oai/artifact-tool` 运行时；在标准 Node 环境中可执行：

```powershell
cd backend/app/reporting
npm install --omit=dev
cd ../../..
python -m app.reporting.export_cli --dataset-version-name demo-master-v1 --report all --output-dir exports
```

若使用 Codex 工作区提供的 Node 运行时，可设置 `REPORT_EXPORT_NODE` 与
`REPORT_EXPORT_NODE_MODULES` 后运行同一命令。导出文件默认写入 `exports/`，不纳入
Git。`python -m app.finalization.cli --dataset-version-name demo-master-v1` 会在
所有平台事实、Scenario Truth、六张 canonical views 和一致性校验通过后计算
`business_content_hash` 并原子发布 Dataset；READY Dataset 只能被幂等重验，不能再由
Generator 改写。

Phase 6B 的完整验收包括：clean database downgrade/upgrade、从空库完整生成、六张
API 与精确表头 Excel round-trip、READY 不可变性、角色权限隔离、OpenAPI/敏感词扫描、
`/health` 与 `/ready` 200，以及全量 pytest 0 failed/0 skipped。

## 12. 后端基础镜像

`backend/Dockerfile` 是已验证可构建的 Phase 1 FastAPI 基础镜像；开发用
`docker-compose.dev.yml` 仍只启动 PostgreSQL。它不表示 Generator、Report API
或后续 Copilot 已实现。

在仓库根目录构建：

```powershell
docker build -f backend/Dockerfile -t overdue-po-system-a:phase1 backend
```

运行 API 容器时必须通过环境变量提供可从容器访问的 `DATABASE_URL_API`；
不得把数据库密码写入 Dockerfile 或提交到仓库。

## 12. Phase 5B Forecast Evidence World

Pre-Phase5B checkpoint（独立5A.1修复）：`1e38a4b2f79771d1affd581647a0569d292c4655`。新增 migration `009_forecast_evidence`；不修改001～008。

```powershell
cd backend
python -m app.generators.forecasts.cli --dataset-version-name demo-master-v1 --seed 20260830 --summary-output ../examples/forecast_world_summary.json
```

可使用 `--config`、`--evidence-config`、`--procurement-config`、`--scenario-config` 传入原始阶段配置。只能在完整前置世界和 GENERATING dataset 上执行；完整同配置复用，部分存在拒绝，错误整阶段回滚。最终 Dataset hash 仍为 null。

Forecast history and 13-week demand are two views of the same synthetic demand world.

```text
Underlying Demand Signal
        ↓
Forecast Versions
        ├─ Monthly Project Forecast
        └─ Latest 13W Forecast (Project → Material)
```

`SYNTHETIC_PLANNING` 是 synthetic source-domain label，不是真实企业系统名。月长表含用于共同月份比较的前2月/后1月重叠事实；Report 3 展示仍限定版本月 M0～M+6，不增加 Excel 列。项目发货是独立履约事实，不使用 PO receipt 冒充。

Demo：102版本（82有效、20无效；20条同日附加版本），135320月事实，11152项目发货，1个最新周快照，1768项目周行、780物料周行。版本日期2025-02-03～2026-08-24；13周起始日2026-08-31～2026-11-23，覆盖至2026-11-29；9个物料13周全零。正常 CLI 重跑 hash 一致：`fe1d2700018ba9dfa31180123fa3c51c4e9dede0f0218224581b8aafd87ebec9`。

已完成底层 Forecast 与 Operational Evidence facts、选择器与查询计算器。Report 3/4/6 final Views、Report API、Excel Export、Diagnosis、Agent、LLM 均未实现。

## 13. Phase 5C Operational Evidence World

Pre-Phase5C checkpoint：`907e26e9b54995aca87657661c73ce6dca49930b`。新增 `010_operational_evidence` 九表；历史001～009保持不变。

```text
Procurement + Inventory + Demand
        ↓
Current Supply/Demand Context

Scenario Plan
        ↓
Historical Stockpile Evidence
```

Supply-demand is context, not a root-cause decision gate.

```powershell
cd backend
python -m app.generators.operational_evidence.cli --dataset-version-name demo-master-v1 --seed 20260831 --summary-output ../examples/operational_evidence_summary.json
```

支持 `--config`、`--evidence-config`、`--forecast-config`、`--procurement-config`、`--scenario-config`。默认 Operational generator 为5C.2.0，schema为010，数量保留四位小数。全空才生成，完整且同配置才复用，部分世界、损坏上游、配置冲突与READY均拒绝；失败整体回滚。

Supply以Schedule open量与当前库存为来源；试产数量按真实来源组织汇总，不固定为0。Stockpile六自然月预测聚合全部Material-Project有效日需求修订，并记录完整lineage；月结余连续，允许净缺口为负。历史命中使用order_date，不以当前囤料状态替代。

Demo：60 Inventory Snapshots、60 Supply-Demand Snapshots；330 Supply Components、408 Demand Components；盈余正/零/负物料为44/0/16。88个Stockpile Versions、2469条Records、14814条Forecast与14814条Balance Projection；版本日期2025-02-01～2026-09-02。历史查询74命中/41未命中。公开摘要仅包含聚合值，不输出逐条Truth。

本次获授权纠正未提交草稿：旧九表数据已备份并校验，受控事务只重建Operational九表；Master、Procurement、Scenario Truth、Evidence、Forecast和Dataset元数据逐表指纹不变。备份位于Git忽略的 `data/synthetic/phase5c_before_correction`，不是可发布数据。私有维护工具以 `python -m scripts.phase5c_maintenance` 从backend运行，不提供公开reset。

新增91项测试；最终单次全量结果为354 passed / 0 failed / 0 skipped（425.57秒，1条既有依赖弃用警告）。真实测试库完成010→base→010；API不能读取Operational raw tables或Truth，generator/evaluator权限验证通过。四个健康端点HTTP200，在线OpenAPI、公共代码与示例防泄漏检查通过。

正常generator角色CLI重复调用得到相同 `operational_content_hash=a2cd88c8de00b9c659ce4c781a953e9e037fa3cf7d2de76e8c348c0bedd37e9f`。Dataset仍为GENERATING，最终business_content_hash=null；上游Evidence与Forecast hash不变。DC-03/DC-12最终展示映射留Phase6，DC-16售后正式处置及KD完整释义继续待确认；不新增本阶段业务阻塞。

未实现Final Report Views、Report APIs、Excel Export、Diagnosis、Decision Engine、Agent或LLM。

## 14. Phase 6A Six Report Semantic Layer

新增 `reporting` schema与`011_report_semantic_views`。六个canonical sources严格从normalized platform facts派生；Report3/4/6另有normalized long views。精确展示列序取自六个“最终模板”，由 `backend/app/reporting/report_header_manifest.json` 单点维护；`docs/REPORT_HEADER_MANIFEST.md` 与 `docs/REPORT_FIELD_MAPPING.md` 是生成投影。

Report 1严格按Schedule粒度和`overdue_days > 0`；Report 2核心供需与component facts对账；Report3使用daily-final-valid及严格Anchor窗口；Report4为每Material完整13周并保留零需求行；Report5按snapshot取项目生命周期；Report6 current版本严格不晚于dataset snapshot，历史as-of仍以PO order_date查询。跨报表validator验证Material、Project、Forecast、MPM及Report3/4/6共享Demand lineage。

`system_a_api`只新增reporting SELECT，仍不能读取evaluation与restricted raw facts。聚合证据位于`examples/report_semantic_summary.json`；Dataset继续`GENERATING`，没有写最终`business_content_hash`。

本阶段未实现Report REST APIs、Excel Export、Dataset READY finalization、Diagnosis、Decision Engine、Agent或LLM。

Phase6A最终单次全量结果：404 passed / 0 failed / 0 skipped（446.81秒，1条既有依赖弃用警告）。开发库与测试库迁移、四个健康端点、角色权限、OpenAPI泄漏、forbidden-term和repository hygiene均已验证。
