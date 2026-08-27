# System A Scenario Rules

## 1. 目标与边界

Synthetic Generator 必须先选择隐藏 Scenario Pattern，再反向生成相互一致的业务证据。Scenario Pattern 是造数模板，不等于最终业务分类。System A 只造证据和保存隐藏真值，不在普通 Report/API 中输出诊断答案。

最终 `cause_type` 只能是：

```text
TRIAL
STOCKPILE
DEMAND_ADJUSTMENT
AFTER_SALES
PROJECT_OBSOLESCENCE
```

允许的内部需求变化子类型：

```text
REDUCTION
DELAY
MIXED
NONE
```

`PROJECT_OBSOLESCENCE` 的责任路径至少为 `CUSTOMER_SIDE`、`INTERNAL_SIDE`。

## 2. 固定判断顺序

1. 从 Report 1 取得超期 PO 和基础信息。
2. 从 Report 2 取得当前供需、候选项目集合及 Material → MPM。
3. 以 `forecast_anchor_date = order_date + material_lt_days`，从 Report 3 的统一 Forecast Version Calendar 选择 Baseline 与后续版本，推断最可能项目 List 和需求变化形态。
4. 若库存组织类型为试产，直接进入 `TRIAL`；所有此类记录交给物料 MPM，不做金额 TOP20 筛选。
5. 非试产且最可能项目有明显需求下修/延后：
   - EOL → `PROJECT_OBSOLESCENCE / CUSTOMER_SIDE`；
   - 非 EOL → `DEMAND_ADJUSTMENT`，再按预计消耗月数决定持续消耗或沟通供应商砍单。
6. 无明显需求下修/延后：
   - EOL 且未来存在持续、少量、非零需求 → `AFTER_SALES`；
   - 否则按 `order_date` 查询历史囤料版本：命中 → `STOCKPILE`；未命中 → `PROJECT_OBSOLESCENCE / INTERNAL_SIDE`。

不得交换上述优先级。尤其是：试产优先于其他证据；需求变化分支先于售后/囤料；售后判断先于历史囤料。

## 3. 通用生成前置条件

每个场景样本至少绑定：

- 一个 `dataset_version_id` 与固定 `snapshot_date`；
- 一个确实满足 `overdue_days > 0` 的 `po_line_schedule_id`，以及其父级 `po_line_id`；
- 一个 `material_id`、一个 `po_reference_project_id`；
- 至少一个可分析项目，且存在 `causal_project_id`；
- 统一 Forecast Version Calendar；
- 将同日版本按 `sequence_no` 归并后，Anchor 前最近一个有效最终 Baseline 和 Anchor 后 2～5 个有效最终版本；`is_valid=false` 永远跳过；
- Report 3/4/6 可追溯的统一 Underlying Demand Signal；
- Report 5 在 `snapshot_date` 时有效的项目生命周期；
- 按 `order_date` 可查询的 Stockpile Version 历史。

Generator 应有一部分样本满足 `po_reference_project_id != causal_project_id`，并保证两者都是该物料的有效或历史关联项目。不得让参考项目永远等于根因项目。

## 4. Ground Truth 合同

`scenario_truth` 仅供 Generator、Evaluation 与测试使用，至少包含：

| 字段 | 规则 |
|---|---|
| `scenario_id` | 内部稳定 ID |
| `dataset_version_id` | 所属企业世界 |
| `po_line_schedule_id` | 待评测的 Report 1 事实行；与 Report 1 一一对应 |
| `po_line_id` | 父级 PO 行 lineage |
| `scenario_pattern` | 下文八种 Pattern 之一 |
| `true_cause` | 只能映射到五类 `cause_type` |
| `true_cause_subtype` | REDUCTION/DELAY/MIXED/NONE 或场景所需子型 |
| `causal_project_id` | 真正证据最强项目，可不同于 PO 参考项目 |
| `demand_change_type` | REDUCTION/DELAY/MIXED/NONE |
| `lifecycle_state` | 生成时真值；必须能被 Report 5 证据支持 |
| `stockpile_flag` | 以 `order_date` 历史查询得到的真值 |
| `responsibility_type` | 至少 CUSTOMER_SIDE/INTERNAL_SIDE；试产可用 MPM |
| `expected_action` | 期望主对策；售后细化仍待业务确认 |

