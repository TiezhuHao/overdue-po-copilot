# Overdue PO Copilot — System A

本仓库已完成 Phase 5A，并实施 Phase 5A.1 源计划持续状态修复；正式 Forecast facts 仍属于 Phase 5B。

## Implementation Status

- [x] Phase 0 / 0.1：业务规格固化与纠偏
- [x] Phase 1：PostgreSQL、SQLAlchemy、Alembic、FastAPI 基础骨架
- [x] Phase 1.1：真实 PostgreSQL 在线验收与仓库基础卫生
- [x] Phase 2：确定性主数据世界、关系、校验与演示数据集
- [x] Phase 3：PO Header、PO Line、PO Shipment / Schedule 采购事实世界
- [x] Phase 4：Scenario Planning 与隔离 Evaluation Truth
- [x] Phase 5A — Evidence Foundation
- [ ] Phase 5B — Forecast Evidence World
- [ ] Phase 5C — Supply/Demand & Stockpile Evidence
- [ ] Phase 6：Report Views / API / Excel Export
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

当前已实现 Master Data、Procurement Fact Generator、隐藏 Scenario Planner、Lifecycle/Product Config 与共享日需求证据；尚未实现 Forecast、Supply/Demand、Stockpile、六张 Report、Agent 或 AI 诊断。

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
      ↓
Forecast / Supply-Demand / Stockpile (next phases)
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

迁移链为：schema/extension → dataset_versions → master data → master relationships → master-world auxiliary relationships → `006_procurement_facts` → `007_scenario_truth` → `008_evidence_foundation`。`alembic downgrade base` 会按依赖逆序删除表和两个应用 schema；共享的 `btree_gist` extension 不会在 downgrade 时删除。重建 Schema 后必须重放已有 grants 脚本；测试夹具已自动执行。

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

禁止词扫描：

```powershell
python scripts/check_forbidden_terms.py
```

## 11. 后端基础镜像

`backend/Dockerfile` 是已验证可构建的 Phase 1 FastAPI 基础镜像；开发用
`docker-compose.dev.yml` 仍只启动 PostgreSQL。它不表示 Generator、Report API
或后续 Copilot 已实现。

在仓库根目录构建：

```powershell
docker build -f backend/Dockerfile -t overdue-po-system-a:phase1 backend
```

运行 API 容器时必须通过环境变量提供可从容器访问的 `DATABASE_URL_API`；
不得把数据库密码写入 Dockerfile 或提交到仓库。
