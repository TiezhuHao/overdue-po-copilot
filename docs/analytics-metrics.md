# System B Phase 1B — deterministic analytics

只计算数值和可计算性，不解释原因、不判断责任、不产生采购建议。输入仅来自已有 Canonical Models 或从这些对象显式提取的 date / Decimal / WeekForecast；不读取 HTTP、数据库、配置 URL 或机器日期。不修改 System A API、数据生成器、迁移、业务数据或 Phase 1A DTO/mapping。

## Implemented

| Metric | Formula | Canonical inputs | Unit | Null / edge semantics |
|---|---|---|---|---|
| `po_age_days` | as_of_date − order_date | PurchaseOrder.order_date；服务传 snapshot_date | 天，整数 | order/as_of/LT 缺失则不可算；as_of 早于下单日、负 LT、非 date 输入拒绝 |
| `threshold_days` | material_lt_days + 180 + 60 | PurchaseOrder.material_lt_days | 天，整数 | 等价于既有 LT + 240，无新业务阈值 |
| `threshold_date` | order_date + threshold_days | 同上 | date | date 溢出不可算；不是 due_date |
| `threshold_delta_days` | po_age_days − threshold_days | 同上 | 天，有符号 | 阈值前为负，当天为 0，越过阈值为正；与基线 overdue_days 公式一致，不截断 |
| `days_to_threshold` | max(threshold_days − po_age_days, 0) | 同上 | 天，非负剩余天数 | 阈值前一天为 1，当天及以后为 0 |
| `days_beyond_threshold` | max(po_age_days − threshold_days, 0) | 同上 | 天，非负越界天数 | 阈值当天及以前为 0，后一天为 1 |
| `observed_forecast_qty` | sum(已提供的合法周桶) | WeekForecast.forecast_qty | 同物料数量单位 | 不补零；没有桶时为 null；重复 index、负数量等不输出可信合计 |
| `total_forecast_qty` | sum(第 1…13 周数量) | WeeklyForecastSnapshot.weeks | 同物料数量单位 | 必须 13 个唯一完整周桶，否则 null |
| `average_weekly_demand_qty` | total_forecast_qty / 13 | 同上 | 数量/周 | 窗口不完整则 null；完整零需求为 0 |
| forecast window | expected=13；observed=已提供桶数；显式完整日期才给 [start, end) | WeekForecast.week_index / week_start_date | 周数、date | 不从 dataset 日期伪造源周日期；全缺日期时仍可计算完整 13 周数量指标 |
| `estimated_consumption_weeks` | open_qty / average_weekly_demand_qty | R4 open_po_qty 或经身份验证的 R1 overdue_open_qty；13 周桶 | 周 | 正需求且 open=0 得 0；零需求（包括 0/0）返回 null + NO_FORECAST_DEMAND；缺失/负数量不算 |
| `supply_demand_surplus_qty` | all_supply_qty − actual_demand_total_qty | MaterialSupplyDemand 对应两项，由 System A 返回 | 同物料数量单位 | 基于上游 reported all_supply_qty 的差值；正数为盈余，负数为缺口，0 为平衡，不表示 confirmed / committed / planned supply |
| `inventory_coverage_weeks` | available_inventory_qty / average_weekly_demand_qty | R4 good_subinventory_qty 与同一行的 13 周桶 | 周 | 不含 defective 库存；缺失、负库存、缺预测、不完整窗口、零需求均不给 ratio |
| `forecast_change_qty` | current.forecast_qty − previous.forecast_qty | 两个显式 ForecastSnapshot，同一自然月 | 同物料数量单位 | 只有满足下述身份、范围、时间条件才算 |
| `forecast_change_rate` | forecast_change_qty / previous.forecast_qty | 同上 | 无量纲倍数 | −0.62 表示 −62%；previous=0 时仅差值可算，rate=null + ZERO_DENOMINATOR，即使 current 也为0 |

### Numeric and date semantics

