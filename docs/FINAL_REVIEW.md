# System A Final Review — 2026-08-30

Synthetic data only. 本轮以 `a968492`（Phase 6B）为起点，初始 working tree clean。
只做公开仓库审查、文档整理和经实际复现确认的最小缺陷修复；没有开发 System B。
Report 6 修复独立提交为 `395435f`：`fix: keep stockpile API within reporting permissions`。

## Findings and disposition

| ID | Finding | Disposition |
|---|---|---|
| FR-01 | Report 6 API 直接 JOIN `platform.materials`；真实 API 角色无权读取，返回 500。既有 API 测试把连接替换成 owner，漏掉该路径。 | 已改为 JOIN 现有 `reporting.report6_stockpile_detail`，关联键仍是 dataset/material ID。未增加 raw-table 权限、未新增 View/migration。新增六条真实角色 HTTP 回归，与 owner 输出比较。 |
| FR-02 | README 的公开 npm 安装路径不能复现 Excel：公共 registry 返回 404，工作区 `@oai/artifact-tool` metadata 为 private，版本 2.8.52；仓库依赖仍为 `*`。 | 仍阻塞完整公开复现。文档明确获授权运行时前提；没有复制私有包、替换 exporter 或私自决定分发/许可。 |
| FR-03 | README 混杂旧阶段“未实现/GENERATING”等描述，export 命令切回根目录却运行 backend 模块，测试连接设置与数据库角色步骤不完整。 | 已重组 README，新增 LOCAL_SETUP.md，区分当前状态、历史证据与运行时前提。 |
| FR-04 | frontend Dockerfile 使用 `COPY . .`，无 `.dockerignore`；backend context 未屏蔽 env variants/node_modules。Git 缺少常见备份/临时产物规则。 | 补齐 ignore 规则，没有删除任何文件或现有数据。 |
| FR-05 | 仓库没有 LICENSE。 | `LICENSE_MISSING`，由维护者决定；本轮不选择 MIT 或其他许可证。 |

## Verification evidence

- 修复前新增真实 API 角色测试：5 passed / 1 failed（仅 stockpile 500），证明回归能捕获缺陷。
- 修复后执行 `test_report_api.py`、`test_report_semantic_integration.py`、
  `test_scenario_leakage.py`、`test_repository_hygiene.py`：**33 passed / 0 failed / 0 skipped**，
  62.51 秒，1 条既有 Starlette/httpx 弃用警告。
- 该 targeted 运行在专用测试库完成 `downgrade base → upgrade head` 与相关夹具生成，
  不是对开发库的重建。历史 migrations 001～011 无 diff。
- 另以实际开发配置的 `system_a_api` 登录：Dataset 列表和六个 Report 路由均 200；
  Report 6 当前版本日期 2026-08-26，未来 6 个月数组存在。
  raw materials 与 `evaluation.scenario_truth` SELECT 均被 SQLSTATE 42501 拒绝。
- `/health`、`/ready` 均 200；OpenAPI 10 个版本化路径，隐藏答案关键词命中为 0。
- 开发 Dataset 仍为 READY，business hash 仍为
  `f91717e3af70a518caf31673fd5f733f1e12b2dfb9598b1e7c0cec20c36ac199`。
  本轮没有重建或改写开发 Dataset、Master、Procurement、Truth 或 Forecast。
- 两个 Compose 配置均通过 `config --quiet`；已有 PostgreSQL 容器 healthy。
  根目录三服务 Compose 只是早期骨架，没有完整传递 API DB URL；推荐 dev Compose + host Python。
- 本轮没有重新生成 Excel、没有在全新机器上安装整个工具链、没有重跑完整 439 项测试。
  **439 passed / 0 failed / 0 skipped** 是 Phase 6B 的历史全量记录，不与 targeted 数量相加。

## Privacy and repository safety

初始 223 个 tracked files、270 个历史 blob 检查未发现已知本地密码、常见 token/private-key
格式、用户绝对路径或历史跟踪的 `.env`。对全部 tracked 文本补充禁止词扫描（仅规则列表自身
作为规则数据排除），README/docs/examples/tests/migrations/comments/source fixtures 均未发现命中。
标准 `check_forbidden_terms.py` 和 repository hygiene 亦通过。

合成来源抽查包括 `MAT-`、`SUP-`、`CUS-`、`PRJ-`、`PO-` 编码生成与中性名称池。
公开 examples 为带 Synthetic notice 的小型聚合记录，没有逐条隐藏答案。
这是一组范围明确的规则检查和来源审查，不是对未知企业名/所有可能密钥的绝对保证。

`.env.example` 仅包含占位密码；`.env`、exports、raw/synthetic 运行数据、venv、node_modules、
缓存、日志、Docker 本地数据目录、备份、临时 Excel 均不提交。
当前工作区产物无强制加入 Git。Docker named volume 不属于 repository tree。
对开发期间曾出现在本地诊断输出中的凭据，仍建议维护者轮换；未在仓库或历史扫描中发现该值。
Git 作者身份属于维护者有意配置的提交 metadata，不将其误判为业务数据泄漏。

## Public inventory

| Keep public | Keep local / ignored |
|---|---|
| backend source、11 migrations、bootstrap SQL、tests | `.env`、真实连接凭据、日志 |
| Manifest、field mapping、contracts、architecture、runbook | 原始企业资料、数据库 dump/volume、维护备份 |
| 小型 Synthetic aggregate examples | 生成 Excel、raw/synthetic 全量事实文件 |
| requirements、safe env example、Compose/Dockerfiles、ignore rules | venv、node_modules、pytest/Next.js 缓存 |
| frontend/agent 占位，README 明确未实现业务 | IDE 临时文件 |

保留必要工程文件；没有删除历史 migration、测试、模板契约、维护脚本或占位模块。
没有创建 GitHub remote、push、tag 或选择许可证。

本轮修改文件：

- `README.md`
- `docs/LOCAL_SETUP.md`（新增）
- `docs/FINAL_REVIEW.md`（新增）
- `.gitignore`
- `backend/.dockerignore`
- `frontend/.dockerignore`（新增）
- `backend/app/services/report_queries.py`
- `backend/tests/test_report_api.py`

## Publication decision

System A 的已实现功能 checkpoint 保留；FR-01 修复后真实角色六报表可读。
但不能将 `a968492` 原样宣称为已通过此次真实角色审查的 stable release。
`system-a-v1.0` 可作为后续 tag 名称，建议在修复提交与公开 Excel 依赖方案确定后再创建。

推荐 repository：`overdue-po-copilot`。
推荐 description：Synthetic procurement data platform and AI-ready overdue PO decision-support system.
推荐 topics：`procurement`、`supply-chain`、`fastapi`、`postgresql`、`sqlalchemy`、
`alembic`、`synthetic-data`、`data-engineering`。
LangGraph/AI Agent 暂仅是路线图，不把它们描述为已实现技术。

**SYSTEM A: COMPLETE（含本轮 FR-01 最小修复）**

**SYSTEM A GITHUB PORTFOLIO READINESS: NOT READY**

技术阻塞为 Excel 私有依赖的公开获取、版本锁定与从空环境完整复现；
另有 `LICENSE_MISSING` 待维护者决定（非数据库/API 运行阻塞）。
文档与源代码可以被审阅，但暂不声称 clone 后即可完整跑通六张 Excel。

**SYSTEM B: NOT STARTED**
