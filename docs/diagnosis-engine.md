# System B — Phase 2A Foundation / Phase 2B Policy / Phase 2C Completion

Phase 2A的原`diagnose`接口仍只产生支持信号，primary_reason=null。Phase 2B建立业务入口/policy；Phase 2C在相同架构中补齐六个可配置业务分支，覆盖原五类原因。缺参数或证据仍不可评估，不提供企业阈值默认值，不输出责任项目、采购动作或置信度。

## Layer responsibility

Analytics 回答“数字是多少”；Diagnosis 将可核验的证据与规则关联，未来回答“证据支持什么原因”；Decision 未来回答“应该怎么办”。本阶段不实现 Decision、Agent、自然语言生成、API 或前端。

```text
Adapter → Canonical Models → existing Analytics functions
                        ↓              ↓
                   Evidence Assembler
                            ↓
                     Evidence Bundle
                            ↓
                   ordered Diagnosis Rules
                            ↓
                  Diagnosis Result + Trace
```

代码位于 `backend/app/system_b/diagnosis/`：

- `models.py`：不可变的输入、证据、缺失项、规则结果和诊断结果契约。
- `assembler.py`：稳定身份/时间校验，调用现有 Analytics，建立字段事实和血缘。不会复制指标公式。
- `rules.py`：简单 Protocol、三个规则及固定顺序的 tuple registry。
- `engine.py`：先验证 bundle 血缘，再检查规则前置条件、执行规则并收集所用事实及其来源。
- `business_models.py`：业务原因、规则缺口、业务评估和升级结果，与foundation signals分离。
- `business_rules.py`：TRIAL和五个参数化业务分支；版本、priority、证据需求及严格排除条件。
- `policy.py`：复用foundation验证，执行业务规则，按明确priority选择唯一primary并生成业务trace。
- `parameters.py`：调用者显式BusinessDiagnosisPolicy；只含身份、阈值、窗口/持续性参数和有效标签，不含答案查找表。

这些模块不导入 Adapter、HTTP、数据库、Settings 或 SDK，不读取机器时间。`as_of_date` 来自 PO 的 dataset snapshot。调用者负责在边界外获取 Canonical 数据，不能通过名称猜测跨记录关系。

## Evidence bundle

`EvidenceInputs`接收一个PO以及可选weekly、supply、previous/current forecast、完整`forecast_history`长表行集合、products和历史囤料查询结果。`EvidenceBundle`包含Canonical输入、Analytics分组结果、facts和missing_evidence。history各行也必须通过已有dataset/material/schedule/时间门禁。

| Evidence kind | 实际内容与范围 |
|---|---|
| `PO` | Header/Line/Schedule、material/supplier/organization 稳定 ID；下单日期、LT、未交量、状态及参考项目 |
| `PO_AGING` | 年龄、阈值、有符号阈值差、非负剩余/越界天数 |
| `PO_CONSUMPTION`, `INVENTORY_COVERAGE` | 同物料/组织的 PO 预计消耗周数与库存覆盖周数 |
| `SUPPLY_DEMAND` | R2 reported `all_supply_qty`、实际需求和 Analytics 盈余差；不称为 confirmed/planned supply |
| `FORECAST_PAIR`, `FORECAST_CHANGE` | 显式两个 R3 同月记录的项目、版本、日期、序号、月份、数量及可比较变化量/变化率 |
| `WEEKLY_FORECAST`, `PROJECT_CONTRIBUTION` | R4 周快照、源版本、13 周日期/数量及项目周事实；不排名、不推导责任 |
| `CURRENT_LIFECYCLE` | R5 当前 lifecycle、配置版本、business unit、planning department；带项目/配置 ID |
| `HISTORICAL_LIFECYCLE` | 保留为显式缺口，当前没有输入实现 |
| `STOCKPILE_HISTORY` | PO 下单日 as-of 查询的选择元数据、记录数量、版本、tag、target/actual quantities |
| `MPM` | R2 的 Material → employee 联系关系，不绑定项目 |
| `PROJECT_SELECTION` | 中性项目数量ranking、唯一top、平均周量、非零周数和最长连续run；并列不可选择 |
| `FORECAST_HISTORY` | R3各项目/版本/月事实，含位置、Anchor、版本序号和完整horizon元数据 |
| `ALIGNED_FORECAST` | 选定项目Baseline与Post的共同月份总量、变化率及中性后移匹配量；来源关联完整history |