- 数量输入必须为有限、非负 Decimal；盈余和变化量允许负值。低层标量函数不自动把 float、负数、NaN、Infinity 或 null 当 0。Canonical 校验本就拒绝的字段（如 null 的核心数量、非整数 LT、null 周数量）在入口抛 Pydantic ValidationError；允许的缺失参数则用 availability 表达。
- 使用独立 Decimal Context：40 位有效数字、ROUND_HALF_EVEN，结果不受调用者 Decimal 精度、rounding、trap 影响。不做金额四舍五入。40 位是运算表示精度，不是业务阈值。
- 消耗与覆盖实际计算 `quantity * 13 / total`，数学上等价于除以周均，避免把循环小数周均作为中间舍入结果再除一次。total/average 从周桶重算，不信任或累加上游展示汇总。
- 消耗/覆盖结果超过13周时，仅表示按当前窗口均值的比例估计，不代表已有13周以后的 Forecast，也不生成消耗完成日期或到货时序。
- `calculate_po_aging` 必须显式传 as_of_date；服务固定传 PO.snapshot_date。纯函数可用于显式历史日期，但不声称还原当时收到数量/Forecast。服务不使用 due_date 或上游 overdue_days 替代原始时间输入。
- 13 周必须 index=1…13 且无重复，输入顺序可乱但不能缺桶。纯窗口函数接受 Canonical WeekForecast 序列，因此可以表达一个未完整收集的窗口；不放宽 Phase 1A 对完整 WeeklyForecastSnapshot 的 13 项校验。
- 周日期全为 null 仍兼容旧 API，不阻止基于13个完整index的数量/周指标。Phase 1C已公开源周日期。若提供日期，则必须全部提供、Monday-start、连续相隔7天；部分提供视为不完整窗口。完整日期输出结束日为最后周起日+7天（exclusive）。
- 每个物料沿用其来源数量单位；UOM 尚未公开，不做跨物料合计或单位换算。低层标量函数不会自行关联实体，调用者必须提供同一物料/单位的分子与周桶。

## Identity and service boundary

`AnalyticsService.analyze_material_forecast(forecast)` 使用 **同一个** WeeklyForecastSnapshot 中的 open_po_qty、good_subinventory_qty 和 weeks，故无需猜测跨表 Join，可直接用于当前 REST 返回值。它输出物料总 open PO 的消耗，不是某条超期 PO 的消耗；也不是到货时序模拟或 MRP。

`AnalyticsService.analyze_purchase_order(po, forecast=None)` 输出 schedule 粒度标识、年龄和条件成立时的 PO 消耗。跨记录必须同 dataset、同 snapshot、非空且相同的 material_id / organization_id；不能按物料名称或编码补 ID。Phase 1C已公开这些ID，现有算法可消费真实REST配对；旧响应缺ID仍为MISSING_STABLE_ID（未提供Forecast则MISSING_FORECAST）。不把未经验证的Forecast附到该PO的计算结果中。

`calculate_supply_demand(source)` 只处理一条 R2 canonical row。nullable PR 以原值保留为来源信息，不加入源 all_supply，既有 open_po_qty 已含 OPEN_PO + IN_TRANSIT，不能再加一次在途量；IN_TRANSIT 不是 ASN。R2 实际需求是既有近端源窗口，与 13 周 Forecast 不是同一个分母。

该供需差仅使用 System A reported `all_supply_qty`，不赋予 confirmed、committed 或 planned supply 含义。confirmed / planned supply composition 仍是未确定的 Contract Gap。

服务不获取数据、不自动分页、不自动挑 Forecast 或拼接项目。未新增 FastAPI endpoint；调用方先经现有 Adapter 获取 canonical 对象，再调用纯函数或服务。

## Conditional Forecast change

`calculate_forecast_change(previous, current)` 本次实现的是**同一明确自然月的数量差/率**，不是 rolling 七个月 total 变化，也不是需求下修/延后识别。R3 的 total 在每个月行重复，不能跨月累加；每版 M0…M+6 窗口还会随版本日期移动，不能拿两个滚动总量直接比较。

必须同时满足：

1. 两条记录存在，material_id、project_id、forecast_version_id 全部非空。
2. 同 dataset / snapshot / material ID / project ID / po_line_schedule_id / forecast_month，月份为月首日。
3. 显式 previous.version_date < current.version_date <= snapshot_date，两个 version ID 不同。
4. 数量合法，保持同一物料的来源单位。

