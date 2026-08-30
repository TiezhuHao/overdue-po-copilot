# v1.0 Release Verification

Release-prep 验收记录，不代表已 push、tag 或创建 GitHub Release。全部业务数据为合成数据；业务 snapshot 固定为2026-08-26，与检查日期无关。

## Checkpoint

Phase 5：`69a65b417881a43830091dbafb352b22d6052430` — `feat: add procurement dashboard and copilot UI`。
提交前与已验收范围一致：9个修改、19个新增文件；hygiene 6项、forbidden 276文件、secret/local-path/generated artifact检查、冻结依赖安装和生产构建均通过。

最初构建因上轮演示服务锁住 `.next` 中日志失败；确认进程身份后停止并重新构建通过。后续本地日志放在已忽略的 exports，没有修改产品代码或删除数据库。

## Final validation

本轮在最终评估代码上执行完整回归，未用旧阶段结果替代：

| Command / check | Pass | Fail | Skip | Deselected | Notes |
|---|---:|---:|---:|---:|---|
| Backend `python -m pytest -q --tb=short` | 996 | 0 | 0 | 1 | 1010.16秒；专用test数据库；唯一排除为收费模型opt-in |
| `python -m pytest tests/test_release_evaluation.py -q` | 25 | 0 | 0 | 0 | 同一25项已包含在全量996内 |
| `python -m tests.release_evaluation` | 25 | 0 | 0 | 0 | JSON summary、退出码0；同一用例集 |
| Frontend `pnpm run test` | 13 | 0 | 0 | 0 | Node / React tests |
| repository hygiene + forbidden-term tests | 6 | 0 | 0 | 0 | 含截图元数据与已知secret检查 |

`pip check`无依赖冲突；`pnpm install --frozen-lockfile`通过且lockfile未变；frontend lint、typecheck、最终production build通过。`git diff --check`通过，仅有Git自动换行提示。Forbidden-term扫描281文件通过；通用密钥模式、已知本地secret、本机绝对路径、待提交生成垃圾及新增文档相对链接均检查通过。

最终额外代码只在tests中增加评估入口和pytest包装；没有修改app引擎、API、Prompt、数据库migration或前端业务实现。独立评估初次运行发现测试断言把一种允许表述包含另一种表述的子串误算成两次，已改为精确整行校验并重跑通过；未放宽生产grounding。

离线发布评估25 pass / 0 fail，每个 case重复两次；Grounding专项6/6；意图只评估脚本化输出的路由。见 [evaluation.md](evaluation.md)。

## Real model boundary

**Real OpenAI smoke not executed**：当前进程没有 `OPENAI_API_KEY` / `OPENAI_MODEL`。没有付费请求，没有虚构模型名或准确率。默认 pytest显式排除收费模型用例，浏览器 FALLBACK 不计为模型成功。

## Local run and screenshots

采用现有 PostgreSQL、READY demo和012 migration；本轮没有改 migration、Generator 或业务数据。运行 System A 8000、System B 8100、Next.js生产服务3000。没有公开端口或重跑 demo生成。

陌生开发者使用 `LOCAL_SETUP.md` 的公开依赖、角色、migration和固定生成步骤，再按README启动三个服务。本次不宣称再次从空数据库/全新机器重建；旧独立环境复现证据见 `PUBLIC_REPRODUCIBILITY.md`。

当前机器没有 Docker CLI（PATH及标准安装位置均无），故 `docker compose config/up` 没有执行成功；只完成两个 Compose 文件的 YAML解析与服务定义审查。实际链路使用现有 PostgreSQL，完整容器从零启动不是本轮已验证项。README明确dev Compose只负责数据库，早期三服务骨架不是v1.0入口。

真实截图来自 demo，没有地址栏、key、本机路径或企业隐私；Dashboard、订单概览/Copilot及诊断/处置视图分别留档。没有修改 DOM 或合成 UI。

- `screenshots/dashboard.jpg`：复核并保留Phase5实际工作台截图。
- `screenshots/po-detail.jpg`：复核并保留Phase5订单概览、指标与中文回答截图。
- `screenshots/diagnosis-decision.jpg`：本轮新增，实际页面滚动到诊断/处置，包含规则版本、MPM、只读限制与Copilot。

本轮再次通过 `/` → `/po/9fe1f6bf-83d8-5987-a6a7-07b54ab82c26?dataset=1d533913-115a-5f95-a865-374640fb05fc`，提交“为什么这个 PO 超期？应该怎么办？”，得到COMPLETED/TRIAL/REQUEST_MPM_CONFIRMATION/MPM及明确FALLBACK回答。无付费模型调用。

另外提交“这个订单还需要多久消耗完？”，保留相同业务身份和精确消耗值。因无模型，两次均为明确身份下的完整分析fallback，不声称验证了真实Analytics意图提取。Evidence展开显示实际business_trial/decision_trial规则版本及R6来源版本。A的health/ready、B的OpenAPI和前端页面实际HTTP200。

## Remaining release caveat

v1.0可用于本地求职展示，真实模型仍待独立验证。无认证或写回，不等于生产就绪。最终 commit后等待人工验收，不 push、不 tag。