源记录若跨 dataset、snapshot、material，或具有相互冲突的 organization/schedule ID，装配失败。跨物料关系缺少 material ID 也失败。缺少其他必要稳定 ID 或可计算指标则标记缺失，不能按名称补齐。拒绝未来观察日期、历史选择/记录版本不一致及重复证据地址。

装配层保留 Analytics 的 availability 和 reason codes；只有满足依赖且具有可用数值的指标才成为对应规则可用事实。零需求不会被转换为无限覆盖。变化率在 previous=0 时可以为空，但可靠的变化量仍能用于方向规则。

## Provenance and trace

每条 `EvidenceFact` 包含 `evidence_id`、kind、source（R1–R6 或 ANALYTICS）、命名的稳定 `entity_keys`、dataset ID、snapshot date、`observed_on`、可选版本日期/序号及 period、field、observed value。`evidence_id` 是一次 PO/dataset 诊断内的稳定地址，不是全局数据库键。

`observed_on` 是源业务观察日期、版本日期或历史查询的逻辑 as-of 日期，不是抓取时间。R5 当前事实使用 dataset snapshot；历史囤料空结果保留查询 as-of 和已选版本（若存在）。所有事实另外保留 dataset snapshot，不将这些时间混为一谈。

派生指标使用 `derived_from` 指向原始字段。例如 Forecast 变化量关联 previous/current 的数量事实，各自保留 material/project/version ID、版本日期、sequence 和月份。最终 `evidence_trace` 包含实际使用的字段及其递归来源，顺序确定，不复制原始数据库对象或完整 HTTP 响应。可选而未用于规则的事实留在 bundle。

调用者不能附加脱离输入的 Analytics 数字。`assemble_evidence` 从 Canonical 输入调用现有计算；`diagnose` 再验证 bundle 与其输入重建结果一致，拒绝修改过的数字、事实或缺失列表。这是进程内一致性校验，不是外部数据签名或来源真实性认证。

## Historical stockpile query scope

`HistoricalStockpileQuery` 要求调用者保留**实际发送的** material ID 和 as-of；as-of 必须为 PO order date。其 `page` 必须是该单物料查询的 CanonicalPage，不能把未过滤的空页包装成“没有囤料”。本阶段拒绝显式 version override，因为该选项不能证明默认的最近有效历史选择。

只有 page=1、items 与 total 完整一致、选择元数据一致，才能判断存在或不存在。R6 物料过滤后的已选版本最多一条物料记录；大于一条视为粒度冲突。完整空结果（包括未选到有效版本）为已知不存在；未提供查询、缺少选择信息、分页不完整或 tag/记录 ID 缺失，均不可判断。调用者提供的查询范围是信任边界，装配层不会自行发 HTTP 请求验证。

## Rule interface and evaluation

`DiagnosisRule` Protocol 声明 `rule_id`、`version`、`semantic_label`、`required_evidence` 和 `evaluate(bundle) -> RuleEvaluation`。registry 是显式 tuple，无动态发现。执行顺序稳定，但不代表未来正式业务原因的判断优先级。

| State | 含义 |
|---|---|
| `MATCHED` | 必要证据齐全，条件成立，输出支持信号 |
| `NOT_MATCHED` | 必要证据齐全，条件不成立 |
| `NOT_EVALUABLE` | 缺少必要证据，不能将未知视作 false |

引擎统一检查 required evidence；缺失时不执行 predicate。返回值校验包括 rule ID/version、状态与 signal 一致性，以及所引用事实必须属于该规则声明的 evidence kind。所有规则均被记录，不因前一规则未命中而省略后续 trace。

| Rule ID / version | 条件 | Signal |
|---|---|---|
| `po_overdue_threshold` / `1.0.0` | Analytics `threshold_delta_days > 0`，即 age > LT+180+60；阈值当天不命中 | `OVERDUE_THRESHOLD_EXCEEDED` |
| `historical_stockpile_presence` / `1.0.0` | 可靠的下单日查询存在完整囤料记录及非空 tag | `HISTORICAL_STOCKPILE_RECORD_PRESENT` |
| `forecast_negative_change` / `1.0.0` | 可比较的显式同月 pair，其 `forecast_change_qty < 0` | `NEGATIVE_FORECAST_CHANGE` |