不得为方便测试而把这些字段复制到 Report View、普通 API Schema 或 Excel。

## 5. 场景总矩阵

| Scenario Pattern | Demand 变化 | snapshot 时 EOL | 未来少量持续非零 | order_date 历史囤料 | 最终 cause | subtype / responsibility |
|---|---|:---:|:---:|:---:|---|---|
| `TRIAL` | 任意但需保持同源 | 任意 | 任意 | 任意 | `TRIAL` | `MPM` |
| `DEMAND_REDUCTION` | REDUCTION | 否 | 不作为判据 | 否或非判定因素 | `DEMAND_ADJUSTMENT` | `REDUCTION` |
| `DEMAND_DELAY` | DELAY | 否 | 不作为判据 | 否或非判定因素 | `DEMAND_ADJUSTMENT` | `DELAY` |
| `DEMAND_MIXED` | MIXED | 否 | 不作为判据 | 否或非判定因素 | `DEMAND_ADJUSTMENT` | `MIXED` |
| `CUSTOMER_SIDE_PROJECT_OBSOLESCENCE` | REDUCTION/DELAY/MIXED | 是 | 低或 0；不得形成明确售后模式 | 非核心 | `PROJECT_OBSOLESCENCE` | `CUSTOMER_SIDE` |
| `AFTER_SALES` | NONE | 是 | 是 | 非判定因素 | `AFTER_SALES` | `NONE` |
| `STOCKPILE` | NONE | 是或否；必须不满足售后 | 不形成售后模式 | 是 | `STOCKPILE` | 按业务责任记录 |
| `INTERNAL_SIDE_PROJECT_OBSOLESCENCE` | NONE | 是或否；必须不满足售后 | 不形成售后模式 | 否 | `PROJECT_OBSOLESCENCE` | `INTERNAL_SIDE` |

“明显”“少量”“持续”的量化阈值不是企业硬规则。`DC-15` 在 Phase 4 标记为 `RESOLVED_AS_SYNTHETIC_CONFIG`：以下默认值只服务于 Synthetic Generator、Evaluation 与自动化测试，均可通过 `ScenarioGenerationConfig` 调整，不代表真实企业判断规则：

```text
comparison_months = 7
reduction_total_drop_ratio = 0.35
delay_near_term_months = 3
delay_near_term_drop_ratio = 0.30
delay_total_retention_lower = 0.85
delay_total_retention_upper = 1.15
delay_shift_share_min = 0.30
mixed_total_drop_ratio = 0.20
mixed_shift_share_min = 0.20
after_sales_level_ratio_min = 0.05
after_sales_level_ratio_max = 0.20
after_sales_min_nonzero_weeks = 8
after_sales_min_nonzero_months = 4
forecast_rounding_tolerance = 0.01
```

售后正式处置、保留量与保供周期仍属于 `NEEDS_BUSINESS_CONFIRMATION / DC-16`，不因上述 Mock 阈值固化而改变。

Phase 4 的默认 Planner 使用 coverage-first：先保证八种 Pattern 非零（试产由组织类型确定），以及 After-sales 的 `stockpile_flag=true/false` 覆盖，再按非负且总和为 1 的权重分配其余物料。权重为 0 不会取消强制覆盖；在项目生命周期约束过滤后，若某物料全部兼容 Pattern 权重为 0，则使用相同 seed 驱动的兼容集合等权抽样。没有兼容 Pattern 或基础世界无法满足强制覆盖时显式报错，不放宽生命周期或五类根因规则。这是 Synthetic 配置策略，不是业务判断优先级变更。

---

## 6. `TRIAL`

### Ground Truth

```text
true_cause = TRIAL
true_cause_subtype = NONE
responsibility_type = MPM
expected_action = 待MPM确认处理
```

### Report 证据

