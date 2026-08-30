# Phase 2B — Deterministic Business Diagnosis Rule Specification

此规范在本轮业务代码之前建立。正式原因沿用五类：TRIAL、STOCKPILE、DEMAND_ADJUSTMENT、AFTER_SALES、PROJECT_OBSOLESCENCE。量产是组织分支入口，不新增 MASS_PRODUCTION 原因。仅 TRIAL 具有当前可完整执行的业务谓词；其余分支保留明确的规则/证据缺口。

## Rule source audit

| 来源 | 已确认内容 | 本轮处理 |
|---|---|---|
| `AGENTS.md` §4–7 | 固定日期、LT+240、五类原因、试产及售后优先级 | 不改变公式和类别 |
| `SCENARIO_RULES.md` §2、§3、§5、§6、§15 | 试产由 R1 inventory organization 判断，优先于其它证据；R5 lifecycle 使用 snapshot；正式分支和排除条件 | 正式 policy 来源，不照搬提示中的线性顺序 |
| `SCENARIO_RULES.md` §7–13 | 数量下降/时间后移区别，EOL 分支，持续小量售后，order-date 历史囤料及内部呆滞 | 记录确定条件，同时保留未量化条件 |
| `DATA_CONTRACT.md` §3、§7、§9 | R1 TRIAL/MASS_PRODUCTION 是组织类型；lifecycle 是 NPI/MASS_PRODUCTION/EOL；DC-15 仅 Synthetic 配置 | 不将 lifecycle=NPI 映射为试产，不把 Mock 阈值提升为正式规则 |
| `ACCEPTANCE_TESTS.md` AT-038–050、AT-054–055 | snapshot EOL、售后优先于囤料、参考项目与原因项目分离 | 场景测试与排除条件依据 |
| `DB_SCHEMA.md` 组织/lifecycle 受控值；`ARCHITECTURE_API.md` lifecycle 与 DC-15/16 | 组织维度与项目维度分离；当前时点语义；Mock 参数用途 | 与实际 Canonical 契约交叉核对 |
| `backend/app/generators/scenarios/{config,planner,validation,mappings}.py` | coverage-first 和试产组织优先；Synthetic 阈值、隐藏期望值 | 只审计，不导入、不读 Truth、不移植阈值或动作 |
| `backend/app/generators/evidence_foundation/validation.py`；`backend/tests/test_scenario_planning.py` | 0.35 等数值用于合成证据校验；不是获准生产式 Diagnosis 参数 | 不用于正式业务谓词 |
| `backend/app/generators/operational_evidence/{generator,validation}.py` | 合成记录使用 PLANNED tag | 不能单凭此字面量发明正式囤料归属规则 |
| `README.md`、`diagnosis-engine.md`、`evidence-contracts.md`、`analytics-metrics.md`、`data-contracts.md` | 当前能力仅基础 signals；R3 同月 pair 不等于完整 Anchor 比较；R4 有贡献事实 | 保持信号、业务原因和未来责任归属分离 |

正式规格已足够明确试产和分支优先级，不重新解析原始 Word/Excel。提示中的“试产→量产→囤料→需求变化”不是最终 policy；提示要求优先核对正式来源，因此采用 `SCENARIO_RULES.md` §2。DC-16 是未来动作缺口，不被误用为 Diagnosis 阻塞理由。

## Common eligibility and policy

Policy ID：`procurement_diagnosis`，version：`1.0.0`。

所有业务规则先要求 PO 稳定身份及 Analytics `threshold_delta_days > 0`。等于零或小于零返回顶层 `NOT_ELIGIBLE`，不设置主原因；无法计算返回 `UNRESOLVED`。业务时点为 dataset snapshot，无机器当前时间。R1 组织类型只接受契约的 TRIAL/MASS_PRODUCTION；未知/空值为缺失证据，不能猜测或当成量产。

| Priority | Branch | Exclusion / routing |
|---:|---|---|
| 10 | TRIAL | 试产组织直接确定，不要求 Forecast、MPM 联系人或 lifecycle 决定原因 |
| 20 | Customer-side PROJECT_OBSOLESCENCE / DEMAND_ADJUSTMENT | 非试产，明确需求变化；按同一证据项目当前 EOL/非 EOL 分叉，二者同级互斥 |
| 30 | AFTER_SALES | 非试产，已排除明显需求变化；EOL 且未来持续少量非零 |
| 40 | STOCKPILE | 已排除试产、明显变化、售后；下单日有效囤料条件命中 |
| 50 | Internal-side PROJECT_OBSOLESCENCE | 已排除试产、明显变化、售后、有效历史囤料 |

数值 priority 是上述偏序的显式编码，不是业务阈值。未知的高优先级/同级分支不能被当成排除成功。若以后存在多个完整匹配，唯一最高优先级者胜出，低优先级完整匹配记录 `SUPPRESSED_BY_HIGHER_PRIORITY_RULE`；同级冲突或更高优先级未决时返回 UNRESOLVED。没有命中且所有规则均可评估时为 NO_MATCH。本轮实际只有 TRIAL 能匹配，不制造其它原因正例。

## Per-rule specification

下表 rule version 均为 `1.0.0`，source 中章节均指 `SCENARIO_RULES.md`，除非另注。

