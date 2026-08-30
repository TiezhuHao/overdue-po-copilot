# Phase 5 — Next.js Product MVP

本地、只读的中文采购工作台。复用 Next.js 16.3.1 / React 19.2.8 / TypeScript 5.9.3 / App Router / 普通 CSS；没有升级框架、引入 UI/chart library 或业务规则。

## 页面与数据流

- `/`：READY dataset 选择、超期清单、PO/物料/供应商/参考项目筛选、原 REST 分页。仅有一个 READY dataset 时明确显示并采用它；多个时要求用户选择，不调用隐式 latest。
- `/po/[scheduleId]?dataset=<datasetId>`：稳定身份订单概览、7个后端指标、Diagnosis、Decision、Evidence折叠区及上下文Copilot。
- Detail 首次打开调用一次完整 Copilot 分析；后续中文追问按提交调用。Dashboard 不逐行调用 Agent，没有 N+1 诊断。

浏览器 → 同源 `/api/backend/{datasets|orders|copilot}` → System A/B 既有公开 API。使用[Next.js Route Handlers](https://nextjs.org/docs/app/api-reference/file-conventions/route)进行固定目标转发、参数白名单、timeout与错误脱敏，没有新的业务API。只有datasets/orders GET及copilot POST。POST核验同源Origin，不透传浏览器Cookie/Authorization，不接受任意URL、Policy或模型配置。后端不加通配CORS，不改变FastAPI契约。

`lib/client.ts`统一fetch，`contracts.ts`校验消费字段及上下文，`presentation.ts`仅作标签/字符串展示。后端地址使用服务器环境 `SYSTEM_A_API_BASE_URL`、`SYSTEM_B_API_BASE_URL`；无 `NEXT_PUBLIC_*` key，前端不导入OpenAI SDK。

## 数字与状态口径

- 总数是R1 `total`，名称为“超期发运行”，**不是去重PO Header数量**；过滤后表示当前筛选总数。
- 物料、供应商、参考项目为**本页已知稳定ID**去重，非全dataset统计；未知ID不作为一种新身份计数。
- 越界天数直接展示R1 `overdue_days`，开放量直接展示`overdue_open_qty`。清单保留源报表的关闭/零数量记录，不重新判断资格。
- 数量保持Decimal字符串，不经浮点转换。长指标在卡片截取4位小数后标`…`，可展开完整值；这不是重新计算或声称四舍五入值。null显示`Not computable`，零值显示0。
- Diagnosis/Decision/owner/action/source rule/version只显示后端已有结果。未决不是已确认，缺动作不推测采购操作。DC-16明确显示`Decision specification incomplete`。
- 当前Copilot公开投影没有Forecast change、coverage、supply-demand和逐项required checks。UI明示未公开；没有从原始报表重新计算，也没有把未公开指标误标为业务零值。
- 不显示金额、savings、风险分数、首页诊断统计；参考项目与top贡献项目不表示责任。

状态有文字与badge，涵盖加载、空列表、不可计算、未决、不适用、未找到、澄清、失败。网络异常只显示安全提示，不显示stack trace。表头、输入label、禁用提交和loading/error可访问文本已提供。

## Copilot

四个快捷问题只填入输入框，不预置答案。每次请求携带dataset、snapshot、schedule；身份最终仍由后端校验。切换身份重新挂载Detail，不沿用前一个订单的回答。临时history仅存在当前页面内存，刷新丢失。

返回answer的章节和段落仅作为React文本节点展示，不解释HTML、脚本或外部链接。模型/确定性fallback/澄清的来源分别显示。业务卡片消费当前订单的结构化结果，回答内附引用和限制。

无OpenAI key仍可完成带明确身份的fallback。TRIAL无需额外诊断Policy，可作为本轮演示入口。其他分支仍需后端明确提供已确认Policy；前端不塞测试参数使结论“变绿”。

## Run locally

需要Python 3.12环境、现有PostgreSQL、Node.js 24及项目固定pnpm 11.19.0。初次环境准备按[本地运行手册](LOCAL_SETUP.md)。不要以owner角色运行API。

**终端1：System A**（仓库根目录开始）：

```powershell
cd backend
python -m pip install -r requirements.txt
python -m alembic current
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

仅部署仓库已有迁移，当前head应为`012_evidence_contract`；若仍是011，订单清单可能正常而供需证据查询会失败。本轮演示库由011升级到已有012，创建证据视图及原授权，没有新增migration、重跑Generator或改业务事实；已发布dataset的hash元数据保持不变。

**终端2：System B**：

```powershell
cd backend
$env:SYSTEM_A_BASE_URL="http://127.0.0.1:8000/api/v1"
python -m uvicorn app.system_b.copilot.api:app --host 127.0.0.1 --port 8100 --env-file ../.env
```

本机8001绑定失败，演示采用8100，无需修改系统端口配置。其他端口可调整启动参数及frontend环境。key/model只在System B服务器配置；本阶段未运行收费模型smoke。

**终端3：Frontend**：

```powershell
cd frontend
Copy-Item .env.example .env.local
pnpm install --frozen-lockfile
pnpm run lint
pnpm run typecheck
pnpm run test
pnpm run build
pnpm start --hostname 127.0.0.1 --port 3000
```

若已有`.env.local`，核对两个公开后端地址，不覆盖其他本地配置。启动服务后打开[采购工作台](http://localhost:3000)。开发热更新可使用`pnpm dev --hostname 127.0.0.1 --port 3000`替代build/start。不加载远程字体，构建不依赖后端或OpenAI在线。

## Demo path and verification

选择实际API返回的`demo-master-v1`、snapshot `2026-08-26`，在首页点击`PO-000015 / 行3 / 发运1`（schedule `9fe1f6bf-83d8-5987-a6a7-07b54ab82c26`），再输入“为什么这个 PO 超期？应该怎么办？”。此记录通过公开列表选取，未读取隐藏答案；记录ID仅作为文档演示指引，不硬编码在应用。

真实链路验证：订单 → `TRIAL` → `REQUEST_MPM_CONFIRMATION` / MPM → 中文fallback回答。查看Evidence可见snapshot、实际规则/版本和源版本引用。不是模拟前端数据，也不表示真实OpenAI已验收。

前端用已有TypeScript编译器、Node测试runner和React server renderer做轻量测试，无新增测试框架。覆盖字段mapping、Decimal/null、分页、scope拒绝、状态保留、代理白名单/Origin/错误脱敏、可访问loading/error、未决与DC-16及原动作呈现。

浏览器验证包括真实Dashboard/Detail/Copilot、筛选/空列表、分页、1440和1920桌面及窄屏基础布局。数据库API回归继续使用专用测试数据库。截图见README Product Screens。

## Remaining UI gaps

缺少公开contract的指标和checks继续明示缺口；没有组织filter（当前R1不提供）、全dataset多维聚合、自由选聊天对象、多轮memory、认证、限流、streaming或采购写回。真实模型与最终GitHub整理留后续阶段；当前服务只绑定本机，不用于生产公开部署。