Forecast 使用现有 Analytics 对同 dataset/snapshot/material/project/schedule/month、不同版本 ID 和明确先后版本日期的校验；装配层额外要求版本序号，提供 horizon 边界时要求月份处于边界内。同日 pair 仍不可比较，不扩展既有 Analytics。没有自动查找上一版本、完整 Anchor 窗口或“下降百分之多少”的业务阈值。

## Diagnosis result and missing evidence

结果包含实体身份、dataset、as-of、每条规则的 ID/version/state、支持 signals、使用/缺失证据以及 trace。状态含义：

- `FOUNDATION_ONLY`：选定基础规则所需证据齐全，仅提供基础信号。
- `INSUFFICIENT_EVIDENCE`：存在规则无法评估。
- `NOT_ELIGIBLE`：阈值规则可评估但未越过阈值；其他缺失项仍保留。

原foundation `DiagnosisResult.primary_reason` 的类型仅允许 `None`。这三条支持规则不能证明最终 STOCKPILE 或 DEMAND_ADJUSTMENT 等业务原因。业务入口返回其扩展类型 `BusinessDiagnosisResult`，见下节。

`completeness=COMPLETE/PARTIAL` **只针对 `completeness_scope` 列出的规则要求**，不是完整业务诊断的可信程度。即使 COMPLETE，仍为 foundation，历史 lifecycle 等未被所选规则要求的缺口仍记录在 bundle 中。结果 missing_evidence 只列所选规则要求的缺口；没有统计 confidence。

稳定缺失码：`NOT_PROVIDED`、`MISSING_STABLE_ID`、`MISSING_REQUIRED_FIELD`、`NOT_COMPUTABLE`、`INCOMPLETE_COLLECTION`、`HISTORICAL_LIFECYCLE_UNAVAILABLE`。缺失项可携带字段名及原 Analytics reason codes。结构冲突则抛出仅含稳定错误码的 `EvidenceAssemblyError`，不输出源记录或凭证。

## Safety boundaries and remaining gaps

`CURRENT_LIFECYCLE` 与 `HISTORICAL_LIFECYCLE` 是不同 evidence kind。历史 kind 始终缺失；即使 R5 当前值为 EOL，要求历史 lifecycle 的规则也必须 NOT_EVALUABLE。不能注入一个未定义的历史输入绕过此限制。

`po_reference_project_id` 仅保留 reference/context 语义，不约束 Forecast 必须属于该参考项目。项目周贡献只保留事实；最大贡献项目不会自动成为责任项目。结果不包含责任字段、推荐动作或最终原因猜测。

后续仍需独立处理历史lifecycle查询、任意Anchor/完整Forecast目录、PO单价/币种、UOM换算及confirmed/planned composition。本轮已支持R3公开选择窗口的比较及数量贡献ranking，但不推导责任。没有System A扩展，也没有移植Generator/Evaluation阈值。

## Phase 2C business policy and rule logic

正式来源、每条规则条件/排除/时间口径和参数见 [diagnosis-rule-specification.md](diagnosis-rule-specification.md)。该规范在Phase 2B始建，本轮按明确授权参数化并记录版本升级。

业务入口`diagnose_business(bundle, policy=None)`先验证完整bundle再执行业务规则。policy为可选仅表示可显式缺失，不代表存在默认参数；TRIAL可独立完成，其余分支按实际需要返回MISSING_POLICY_PARAMETER。`BusinessRule`保持现有ID/version/semantic label/required evidence/evaluate结构，额外消费参数及已评估的高优先级排除结果。只有MATCHED并通过policy选择才成为primary。

`business_trial / 1.0.0`保持不变：可用aging、完整PO身份、R1组织TRIAL。未知组织不可评估，NPI不冒充试产，可选Forecast/囤料/联系人不阻止TRIAL。其它五个分支升级2.0.0：共同月份显著变化参数 + 选定项目CURRENT_STATE分叉；无显著变化后判断显式13周售后模式；再判断order-date历史tag是否属于显式有效标签；最后严格fallback。不存在“任意负数→明显变化”或“EOL→售后”的快捷路径。