| rule_id / diagnosis_code | Meaning / priority | Required inputs and formula | Supporting evidence | Exclusions / missing behavior | Temporal semantics / source |
|---|---|---|---|---|---|
| `business_trial` / TRIAL | 试产组织超期 PO；10 | 完整 PO 身份、可用 aging、R1 inventory_organization_type；`delta>0 AND organization_type=TRIAL` | Material→MPM 可留作后续联系人证据；Forecast/囤料可存在但不是必需 | 非超期不适用；MASS_PRODUCTION 不匹配；缺身份/日期/未知组织不可评估 | R1 DATASET_SNAPSHOT_CONTEXT + 显式 aging；不查询项目 lifecycle；§2/§6，DATA_CONTRACT R1，AT-043 |
| `business_customer_obsolescence` / PROJECT_OBSOLESCENCE | 客户侧分支（本轮不输出责任）；20 | 非试产；Anchor 比较证明明显变化；最可能项目在 snapshot EOL | 同月负差只能辅助 | 试产排除；缺项目/变化规范→NOT_EVALUABLE | Anchor=order+LT；lifecycle CURRENT_STATE；§7–10 |
| `business_demand_adjustment` / DEMAND_ADJUSTMENT | 需求变化、项目非 EOL；20 | 非试产；同一项目/共同月份的正式 Reduction/Delay/Mixed 判据；该项目 snapshot 非 EOL | 13周数量和单月变化 | 试产/EOL 分支排除；不能用单月下降代替完整判据；缺口→NOT_EVALUABLE | Anchor 多版本 + CURRENT_STATE；§7–9 |
| `business_after_sales` / AFTER_SALES | 售后需求；30 | 非试产；已证实无明显变化；选定项目当前 EOL；未来持续少量非零 | 月/周数量；历史囤料不决定该分支 | 明显变化排除；EOL 本身不充分；缺口→NOT_EVALUABLE | CURRENT_STATE + future week/month horizon；§11，AT-040/041 |
| `business_stockpile` / STOCKPILE | 历史有效囤料相关；40 | 非试产、排除变化及售后；order_date 最近有效版本的 material 记录满足正式有效条件 | 历史 record/tag/数量；供需盈余不增加 >0 门槛 | 任意记录存在不充分；未排除上游/缺 tag 有效规范→NOT_EVALUABLE | STOCKPILE_AS_OF_ORDER_DATE；当前或非 EOL 都不是必需；§12，AT-044–049 |
| `business_internal_obsolescence` / PROJECT_OBSOLESCENCE | 内部呆滞分支（本轮不输出责任）；50 | 非试产，排除明显变化、售后、有效历史囤料 | 覆盖、零需求仅背景 | 不是 default else；任一排除未知→NOT_EVALUABLE | 变化 Anchor / lifecycle CURRENT_STATE / stockpile order date；§13，AT-042/043 |

没有使用 MPM 缺失去阻止 TRIAL 原因：§6 明确所有试产超期 PO 均进入试产分支，联系人解析与处理动作属于后续层。本轮不实现任何动作。

## Unimplemented / Blocked Rules

| Gap ID | Type | Missing definition / evidence | Affected branches |
|---|---|---|---|
| `SIGNIFICANT_FORECAST_CHANGE` | RULE_SPEC_GAP | 正式“明显”变化、Reduction/Delay/Mixed 判据与阈值；DC-15 的 Synthetic 数值不能自动继承 | 所有非试产分支及其排除条件 |
| `MOST_LIKELY_PROJECT_SELECTION` | RULE_SPEC_GAP | 从多项目跨版本证据到最可能项目的确定算法、并列/缺数据策略 | 所有非试产分支 |
| `ANCHOR_COMPARISON_WINDOW` | CONTRACT_GAP | 当前 bundle 只有显式同月 pair；缺完整共同月份 Baseline+2–5版、完整候选集合和完整性证据 | 所有非试产分支 |
| `AFTER_SALES_PATTERN` | RULE_SPEC_GAP | 正式小量参考水平、持续周/月范围与阈值 | AFTER_SALES 及其后续排除 |
| `VALID_STOCKPILE_CONDITION` | RULE_SPEC_GAP | “有效囤料条件满足”的正式 tag/record 语义；PLANNED 是 Generator 字面量，不足以证明 PO 归属 | STOCKPILE / 内部呆滞 |

当前生命周期契约可以支持正式树中的 snapshot 判断，**并非这些分支本身必须历史 lifecycle**。但任何未来要求下单时 lifecycle 的规则仍缺 HISTORICAL_LIFECYCLE，禁止借当前值填补。

本轮不新增 contribution 排名算法：该算法不是 TRIAL 必需输入，也无法解决最可能项目规范缺口。R4 项目贡献事实继续保留，不把最大贡献、PO reference project 或任何名称匹配当作责任项目。数量下降与时间后移继续区分；现有 `NEGATIVE_FORECAST_CHANGE` 只证明单月负向变化。

## Verification contract

Golden scenarios 位于测试侧：最小试产、试产伴随其它信号、量产伴随 EOL/负差/囤料仍未决、量产 NPI 不冒充试产、阈值前/当天/后、未知组织、缺稳定 ID、缺 Forecast/囤料、同数据重复计算。Primary trace 必须包含组织字段、aging delta及其 order/LT 来源。Policy 的多匹配/同级冲突/高优先级缺失仅用测试侧评估结果验证选择器，不宣称 blocked 原因已实现。