现有函数仍拒绝同日不同版本，不按UUID大小、数组顺序、版本名称或BASELINE/POST标签排序。Phase 1C公开稳定身份与sequence，使真实REST中严格不同日期、同物料/项目/月份的显式pair可计算；本轮没有修改Analytics或新增自动挑版功能。R3每个版本日只公开最终有效修订，完整版本目录/任意horizon仍不在当前契约内。

## Availability semantics

分组输出使用 status + reason_codes，数值字段保持普通 Decimal/int/null，不为每个 primitive 创建对象。

| Status | Meaning |
|---|---|
| AVAILABLE | 该组数值指标可完整计算；合法 0 与 null 不同。周日历元数据缺失不改变完整 index 窗口的数值可用性 |
| PARTIAL | 仅部分指标/证据可用，例如观察到12周、完整零需求导致 ratio 不可算、previous=0 但差值可算、源供需可算但 confirmed/planned 被阻塞 |
| NOT_COMPUTABLE | 缺少可用预测/所需字段、输入非法、身份或版本不可比较，不能输出该组可信核心计算值 |

消费方应同时查看所需具体数值是否 null，不能把 PARTIAL 当成 ratio 已就绪。coverage 在库存覆盖可用时仍为 PARTIAL，因为 confirmed/planned coverage 尚不可算。

| Reason code | Meaning |
|---|---|
| MISSING_REQUIRED_FIELD | 缺下单日、LT、as_of、数量或对象 |
| INVALID_INPUT | 负数量、非有限/非 Decimal 标量、负 LT、倒置日期等非法输入 |
| MISSING_FORECAST | 未提供 Forecast/周桶或一个待比较版本 |
| INCOMPLETE_FORECAST_WINDOW | 桶缺失/空窗口或仅提供部分源周日期，不做外推 |
| INVALID_FORECAST_WINDOW | 周 index 重复/越界、日期不连续或非 Monday-start |
| NO_FORECAST_DEMAND | 完整13周需求为零，消耗/覆盖分母为0 |
| MISSING_STABLE_ID | 不能核验物料、组织、项目或版本身份 |
| INCOMPATIBLE_SCOPE | dataset、snapshot、稳定实体或 horizon 不一致 |
| INCOMPARABLE_FORECAST_VERSIONS | 缺版本身份、时间不明确、同日修订、倒序或范围不同 |
| ZERO_DENOMINATOR | 前版数量为0，变化率不可算；不阻止计算绝对差值 |
| UNCONFIRMED_SUPPLY_COMPOSITION | 现有契约尚未定义 confirmed/planned 供应集合及承诺语义 |

## Blocked by upstream contract

Phase 1B未改上游；下表按Phase 1C证据增强后的实际状态更新。没有新增Analytics算法：

| Blocked metric | Why / missing contract |
|---|---|
| overdue amount | B-G02：缺 PO 单价与币种；不借协议价，不默认货币，不计算伪金额 |
| 金额型project exposure Top 3 | Phase 2C已实现数量贡献ranking和唯一top，不提供金额exposure或责任归属 |
| 任意Anchor/完整Forecast版本目录 | Phase 2C可比较R3已选Baseline/Post窗口；仍无完整目录/任意Anchor或额外重叠月份，不自动猜测版本 |
| REST的PO级consumption（身份阻塞已解除） | R1/R4已提供material/organization ID，既有算法可按同dataset/snapshot/identity使用；缺证据仍按原availability处理 |
| confirmed_supply_qty / planned_supply_qty | B-G07：PR/ASN可空，IN_TRANSIT不是ASN，open PO已含在途；缺供应承诺状态、组成、排重和单位语义，不能强套 inventory + ASN + PO (+ PR) |
| confirmed/planned gap 与 coverage | 依赖上一项；不把 all_supply 偷换成 confirmed，也不把 PR 当成确认供应 |
| 周窗口实际日历日期（已解除） | B-G06已提供weekly snapshot ID/date与周日期；旧接口响应无日期时仍不伪造 |

原有 NEEDS_BUSINESS_CONFIRMATION 事项不在本阶段解决。没有新增最终原因类型、业务阈值或责任路径。

## Phase 2C neutral evidence metrics

新增`analytics/evidence_metrics.py`，沿用40位ROUND_HALF_EVEN局部Decimal context，不改变原指标公式，不读取业务Policy或输出业务原因。

### Project contribution aggregation