| Report | 必须生成的证据 |
|---|---|
| Report 1 | PO 确实超期；`inventory_organization_type=TRIAL`；数量关系有效；不出现原因字段 |
| Report 2 | 该 `material_id` 有且仅有一个在 snapshot 有效的 MPM 编号、姓名、部门；试产供需字段结构完整 |
| Report 3 | 生成合法且同源的历史 Forecast，避免出现断裂数据；其形态不得改变试产分支优先级 |
| Report 4 | 最新 13 周预测与 Report 3 同源；零需求时仍遵守 null/状态规则 |
| Report 5 | 参考/候选项目可关联到有效配置；生命周期不决定此场景最终类型 |
| Report 6 | 历史囤料数据可有可无，但不能让普通 API 暴露真值；试产优先于囤料命中 |

### 强制约束

- 所有试产超期 PO 都进入 MPM 处理，不按金额、数量或 TOP20 筛选。
- MPM 由 Material → MPM 取得，不能由 Project 推断。

---

## 7. `DEMAND_REDUCTION`

### Ground Truth

```text
true_cause = DEMAND_ADJUSTMENT
true_cause_subtype = REDUCTION
demand_change_type = REDUCTION
lifecycle_state = NPI | MASS_PRODUCTION
```

### 需求形态

- Baseline 在 causal project 的共同可比月份存在稳定/较高需求。
- Anchor 后版本在相同月份窗口的需求总量显著下降。
- 下降不能主要由数量移到更远月份解释；否则属于 DELAY/MIXED。
- 同物料其他项目可以有噪声，但 causal project 的证据强度必须最高。

### Report 证据

| Report | 必须生成的证据 |
|---|---|
| Report 1 | 量产 PO、有效超期数量、参考项目可与 causal project 不同 |
| Report 2 | 供需组件自洽；项目集合包含 causal project；Material → MPM 可解析 |
| Report 3 | Anchor 前 Baseline + 后续版本连续有效；causal project 在可比窗口总量下降且无等量后移；源表不写 REDUCTION 标签 |
| Report 4 | 最新物料级 13 周需求体现下修后的较低水平，不得仍凭空极高 |
| Report 5 | causal project 在 snapshot 时明确非 EOL |
| Report 6 | 按 order_date 查询可不命中囤料；无论是否有非核心记录，都不能覆盖需求调整分支 |

### 对策真值

- `estimated_consumption_months < 6` → 持续消耗。
- `estimated_consumption_months >= 6` → 沟通供应商砍单。
- 13 周需求为 0 时消耗月数为 null；其对策映射须按最终业务配置执行，不伪造数值。

---

## 8. `DEMAND_DELAY`

### Ground Truth

```text
true_cause = DEMAND_ADJUSTMENT
true_cause_subtype = DELAY
demand_change_type = DELAY
lifecycle_state = NPI | MASS_PRODUCTION
```

### 需求形态

- Anchor 后版本的近期月份需求下降。
- 需求在更远月份重新出现；足够长的比较窗口内，总量大体保持，主要变化是时间后移。
- 不得只把所有需求同比缩小；那是 REDUCTION。

### Report 证据

| Report | 必须生成的证据 |
|---|---|
| Report 1 | 与 Reduction 相同的合法量产超期 PO 基础 |
| Report 2 | 项目集合含 causal project；供需数据与延后后的当前状态相容 |
| Report 3 | Baseline 的近期需求在后版本向更远月桶移动；总量保持在配置容差内；不预填 DELAY |
| Report 4 | 13 周内需求可下降，但更远月的 Report 3 仍保留需求；两者不矛盾 |
| Report 5 | causal project 非 EOL |
| Report 6 | 未来半年需求与同源延后形态相容；历史囤料不参与最终分类优先级 |

---

## 9. `DEMAND_MIXED`

### Ground Truth

```text
true_cause = DEMAND_ADJUSTMENT
true_cause_subtype = MIXED
demand_change_type = MIXED
lifecycle_state = NPI | MASS_PRODUCTION
```

### 需求形态

- Anchor 后版本既发生总量净下降，又有部分需求向后移动。
- 下降部分与延后部分必须都超过最终确认的各自阈值，不能把纯 Reduction/Delay 标成 Mixed。

