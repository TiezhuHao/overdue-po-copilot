# Phase 2C — Deterministic Business Diagnosis Rule Specification

此规范始建于Phase 2B；Phase 2C按用户明确授权，将未量化概念参数化，补齐六个分支。正式原因仍只有TRIAL、STOCKPILE、DEMAND_ADJUSTMENT、AFTER_SALES、PROJECT_OBSOLESCENCE；量产不是第六类原因。规则可以执行不等于企业参数已确认：没有内置Demo参数，调用方必须显式提供，缺失则不可评估。

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
| `README.md`、`diagnosis-engine.md`、`evidence-contracts.md`、`analytics-metrics.md`、`data-contracts.md` | 原R3同月pair不等于完整Anchor比较；R4已有贡献事实 | Phase 2C新增完整history装配与中性聚合，继续分离信号、原因与责任 |

正式规格已足够明确试产和分支优先级，不重新解析原始 Word/Excel。提示中的“试产→量产→囤料→需求变化”不是最终 policy；提示要求优先核对正式来源，因此采用 `SCENARIO_RULES.md` §2。DC-16 是未来动作缺口，不被误用为 Diagnosis 阻塞理由。

## Common eligibility and policy

Routing policy：`procurement_diagnosis / 2.0.0`。BusinessDiagnosisPolicy由调用方提供独立policy_id/version和下列参数，完整对象与SHA-256 fingerprint进入结果；每条业务评估记录`used_policy_fields`。未提供参数对象时结果明确`business_policy=null`，routing版本不代表存在隐含参数。

| Parameter | Validation / exact meaning | Missing behavior |
|---|---|---|
| `demand_change.total_drop_ratio` | `(0,1]`；共同月份总量相对Baseline的下降幅度，含等号 | 变化及排除分支NOT_EVALUABLE |
| `demand_change.later_shift_ratio` | `(0,1]`；中性later_shift_qty / Baseline合计，含等号 | 同上 |
| `demand_change.min_comparison_months` | 整数2–7；拒绝过短共同窗口 | 同上 |
| `demand_change.post_version_count` | 整数2–5；必须具有位置1..N的完整Post前缀 | 同上 |
| `after_sales.max_average_weekly_qty` | 正Decimal；选定项目13周平均数量上限，含等号，单位为该物料Canonical qty/week | 需要售后判据时NOT_EVALUABLE |
| `after_sales.min_nonzero_weeks` | 整数1–13；13周内非零桶的最少个数 | 同上 |
| `after_sales.min_consecutive_weeks` | 整数1–13；最长连续非零周数的下限 | 同上 |
| `valid_stockpile_tags` | 非空、无重复、无空白标签的显式tuple；精确匹配，不自动转大小写 | 需要囤料判据时NOT_EVALUABLE |

没有量化默认值；允许参数组为null以表达缺失，不将null解释成禁用规则。数量阈值必须使用对应物料的Canonical单位，当前Contract仍没有UOM转换能力。Policy只允许这些参数与身份，不允许PO/material答案表或期望原因字段。

### Parameterized predicate definition

项目：对同一R4快照/物料/13周完整项目桶聚合，唯一正贡献第一名作为本轮规则的`top_contributing_project`。并列第一→`AMBIGUOUS_TOP_PROJECT`，全零→`NO_POSITIVE_PROJECT_DEMAND`，均不选项目。不把它称为责任或已证明的因果项目。

Forecast：接收调用者提供的Canonical `forecast_history`，不从数组顺序猜previous/current。验证R3显式位置0=Baseline、位置1..N=Post，N在2–5；Anchor=order+LT，Baseline严格早于Anchor，Post严格晚于Anchor且不晚于snapshot。每版必须完整覆盖其声明的7个自然月；同一项目/物料/schedule/dataset/snapshot且版本身份、日期、序号一致。

在所有提供版本的共同月份上计算Baseline与每个Post的中性总量和后移匹配量；明确定义见 [analytics-metrics.md](analytics-metrics.md)。共同窗口必须满足policy最小月份数，前N个Post必须完整。任一被要求的Post满足 `total_change_rate <= -total_drop_ratio OR later_shift_share >= later_shift_ratio` 即为显著变化；全都可评估且未满足才能证明该配置窗口内无显著变化。Baseline总量为0时rate为null；在数量非负前提下既无可减少的Baseline数量，也无可后移的Baseline亏缺，因此不命中这两个负向条件。

售后：本轮明确支持**选定项目完整13周**模式，`0 < average_weekly_qty <= max_average_weekly_qty`且nonzero count和最长连续run均达到显式参数；不声称额外验证6个月需求或与历史正常日量的比例。需要月维度售后策略时应独立扩展输入/参数，而不是隐式套用Generator配置。

所有业务规则先要求 PO 稳定身份及 Analytics `threshold_delta_days > 0`。等于零或小于零返回顶层 `NOT_ELIGIBLE`，不设置主原因；无法计算返回 `UNRESOLVED`。业务时点为 dataset snapshot，无机器当前时间。R1 组织类型只接受契约的 TRIAL/MASS_PRODUCTION；未知/空值为缺失证据，不能猜测或当成量产。

| Priority | Branch | Exclusion / routing |
|---:|---|---|
| 10 | TRIAL | 试产组织直接确定，不要求 Forecast、MPM 联系人或 lifecycle 决定原因 |
| 20 | Customer-side PROJECT_OBSOLESCENCE / DEMAND_ADJUSTMENT | 非试产，明确需求变化；按同一证据项目当前 EOL/非 EOL 分叉，二者同级互斥 |
| 30 | AFTER_SALES | 非试产，已排除明显需求变化；EOL 且未来持续少量非零 |
| 40 | STOCKPILE | 已排除试产、明显变化、售后；下单日有效囤料条件命中 |
| 50 | Internal-side PROJECT_OBSOLESCENCE | 已排除试产、明显变化、售后、有效历史囤料 |