`calculate_project_exposure(weekly)`接收一条Canonical R4，要求完整13周、Monday-start日期、快照/源版本/物料/组织ID，以及每个贡献项目完整13个周桶。每周项目合计必须精确等于物料周需求；缺桶不自动补零，不用宽表展示总量替代逐周核验。

| Metric | Formula / units |
|---|---|
| total_contribution_qty | 项目13周qty求和；物料Canonical数量单位 |
| contribution_share | 项目合计 / 物料13周合计；无量纲 |
| average_weekly_qty | 项目合计 / 13；qty/week |
| nonzero_week_count | qty>0的周桶个数；weeks |
| longest_nonzero_run | 按week index排序的最长连续非零周数；weeks |
| top_contributing_project | 唯一且正贡献的最大项目ID；不是责任项目 |

排名按数量降序；UUID仅使并列项展示顺序稳定，不用于选胜者。并列第一：PARTIAL + AMBIGUOUS_TOP_PROJECT，保留ranking但top为空。全零：NOT_COMPUTABLE + NO_POSITIVE_PROJECT_DEMAND，share为空；没有无穷大或sentinel。

缺事实/ID、无效周历、项目桶不完整、项目与物料数量不对账分别返回MISSING_PROJECT_CONTRIBUTIONS、MISSING_STABLE_ID、INCOMPLETE_FORECAST_WINDOW/WEEKLY_WINDOW_MISMATCH、INCOMPLETE_PROJECT_WINDOW、PROJECT_CONTRIBUTION_TOTAL_MISMATCH等稳定原因码。未知值不作零。

### Aligned Forecast totals and later-period matching

`calculate_anchor_comparisons(po, project_id, history)`只消费显式R3 Canonical长表行。要求同dataset/snapshot/material/schedule/project，位置0的Baseline严格在order+LT之前，连续位置1..N（N=2..5）在Anchor之后、不晚于snapshot；版本ID各异，日期严格递增，同一版本metadata一致。每版完整包含声明的7个自然月，月份不重复、不补零。所有提供版本共同月份至少2个；业务Policy还可以要求更长窗口。

用所有提供版本的共同月份集合（升序）逐一比较Baseline与每个Post：

| Metric | Formula / units |
|---|---|
| aligned_previous_total / aligned_current_total | 共同月份的previous/current qty之和；qty |
| per-period change_qty | current_qty - previous_qty；qty |
| total_change_qty | aligned_current_total - aligned_previous_total；qty |
| total_change_rate | total_change_qty / aligned_previous_total；无量纲，分母0时null |
| later_shift_qty | 按月先后将较早负差与之后正差匹配的数量；qty |
| later_shift_share | later_shift_qty / aligned_previous_total；无量纲，分母0时null |

后移匹配的严格算法：初始化`earlier_deficit=0, shift=0`。每月delta<0时，将`-delta`加到earlier_deficit；delta>0时，`matched=min(earlier_deficit, delta)`，加入shift并从earlier_deficit扣减；delta=0不改变状态。之后的亏缺不能匹配之前的盈余。因此纯总量缩减（没有后续回补）或反向前移的shift为0。算法只是数量形态证据，不证明真实需求搬迁，也不直接输出DELAY或MIXED。

保留每月previous/current/change和两版ID/date及Post位置；完整版本序号、Anchor和horizon通过原始history事实保留于provenance。重复/缺月、版本位置缺口、时间/身份冲突或无共同窗口均NOT_COMPUTABLE，不通过数组顺序或ID大小猜先后。

规则层的数量阈值由调用者另行提供；此模块不含显著下降、售后或责任评分。当前无UOM换算，所有跨记录数量必须属于同一物料的Canonical单位。

## Usage and tests

```python
from app.system_b.analytics.service import AnalyticsService
from app.system_b.analytics.calculations import calculate_supply_demand

# po, weekly_forecast, supply_demand are canonical objects from the existing adapter.
po_result = AnalyticsService.analyze_purchase_order(po, weekly_forecast)
material_result = AnalyticsService.analyze_material_forecast(weekly_forecast)
supply_result = calculate_supply_demand(supply_demand)
```

`python -m pytest tests/test_system_b_analytics.py -q`：纯函数、服务、身份边界、固定日期、Decimal context 隔离及依赖约束；不需要网络或数据库。