### Report 证据

| Report | 必须生成的证据 |
|---|---|
| Report 1 | 合法量产超期 PO |
| Report 2 | 项目集合与供需状态自洽 |
| Report 3 | causal project 同时呈现近期减少、远期回补和净总量下降；源表不写 MIXED |
| Report 4 | 最新 13 周反映近期下降后的需求，不与远期回补相冲突 |
| Report 5 | causal project 非 EOL |
| Report 6 | 未来半年需求由同一混合 Demand Signal 派生；历史囤料不覆盖需求变化分支 |

---

## 10. `CUSTOMER_SIDE_PROJECT_OBSOLESCENCE`

### Ground Truth

```text
true_cause = PROJECT_OBSOLESCENCE
demand_change_type = REDUCTION | DELAY | MIXED
lifecycle_state = EOL
responsibility_type = CUSTOMER_SIDE
expected_action = 沟通客户处理呆滞
```

### Report 证据

| Report | 必须生成的证据 |
|---|---|
| Report 1 | 量产且超期，不暴露 EOL/原因/责任路径 |
| Report 2 | causal project 在候选项目集合中，供需数量自洽 |
| Report 3 | causal project 在 Anchor 后存在明确需求下修/延后/混合证据 |
| Report 4 | 最新需求与项目变化后的物料聚合相容，通常较低或为 0 |
| Report 5 | causal project 在 snapshot 时生命周期映射为 EOL；事业部、计划部门、客户均可解析 |
| Report 6 | 可有历史记录，但不得改变“需求变化 + EOL”优先判定；普通查询不能返回 CUSTOMER_SIDE 真值 |

### 强制区分

此场景不是 After-sales：它先满足“明显需求变化”，因此按判断顺序进入客户侧项目呆滞。未来残余需求不得被造得足以成为清晰的售后持续模式。

---

## 11. `AFTER_SALES`

### Ground Truth

```text
true_cause = AFTER_SALES
true_cause_subtype = NONE
demand_change_type = NONE
lifecycle_state = EOL
```

### 需求形态

- Anchor 前后 Forecast 不存在达到“明显”阈值的突发 Reduction/Delay/Mixed。
- 项目已 EOL。
- 未来多个周/月桶持续出现少量且非零的需求；不能只在一个桶出现孤立尖峰。

### Report 证据

| Report | 必须生成的证据 |
|---|---|
| Report 1 | 量产超期 PO；不出现售后/EOL标签 |
| Report 2 | 项目集合含 causal project；当前供需与低量保供场景相容 |
| Report 3 | 跨版本无明显突发变化；未来月持续有小量需求 |
| Report 4 | 13 周内多个周桶为小量非零，而非全 0 或一次性尖峰 |
| Report 5 | causal project 在 snapshot 时为 EOL，客户/组织可解析 |
| Report 6 | 历史囤料命中与否不参与此分支判定；未来月需求与 Report 3/4 同源 |

### 参数与待确认边界

“少量”“持续”的默认 Mock 阈值已按 `DC-15 / RESOLVED_AS_SYNTHETIC_CONFIG` 在 `ScenarioGenerationConfig` 固定并保持可配置，不作为真实企业硬规则。保留量、保供周期和正式售后对策仍为 `NEEDS_BUSINESS_CONFIRMATION / DC-16`；确认前 `expected_action` 不得写入未经批准的细化方案。

---

## 12. `STOCKPILE`

### Ground Truth

```text
true_cause = STOCKPILE
demand_change_type = NONE
lifecycle_state = EOL | NPI | MASS_PRODUCTION
stockpile_flag = true
```

### Report 证据

| Report | 必须生成的证据 |
|---|---|
| Report 1 | 量产超期 PO；`order_date` 可用于历史版本查询 |
| Report 2 | 项目/供需/MPM 信息完整；通常呈供应盈余，但最终是否要求 >0 需以业务口径为准 |
| Report 3 | causal project 无明显 Reduction/Delay/Mixed；不满足售后分支 |
| Report 4 | 13 周需求与最新 Demand Signal 一致，支持预计消耗月数或 NO_FORECAST_DEMAND |
| Report 5 | causal project 可为 EOL 或非 EOL；若为 EOL，未来需求必须不满足“持续少量非零”的 After-sales 条件 |
| Report 6 | `order_date` 当天或之前最近有效版本存在该 material；有效囤料条件满足；版本后的未来月需求同源 |