Routing `procurement_diagnosis / 2.0.0`保持TRIAL(10) → 变化EOL/非EOL(20) → AFTER_SALES(30) → STOCKPILE(40) → 内部(50)。量产不是原因，rank不是数量门槛。同级冲突或更高/同级未决阻止选择；内部要求全部五个更高分支明确NOT_MATCHED。完整低优先级匹配被覆盖时保留suppressed语义，foundation signals不被当成root causes。

| Business status | Meaning |
|---|---|
| DIAGNOSED | 唯一业务规则在当前显式参数和证据下完整成立 |
| NOT_ELIGIBLE | PO未越过LT+240；包括阈值当天；primary为空 |
| UNRESOLVED | 必要证据/规则规范不足，或policy冲突；primary为空 |
| NO_MATCH | 所有规则可评估但没有匹配；当前完整树通常由严格fallback覆盖，选择器仍保留该状态 |

业务结果包含primary rule ID/version、调用者policy ID/version、参数全文`business_policy`、参数fingerprint、routing版本、business_evaluations、rule gaps和固定reason_summary_code。每条评估记录used_policy_fields。参数对象在入口重新校验，拒绝构造绕过；只允许阈值/标签/窗口参数，无PO/material答案表。原evaluations/signals仍为foundation支持层，没有生成式解释。

业务结果的completeness_scope列出业务policy规则；missing_evidence与rule_gaps按该范围汇总。试产已明确排除后续分支时可以COMPLETE，即使可选foundation signals有缺失；这些缺失仍保留于foundation evaluations和bundle。UNRESOLVED始终PARTIAL。Primary trace包含R1组织字段及Analytics阈值差，并递归包含order/LT源字段。

正式非试产树使用选定项目snapshot CURRENT_STATE，要求同一project_id，缺配置或多个配置lifecycle冲突则未决；不使用参考项目回退。本轮项目选择是中性数量贡献唯一第一名，不宣称因果或责任。并列/全零不能按UUID选择。售后是明确的13周模式，不额外宣称6月或历史正常日量比例判断。历史lifecycle仍是独立未提供的证据类型。

## Usage and verification

以下对象由调用者通过现有 Adapter 获取并核验，Diagnosis 本身无 I/O：

```python
from app.system_b.diagnosis.assembler import assemble_evidence
from app.system_b.diagnosis.engine import diagnose
from app.system_b.diagnosis.models import EvidenceInputs, HistoricalStockpileQuery

inputs = EvidenceInputs(
    po=po,
    weekly=weekly,
    supply=supply,
    previous_forecast=previous,
    current_forecast=current,
    forecast_history=tuple(history_rows),  # complete required R3 version/month buckets
    products=tuple(products),
    stockpile=HistoricalStockpileQuery(
        material_id=po.material_id,
        as_of_date=po.order_date,
        page=stockpile_page,  # actual material-filtered order-date query, no version override
    ),
)
bundle = assemble_evidence(inputs)
result = diagnose(bundle)

# Explicit business entry; no change to the foundation-only API.
from app.system_b.diagnosis.policy import diagnose_business
from app.system_b.diagnosis.parameters import BusinessDiagnosisPolicy
policy = BusinessDiagnosisPolicy(
    policy_id=approved_policy_id, version=approved_policy_version,
    demand_change=demand_parameters, after_sales=after_sales_parameters,
    valid_stockpile_tags=approved_tags,
)
business_result = diagnose_business(bundle, policy)
```

在 backend 目录执行 `python -m pytest tests/test_system_b_diagnosis.py -q`。测试只用固定 Canonical fixtures，覆盖规则三态、跨 dataset/身份/时间拒绝、来源与派生链、历史 lifecycle 红线、参考项目边界和确定性；不依赖数据库、网络、Generator 或当前时间。

`python -m pytest tests/test_system_b_business_diagnosis.py -q` 增加测试侧JSON Golden scenarios：真正的TRIAL正例、优先级排除、非试产缺口、lifecycle误用反例和阈值边界。多匹配/冲突测试仅验证policy选择器，不把测试侧假评估结果冒充已实现业务原因。

`python -m pytest tests/test_system_b_diagnosis_completion.py -q`验证六分支真实Golden正例/排除、参数切换、完整比较窗口、后移数学、并列、缺参数/生命周期/历史证据及严格fallback。所有数值policy仅存在测试fixture，没有默认企业profile。
