# System A local setup — Windows PowerShell

Synthetic data only. 以下步骤用于新的本地开发环境；不连接真实企业系统。
命令假定默认数据库名 `overdue_po_copilot`、端口 5432，且使用同一 PowerShell 会话。
不要对现有 READY Dataset 重跑生成，不删除数据卷，也不要用测试命令重建开发库。

## 1. Prerequisites and local configuration

需要 Python 3.12、Git、Docker Desktop（PostgreSQL 16 容器）。Excel 另需
[获授权运行时](#excel-runtime)，其私有依赖尚不能由公共 npm registry 安装。
先在仓库根目录检查：

```powershell
python --version
git --version
docker --version
docker compose version
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

用本地编辑器修改 `.env` 中全部 `change_me`，不要把密码写入 README、提交或截图。
`POSTGRES_PASSWORD` 是管理员密码；四个角色各自的数据库 URL 密码须与下方设置一致。
为避免 URL 转义错误，可使用密码管理器生成高强度字母数字密码；特殊字符需 URL encode。
`.env` 及 `.env.*` 默认被忽略，只有安全占位文件 `.env.example` 被跟踪。

```powershell
docker compose -f docker-compose.dev.yml config --quiet
docker compose -f docker-compose.dev.yml up -d --wait postgres
docker compose -f docker-compose.dev.yml ps
```

使用 `docker-compose.dev.yml`，不是根目录早期三服务骨架。
现有卷的数据库密码不会因编辑 `.env` 自动更新，遇到这种情况应核对原配置，不要删卷。
Compose 的数据库端口默认绑定所有接口；只在受信任的本地环境使用，检查防火墙。

## 2. Bootstrap roles and passwords

仍在仓库根目录。容器自带 psql，无需安装 Windows PostgreSQL client。

```powershell
Get-Content -Raw backend/db/bootstrap/001_roles.sql |
    docker compose -f docker-compose.dev.yml exec -T postgres psql -U postgres -d overdue_po_copilot -v ON_ERROR_STOP=1
docker compose -f docker-compose.dev.yml exec postgres psql -U postgres -d overdue_po_copilot
```

进入 psql 后执行以下命令，按提示交互输入各角色密码（不会写入命令历史）：

```text
\password system_a_owner
\password system_a_generator
\password system_a_api
\password system_a_evaluator
\q
```

确认与 `.env` 对应角色的 URL 一致。owner 用于 migration/finalization，generator 用于
数据生成，API 必须使用 `system_a_api`，不得为了绕过权限错误换成 owner。

## 3. Python, migrations and grants

从根目录进入 backend，此后除另有说明都留在 backend。

```powershell
Set-Location backend
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m alembic upgrade head
Get-Content -Raw db/bootstrap/002_grants.sql |
    docker compose --project-directory .. -f ../docker-compose.dev.yml exec -T postgres psql -U system_a_owner -d overdue_po_copilot -v ON_ERROR_STOP=1
& .\.venv\Scripts\python.exe -m alembic current
```

预期 head 为 `011_report_semantic_views`。从 backend 启动时 Settings 自动读取 `../.env`。
已导出的同名环境变量优先于文件；如果连接到错误数据库，检查当前会话是否有旧变量。

## 4. Full demo generation and publication

以下命令适用于新数据库中不存在该 Dataset 的情况。
使用固定 seed/snapshot，不读取机器当前日期。每行成功后再继续下一行。
生成可能需要数分钟；CLI 输出仅为合成记录或聚合摘要，不输出隐藏逐条答案。

```powershell
& .\.venv\Scripts\python.exe -m app.generators.master_data.cli --seed 20260826 --snapshot-date 2026-08-26 --version-name demo-master-v1
& .\.venv\Scripts\python.exe -m app.generators.procurement.cli --dataset-version-name demo-master-v1 --seed 20260827
& .\.venv\Scripts\python.exe -m app.generators.scenarios.cli --dataset-version-name demo-master-v1 --seed 20260828
& .\.venv\Scripts\python.exe -m app.generators.evidence_foundation.cli --dataset-version-name demo-master-v1 --seed 20260829
& .\.venv\Scripts\python.exe -m app.generators.forecasts.cli --dataset-version-name demo-master-v1 --seed 20260830
& .\.venv\Scripts\python.exe -m app.generators.operational_evidence.cli --dataset-version-name demo-master-v1 --seed 20260831
& .\.venv\Scripts\python.exe -m app.finalization.cli --dataset-version-name demo-master-v1
```

最后预期 `status=READY`，final business hash 为
`f91717e3af70a518caf31673fd5f733f1e12b2dfb9598b1e7c0cec20c36ac199`。
这要求同一实现、配置与已验证依赖版本；不同配置不能拿这个 hash 作断言。
不需要再次运行历史 timing-correction 或 maintenance 脚本。
相同完整 GENERATING 阶段可复用；READY 拒绝 Generator 写入，finalization 可幂等重验。

## 5. API startup and query

在 backend 启动：

```powershell
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开 PowerShell 查询（此处不依赖工作目录）：

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/ready
Invoke-RestMethod http://localhost:8000/api/v1/datasets
Invoke-RestMethod "http://localhost:8000/api/v1/reports/overdue-pos?dataset_version_name=demo-master-v1&page_size=2"
Invoke-RestMethod "http://localhost:8000/api/v1/reports/latest-13w-forecast?page_size=2"
```

两种 Dataset selector 不能同时传入。所有报表默认最新 READY；没有 READY 返回 404。
Report 3 API 按月份返回长表行，Report 4 使用固定周槽位，Report 6 包含未来月份与库龄数组。
完整字段/筛选见 `/docs` 与 `/openapi.json`。无公网用户认证，不要对外部署此开发命令。

## Excel runtime

截至 2026-08-30，公共 npm registry 对 `@oai/artifact-tool` 返回 404；本次可用的
工作区包版本为 2.8.52，metadata 标记 `private=true`。仓库 package.json 仍为 `*`，
没有可用于公开安装的 lockfile 或经确认的分发方案。
不能把 `npm install --omit=dev` 当作从空环境复现 Excel 的有效路径，也不要复制或提交私有包。

已经拥有获授权运行时的用户，可在 backend 设置已有路径（交互输入，不硬编码个人路径）：

```powershell
$env:REPORT_EXPORT_NODE = Read-Host 'Existing Node executable path'
$env:REPORT_EXPORT_NODE_MODULES = Read-Host 'Existing authorized node_modules directory'
if (-not (Test-Path -LiteralPath $env:REPORT_EXPORT_NODE)) { throw 'Node executable not found' }
if (-not (Test-Path -LiteralPath (Join-Path $env:REPORT_EXPORT_NODE_MODULES '@oai/artifact-tool/package.json'))) { throw 'Authorized Excel runtime not found' }
& .\.venv\Scripts\python.exe -m app.reporting.export_cli --dataset-version-name demo-master-v1 --report all --output-dir ../exports
```

输出文件为 `report1_overdue_po_detail.xlsx`、`report2_material_supply_demand.xlsx`、
`report3_forecast_history.xlsx`、`report4_latest_13w_forecast.xlsx`、
`report5_product_configuration.xlsx`、`report6_stockpile_detail.xlsx`。
全部在根目录 `exports/` 下且默认 ignore。当前环境的历史 smoke 结果为
115 / 60 / 900（28 sheets）/ 60 / 272 / 24 行；动态表头由版本/snapshot 决定。

没有该运行时的用户仍可运行数据库与 API，但 Excel 和依赖它的完整测试被阻塞。
公开分发方式或替代实现需后续单独决定；本次 Final Review 不替换 exporter。

## 6. Tests on a disposable database

在 backend，为第一次运行创建专用测试库；已经存在时不要再次执行 createdb：

```powershell
docker compose --project-directory .. -f ../docker-compose.dev.yml exec -T postgres createdb -U postgres --owner=system_a_owner overdue_po_copilot_test
Get-Content -Raw db/bootstrap/001_roles.sql |
    docker compose --project-directory .. -f ../docker-compose.dev.yml exec -T postgres psql -U postgres -d overdue_po_copilot_test -v ON_ERROR_STOP=1
```

填好根目录 `.env` 中 `TEST_DATABASE_URL` 和 `TEST_DATABASE_ADMIN_URL`。
pytest 的连接设置直接读取进程环境，不能只依赖应用 Settings 读取 `.env`。
只加载这两个键，不打印值、不执行文件内容：

```powershell
Get-Content ../.env | ForEach-Object {
    if ($_ -match '^(TEST_DATABASE_URL|TEST_DATABASE_ADMIN_URL)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
    }
}
& .\.venv\Scripts\python.exe -m pytest
& .\.venv\Scripts\python.exe ../scripts/check_forbidden_terms.py
```

完整 pytest 还需同会话中的 Excel runtime。测试会在专用测试库执行
`downgrade base → upgrade head`，并重放 grants；禁止使用开发库或共享库。
无需 PostgreSQL 的检查可用 `python -m pytest -m "not integration"`，不能将子集结果当全量验收。

## Review boundary

本手册修复了原 README 的工作目录、角色密码和测试环境变量说明。
本次只验证 Compose 配置解析、已有实例只读状态、CLI 参数及 targeted 回归；
未另建一套全新机器环境、未重建开发 Dataset、未重跑历史 439 项全量。
Python 依赖使用固定版本，但这里不宣称重新下载并验证了所有依赖的公开可获取性。
完整 public reproducibility 仍受 Excel 私有依赖阻塞。