### 历史版本要求

- 至少再生成一个 snapshot 后的新版本，用于证明“当前最新版本”可能与下单时版本不同。
- 查询必须仍选择 `order_date` 之前最近有效版本。
- 若该历史版本无记录，不能仅因当前版本有记录而判为 Stockpile。

### 对策真值

- `estimated_consumption_months < 6` → 持续消耗。
- `estimated_consumption_months >= 6` → 沟通供应商砍单。
- Report 6 模板“13 周无 Forecast 需求”的具体动作与主判断树需保持一致并由业务方确认。

---

## 13. `INTERNAL_SIDE_PROJECT_OBSOLESCENCE`

### Ground Truth

```text
true_cause = PROJECT_OBSOLESCENCE
true_cause_subtype = NONE
demand_change_type = NONE
lifecycle_state = EOL | NPI | MASS_PRODUCTION
stockpile_flag = false
responsibility_type = INTERNAL_SIDE
expected_action = 沟通事业部处理呆滞
```

### Report 证据

| Report | 必须生成的证据 |
|---|---|
| Report 1 | 量产、合法超期、无答案泄漏 |
| Report 2 | 供需/项目集合自洽；可显示长期盈余风险 |
| Report 3 | causal project 无明显 Reduction/Delay/Mixed，不得伪造客户侧需求突变 |
| Report 4 | 未来需求不形成“EOL + 持续少量非零”的售后模式 |
| Report 5 | lifecycle 可为 EOL 或非 EOL；若为 EOL，未来需求必须不满足 After-sales 条件 |
| Report 6 | 按 order_date 选择的最近有效历史版本中无该 material 的有效囤料记录 |

### 强制区分

- 与 Customer-side 呆滞的区别：没有明显需求下修/延后，因此不进入“需求变化 + EOL”的 CUSTOMER_SIDE 分支。
- 与 Stockpile 的区别：下单时历史囤料版本未命中。
- 与 After-sales 的区别：不满足“EOL + 未来持续少量非零需求”；这不等价于必须非 EOL。

---

## 14. Underlying Demand Signal 同源规则

Generator 必须先生成 `project × material × time` 的底层需求，再通过确定性变换派生：

```text
Underlying Demand Signal
├─ Forecast Version 观测/版本化 → monthly_forecasts → Report 3
├─ snapshot 最新聚合 + 周拆分 → weekly_forecasts → Report 4
└─ Stockpile Version 观察窗口 → stockpile_forecasts → Report 6
```

必须保存可测试的 lineage 键或生成批次引用，使任一 Report 3/4/6 行可回溯到 Demand Signal。允许因粒度转换产生舍入差，但舍入方法与容差必须配置化、可测试；不得独立调用三个随机函数生成三张表。

## 15. 场景间负证据

为保证判断树可评测，每个 Pattern 除正证据外还要生成排除更高优先级分支的负证据：

| Pattern | 必须排除 |
|---|---|
| TRIAL | 无需排除其他分支，因试产优先 |
| Demand 三类 | 排除试产；Report 5 非 EOL |
| Customer-side Obsolescence | 排除试产；有需求变化；EOL |
| After-sales | 排除试产与明显需求变化；满足 EOL + 未来持续少量非零，历史囤料不作为判定因素 |
| Stockpile | 排除试产、明显需求变化与售后；历史囤料命中 |
| Internal-side Obsolescence | 排除试产、明显需求变化、售后与历史囤料 |

## 16. 场景覆盖最低要求