数值priority只编码正式偏序。未知的高优先级/同级分支不能被当作排除成功；同级冲突返回UNRESOLVED。若多个完整规则命中，唯一最高优先级者胜出，低优先级完整匹配记录`SUPPRESSED_BY_HIGHER_PRIORITY_RULE`。内部呆滞要求所有五个更高分支均已评估且NOT_MATCHED；任何未决阻止fallback。

## Per-rule specification

TRIAL维持`1.0.0`；其余五个分支从blocked实现升级为`2.0.0`，routing版本同为`2.0.0`。企业参数版本由调用者独立管理；修改参数可改变结果，结果保留参数全文和fingerprint，即使调用者复用了ID/version也可辨别实际参数。source章节指`SCENARIO_RULES.md`。

| rule_id / diagnosis_code | Meaning / priority | Required inputs and formula | Supporting evidence | Exclusions / missing behavior | Temporal semantics / source |
|---|---|---|---|---|---|
| `business_trial` / TRIAL | 试产组织超期 PO；10 | 完整 PO 身份、可用 aging、R1 inventory_organization_type；`delta>0 AND organization_type=TRIAL` | Material→MPM 可留作后续联系人证据；Forecast/囤料可存在但不是必需 | 非超期不适用；MASS_PRODUCTION 不匹配；缺身份/日期/未知组织不可评估 | R1 DATASET_SNAPSHOT_CONTEXT + 显式 aging；不查询项目 lifecycle；§2/§6，DATA_CONTRACT R1，AT-043 |
| `business_customer_obsolescence` / PROJECT_OBSOLESCENCE | 客户侧分支，不输出责任项目；20 | 非试产；demand_change参数判据成立；唯一选定项目当前EOL | 完整共同月份变化、版本和项目贡献 | 试产/无显著变化/非EOL排除；缺参数、项目、对应lifecycle→NOT_EVALUABLE | Anchor + CURRENT_STATE；§7–10 |
| `business_demand_adjustment` / DEMAND_ADJUSTMENT | 需求变化、项目非EOL；20 | 同上，但选定项目当前非EOL | 总量与后移中性指标；不强行输出Reduction/Delay子类型 | 试产/无显著变化/EOL排除；缺证据不可评估 | Anchor + CURRENT_STATE；§7–9 |
| `business_after_sales` / AFTER_SALES | 售后需求；30 | 无显著变化；选定项目当前EOL；after_sales显式13周模式成立 | 选定项目平均、nonzero count、连续run | 显著变化或非EOL明确排除；缺参数/证据不可评估；历史囤料不参与 | CURRENT_STATE + 13周；§11，AT-040/041 |
| `business_stockpile` / STOCKPILE | 历史有效囤料相关；40 | 无显著变化；售后已NOT_MATCHED；历史记录tag精确属于valid_stockpile_tags | order-date选择元数据、record/tag、数量 | 售后优先；缺历史查询/标签参数/上游排除→NOT_EVALUABLE；空完整查询不匹配 | STOCKPILE_AS_OF_ORDER_DATE；§12，AT-044–049 |
| `business_internal_obsolescence` / PROJECT_OBSOLESCENCE | 严格内部fallback，不输出责任项目；50 | 所有高优先级适用规则完整评估并NOT_MATCHED | 前述排除所用证据和参数 | 任一MATCHED排除；任一NOT_EVALUABLE则未决，绝不是default else | 继承每项证据时点；§13，AT-042/043 |

没有使用 MPM 缺失去阻止 TRIAL 原因：§6 明确所有试产超期 PO 均进入试产分支，联系人解析与处理动作属于后续层。本轮不实现任何动作。

## Remaining runtime gaps and boundaries

六个分支均已实现，不再用Phase 2B固定gap永久阻塞。运行时缺参使用`MISSING_POLICY_PARAMETER`，缺字段/窗口使用MissingEvidence及具体中性计算reason code；这些都能导致NOT_EVALUABLE，不会被视作false。

仍未定义企业参数的权威值，不发布隐藏默认值或Demo profile。项目第一名并列、全部零贡献、项目桶不完整/不对账、对应项目lifecycle缺失/冲突、历史查询不完整、共同月份不足都保持未决。不会自动补R3版本/缺失月份，也不会通过名称连接。

当前生命周期契约可以支持正式树中的 snapshot 判断，**并非这些分支本身必须历史 lifecycle**。但任何未来要求下单时 lifecycle 的规则仍缺 HISTORICAL_LIFECYCLE，禁止借当前值填补。

R3日内最终有效版本及位置由现有System A公开契约提供，装配层验证这些元数据而不重查完整版本目录；它不能证明调用方是否隐瞒了整个上游版本。调用方必须保留真实响应且完整取得所要求的版本月桶。Top contribution是本轮明确选定的中性规则输入，不声称它等于根因项目；参考项目不参与选择。后移匹配量只是可对齐的数量形态，不证明真实订单迁移关系。

## Verification contract

`test_system_b_diagnosis_completion.py`提供显式测试policy及9个完整Golden场景：TRIAL、客户侧、数量调整、后移调整、售后、囤料、内部、EOL囤料、EOL内部。另验证并列、缺参数/窗口、日期/身份/生命周期冲突、严格fallback、阈值边界、空历史查询、顺序/Decimal确定性、同证据不同policy及完整provenance。测试expected只在tests中，不进入System A或Policy。