- 八种 Pattern 每种至少有正样本。
- REDUCTION/DELAY/MIXED 必须各有多个版本、跨月/跨年边界样本。
- 至少一个 Forecast Baseline 恰好在 Anchor 前一天，另一个有无效版本夹在中间。
- 至少一个 Stockpile Version 与 `order_date` 同日；另一个需回溯到更早版本。
- 至少一个 13 周总需求为 0 的样本。
- 至少一个 `po_reference_project_id != causal_project_id` 的非试产样本。
- 至少一个物料服务多个项目，且只有一个项目呈主要因果证据。

## 17. Phase 5A Evidence Foundation 实现口径

本节记录原 Phase 5A checkpoint；源修订时间与数量状态的现行实现以第 18 节为准。

Phase 5A 只生成 Lifecycle、Product Config、共享日需求及中性源修订；不生成 Forecast Version、月/周 Forecast、Supply/Demand、Stockpile、Report View/API。

生命周期严格服从 Phase 4 的 project requirements；其余项目按 seed 生成 NPI → MASS_PRODUCTION → EOL 的合法前缀历史。snapshot 恰有一个 stage；不得重选 required project 的生命周期。

### 源需求观测，不是 Forecast Calendar

每个 Material × Project 恰有一条日需求 Signal；从最早相关 Anchor 前至少两个月及最早下单日前一月起覆盖至 snapshot 后八个月。初始日点加 `demand_signal_revisions` 形成可按观察日读取的统一数量序列。

为每个物料的相关 Anchor 创建源计划周期：相邻间隔不超过两天的 Anchor 归为一组，组首前一天为预算刷新观察日，组末后一天为修订观察日；共同可比窗口从组首所在月月首开始。刷新与修订均只保存日期和绝对数量，并且同一物料的所有候选项目使用相同观察日期及完整日粒度覆盖，不以“只有一个项目有修订记录”暗示 causal project。

这些日期仅是 Synthetic source revision basis，不取代既定 Forecast Anchor 公式、Monday-start 或共享周版本选择规则。Phase 5B 必须另外验收每个 PO 的真实 Forecast Baseline/后续 2～5 版本；Phase 5A 的源观测对验收不能宣称为该项已通过。

`EvidenceFoundationConfig` 默认：seed=20260829，版本=5A.1.0/schema=008，历史至少2月、未来8月，每项目2个配置，正常日量40～120，日内数量噪声±2%，周期预算保留系数0.90。以下是造数幅度，不是重新定义 `DC-15` 阈值：

- Reduction：源修订后未来数量减少55%，无远期回补；
- Delay：将近3个月数量的80%移至其余比较月份，7个月总量精确保留；
- Mixed：移走近端数量的30%并永久减少整个7个月总量的25%，同时保留可观测远期净增加；无法同时满足约束的配置显式失败；
- Customer-side：按 Truth 的上述三种形态生成，并遵守项目 EOL；
- After-sales：数量相对正常日量参考取 Phase 4 已确认 min/max 的中值（默认12.5%），连续13周/6月非零，源观测前后不调整；
- Stockpile/Internal-side：causal 项目使用稳定零需求，不构成 Demand Adjustment，也排除 EOL 售后；历史囤料事实仍留 Phase 5C；
- Trial：合法稳定日需求，其数量形态不改变试产优先级；
- 非 causal 项目：稳定正常需求及轻微日噪声。调整分支的 causal 数量变化得分严格更大；售后/稳定零量分支以量级差异形成可观测证据，不要求凭空产生 Forecast 下修。

Validation 只在 Generator/Evaluation 中比较数量证据：`drop=1-after_total/before_total`、`near_drop=1-after_near/before_near`、`shift=max(after_far-before_far,0)/before_near`。调整强度为正向 drop、near_drop 与 shift 之和；阈值始终来自传入的 `ScenarioGenerationConfig`。持久化 platform 不保存这些分型或得分。

Evidence 服务先按各阶段原配置重建预期 Master/Procurement/Scenario 并与现存内容比对，只读验证前置完整性，不调用上游生成服务去补数据。六张 Evidence 表在同一事务中写入；全空时生成、完整且哈希一致时复用、部分存在时拒绝。最终 Dataset 继续 `GENERATING`，不得写 `business_content_hash`。

## 18. Phase 5A.1：持续有效的源计划状态

根因是原始周期预算恢复与扣减围绕 Anchor 集中在几天内；周度发布经常同时跳过预算恢复而只观察两次扣减后的值。改发布星期不能解决多 Anchor 的状态冲突。

现行 `revision_timing_version=PERSISTENT_1`：每个不同 Anchor 是一个 source planning event，数量状态自 Anchor 当日生效，持续到下一事件；没有临时预算恢复。所有候选项目沿用同一物料事件日，不用记录是否存在暗示 causal project。Anchor 同日 Forecast 仍既非 Baseline 也非 post。

同物料的多个事件联合构造非负计划状态，不能反复从原始均匀预算独立扣减。Generator-only 线性约束构造器覆盖每个 Anchor 前 14 天内可能的 Baseline、之后 42 天内的状态：包含七种周度偏移、最多五个 post、最近 Baseline 或首个 post 无效时跳过一周。约束直接复用 `ScenarioGenerationConfig`，生成采用比阈值严格 0.01 的数值余量，而非降低阈值。Delay 比较窗口总量保持相等，Reduction 不增加远期量，Mixed 同时满足净减少与远期移量；无解直接拒绝，不修改 Truth 或阈值。

为满足重叠事件，调整分支的初始计划月度分布及后续状态一起求解，目标尽量接近均匀预算。计划覆盖原 Anchor 七个月窗口的并集；并集之外的未来调整项目计划为零，历史早期日点保留。日内按原 seeded 权重用最大余数法分配，Decimal 月合计精确守恒。它们仍是同一个源 Demand World，不是独立生成 Forecast。稳定分支、售后持续小量与其他候选项目的原始日需求保持不变。

原 `reduction_drop_ratio` 等五个脉冲幅度字段只保留默认值以维持 Phase 5A 实体 identity signature；非默认覆盖显式拒绝，避免静默忽略。实际业务判据仍唯一来自 Scenario config，`reduction_total_drop_ratio=0.35` 等值未改。新 timing version 进入内容 signature；独立旧 identity signature 保留 Lifecycle、Config、Signal、Point 的既有 ID。

`DemandObservationIndex` 不读取未来修订，也不依赖 weekday、PO 或 Truth。Schema 008 已支持该状态模型，无 migration 变更。正式 Forecast Calendar/WindowSelector 仍属于 Phase 5B，本节只固化源状态及 publication dry-run。

## 19. Phase 5B 的真实 Forecast 版本证据

ForecastGenerator 只接收 Master、共享 Evidence 和 Forecast 配置，不读取 Scenario Truth，也不重新生成 Demand。ForecastValidator 独立读取隔离 Truth，按每个 schedule 的真实 Anchor，从共享版本表先过滤无效、归并同日最终版本，然后取严格前 Baseline 和最多5个严格后版本；其2～5版前缀均可查询。

比较窗口固定为 Anchor 所在月起的7个自然月。月事实保留必要前后重叠桶，避免拿两个滚动展示窗口的不同月份当作需求变化。Reduction/Delay/Mixed/NONE 判据只复用 `ScenarioGenerationConfig`；Mixed 同时要求净减少和移量，纯 Reduction/Delay 反例继续拒绝。Customer-side 按原 Truth 中的变化子型校验，所有其他项目同样有事实，调整项目证据强度须严格最高。

`ForecastGenerationConfig` 固定 V1 7日周频、默认后3版/允许2～5、展示7个月、13周、数量4位小数；seed默认20260830，仅用于发布有效性/补发夹具及生成签名，不改源需求。补发偏好0.12、无效日偏好0.07；至少覆盖同日有效修订与高序号无效回退，整日无效日期间隔至少7周，保证任意6周窗口至多跳过一版。所有版本日在 dataset snapshot 当天或之前，默认连续星期一 Calendar。

最新13周来自 snapshot 源观察，项目周合计精确组成物料周值；完整自然月与最新有效月预测在原舍入容差内对账。Demo 必须包含物料级全零13周，当前仅提供合计/周均安全计算，不实施 PO 消耗对策。After-sales 与 NONE 保持原稳定源状态。
