# System A Acceptance Tests

## 1. 目的与执行门禁

本文件定义未来实现的自动验收合同。测试分为 unit、integration、contract、acceptance 和 static scan。只有确实依赖 `NEEDS_BUSINESS_CONFIRMATION` 的测试才标记为显式 blocked/xfail（附问题 ID）；已确认项必须转为可执行断言，已授权延后至 Generator 的事项标记为 deferred 而不是 Phase 1 blocked。

System A 完成的最低条件：

- 全部非 blocked 测试通过；
- 业务确认项已转成明确规格与测试；
- 六张 Report View/API 可从同一 dataset 查询一致证据；
- 普通 API/数据库角色无法访问 Ground Truth；
- 相同输入的业务内容哈希完全一致。

## 2. 测试数据与比较规范

### 2.1 确定性输入

测试签名至少包含：

```text
random_seed
snapshot_date
generator_version
schema_version
canonical generation_config
```

仅比较业务内容时排除 `generated_at`、运行耗时、日志 ID 等非业务运行元数据。所有表按稳定主键排序、Decimal 规范化、JSON key 排序后计算哈希。

### 2.2 最小场景夹具

至少包含八种 Pattern：TRIAL、DEMAND_REDUCTION、DEMAND_DELAY、DEMAND_MIXED、CUSTOMER_SIDE_PROJECT_OBSOLESCENCE、AFTER_SALES、STOCKPILE、INTERNAL_SIDE_PROJECT_OBSOLESCENCE。

另外必须有：跨年 Forecast、13 周需求为 0、无效版本夹在 Anchor 附近、order_date 同日 Stockpile Version、PO 参考项目与根因项目不同、多项目共用物料。

---

## 3. Dataset 与可重复性

### `AT-001` 相同输入生成相同业务世界

**Given** 两个隔离数据库使用相同确定性输入。  
**When** 分别完整生成 dataset。  
**Then** 所有 platform 业务表规范化哈希相同，稳定实体 ID 相同，六张 Report 输出哈希相同。

### `AT-002` 非业务时间不破坏复现

两次生成的 `generated_at` 可以不同；排除运行元数据后的业务哈希必须相同，`business_content_hash` 相同。

### `AT-003` seed 变化产生不同世界

只改变 seed，生成签名和至少一个业务实体/事实内容必须不同；仍满足全部约束。

### `AT-004` snapshot_date 是确定性输入

只改变 snapshot_date，应产生不同 signature；所有“当前”Report 使用新 snapshot，不读取机器日期。

### `AT-005` dataset_version 隔离

同库生成 A/B 两个 dataset。任何 Report 以 A 查询时不得出现 B 的 ID/业务行；所有复合 FK 不能跨 dataset 建立。

### `AT-006` dataset/forecast/stockpile 版本分层

一个 dataset 内可有多个 forecast_version 和 stockpile_version；三类 ID/表不可互换。删除/失效一个 Forecast Version 不改变 dataset identity。

### `AT-007` READY 状态门禁

`GENERATING`、`FAILED`、`RETIRED` dataset 不得被普通 Report API 当作可查询 READY 数据返回。

---

## 4. 主外键与主数据一致性

### `AT-008` 所有外键有效

对所有显式 FK 执行 orphan query，结果必须为 0；包括 material/project/customer/supplier/employee/organization、版本、PO、Demand lineage。

### `AT-009` material_id 跨表一致

Report 1 场景所需物料必须在 Report 2/3/4/6 的内部关联中解析到同一个 `material_id`；业务编码只用于展示。V1 每个 Material 恰有一个 Primary Inventory Organization，Report 2 与 Report 4 各恰有一行，且 organization_id 均指向该主组织。

### `AT-010` project_id 跨表一致

Report 3 的每个项目必须在 Report 5 有 snapshot 时有效配置/生命周期；名称重复时仍通过 ID 精确关联。夹具同时覆盖一个 Project 多个 Product Config、一个 Product Config 多个 Material，且每个 Config 只属于一个 Project。

### `AT-011` Material → MPM 唯一有效

每个试产 PO 的物料在 snapshot 时恰有一个主 MPM。测试创建 Project → MPM 但没有 Material → MPM 时必须失败，证明实现没有错误回退。

### `AT-012` 有效区间不重叠

同一项目 lifecycle、同一物料主 MPM 等单值时效关系不能在同一日期重叠；数据库约束应拒绝插入。项目生命周期受控值至少只接受 `NPI/MASS_PRODUCTION/EOL`，并拒绝把 `AFTER_SALES` 写作 lifecycle stage。

### `AT-013` 名称不是 Join 键

构造两个同名不同 ID 项目，Report 3→5 关联仍返回正确 ID 的配置，不发生笛卡尔或错误匹配。

---

## 5. Report 1 与超期公式

### `AT-014` 超期公式正确

对每个由 PO Header → PO Line → PO Line Schedule / Shipment 连接得到的 Report 1 行验证；每行 `po_line_schedule_id` 唯一，并与一条 Evaluation Sample 一一对应：

```text
expected = snapshot_date - order_date - material_lt_days - 240
overdue_days = expected
is_overdue = (expected > 0)
```

Report 1 只能返回 expected > 0。

### `AT-015` 边界严格大于 0

- `snapshot_date = order_date + LT + 240` → 不超期；
- 多 1 天 → `overdue_days=1` 且进入 Report 1；
- 少 1 天 → 不进入。

### `AT-016` 不使用 due_date 判断超期

构造 due_date 很早但公式未超期的 PO，不进入 Report 1；构造 due_date 很晚但公式超期的 PO，仍进入。

### `AT-017` 数量关系

每行满足：

```text
schedule_qty >= 0
schedule_received_qty >= 0
overdue_open_qty = greatest(schedule_qty - schedule_received_qty, 0)
```

构造同一 PO Line 下两个 Shipment，Report 1 必须返回两行且分别计算，不得先汇总到 PO Line。Generator V1 的默认夹具另验证每个 PO Line 只生成一个 Shipment，但 Schema 不得拒绝多 Shipment。

### `AT-018` LT 来源一致

Report 1 的主用 LT、Forecast Anchor 使用的 LT 和 material master 主用 LT 一致。原厂 LT 不得替代主用 LT。

### `AT-019` 固定 snapshot 不读机器日期

冻结 dataset snapshot 后，在不同时区/机器日期运行同一查询，Report 1 行集与 overdue_days 完全相同。静态扫描禁止业务代码调用 `date.today()`/`now()` 作为判定依据。

---

## 6. Forecast Anchor 与版本选择

### `AT-020` Forecast Anchor 正确

订单日 2024-05-12、LT 30 天时，Anchor 必须为 2024-06-11；不能使用 `order_date+LT+240` 或 due_date 的其他口径。

### `AT-021` Baseline 选择正确

有效版本日期为 06-03、06-10、06-12、06-19，Anchor=06-11；Baseline 必须是 06-10，后续从 06-12 开始。

### `AT-022` 无效版本被跳过

Anchor 前最近日若版本 `is_valid=false`，必须回退到更早最近有效版本；后续窗口同样跳过无效版本。

### `AT-023` 版本窗口数量

默认返回 Baseline + Anchor 后 3 版；配置允许后 2～5 版，总体 3～6 版。PO 不得生成私有 Forecast Version。

### `AT-024` 全体 PO 共享版本日历

不同 PO 的窗口可不同，但引用的版本必须来自同一 dataset 的 `forecast_versions`；不得出现仅为一个 PO 建立的版本头。

### `AT-025` 同日版本规则

V1 默认周版本日历。对同一 `version_date` 的多个补发/修订版本，只选择 `is_valid=true` 中 `sequence_no` 最大者；最大序号若无效则回退到较小的最大有效序号，全部无效则整日跳过。Anchor 同日最终版本不作为 Baseline，也不属于 Anchor 后版本；重复运行选择结果一致。

---

## 7. Forecast 同源与动态时间列

### `AT-026` Report 3/4/6 lineage 同源

抽取每个场景物料：Report 3 月预测、Report 4 周预测、Report 6 未来月需求必须能回溯到相同 `demand_signal_id` 或等价 lineage bridge。

### `AT-027` 月周聚合对账

对可完整覆盖的日期窗口，将 weekly/daily Demand Signal 聚合到月，与 Report 3/6 月值在固定舍入容差内一致；容差必须由配置定义，不能按测试临时放宽。

### `AT-028` 趋势不矛盾

若 Report 3 最新版本显示 causal project 需求大幅消失，Report 4 不得在没有其他项目需求来源的情况下生成极高 13 周需求。反例夹具必须被一致性校验拒绝。

### `AT-029` Report 3 长表与宽表

每个 Material×Project×Version 的 M0～M+6 共 7 月从 `monthly_forecasts` 透视；`汇总=sum(7月)`。跨年时列标题正确从 12 月滚到次年 1 月，不改 Schema。`累计发货` 等于 Material × Project 从当前 dataset 历史起点至该 Forecast Version Date（含）的发货数量之和。

### `AT-030` Report 4 长表与宽表

每物料最新快照恰有 week_index 1～13、无重复无缺口；`13周合计=sum(13桶)`，`周均=合计/13`。snapshot 为星期一时 `week_1_start=snapshot_date`；否则为其后最近星期一，后续每周相隔 7 天。按项目汇总 13 周贡献，`top_project` 必须为贡献最大者，并列按稳定 `project_id` 排序。

### `AT-031` Report 6 六个月动态列

每个选中历史版本-物料恰有连续 6 个未来月桶；第 1 月为 `stockpile_version_date` 所在自然月的下一自然月，随后逐自然月递增，跨年无需新增物理列。

### `AT-032` Generator 禁止三张表独立随机

静态/结构测试确认 Report 3/4/6 generator 接受同一 Demand World/lineage 输入；若删除 Demand Signal，三类派生必须失败，不能各自 fallback random。

---

## 8. Demand Adjustment 场景

量化阈值使用测试配置中的显式参数，不宣称为真实企业硬规则。默认 Mock 参数已在 Phase 4 固定，并在 Phase 5A Evidence Validator 复用；不再作为 deferred 项。

### `AT-033` Demand Reduction

Baseline 与后版本共同可比窗口中，causal project 总量下降超过 reduction 阈值，且远期回补低于 delay 阈值。Truth 为 `DEMAND_ADJUSTMENT/REDUCTION`；Report 5 非 EOL；源 Report 3 不包含 REDUCTION 标签。

### `AT-034` Demand Delay

近期需求下降并在更远月份回补；扩展窗口总量变化在容差内。Truth 为 `DEMAND_ADJUSTMENT/DELAY`，非 EOL。只减少未回补的反例不能通过。

### `AT-035` Demand Mixed

同时存在超过阈值的净总量下降和向后移动。Truth 为 `DEMAND_ADJUSTMENT/MIXED`。纯 Reduction、纯 Delay 反例不得误标 Mixed。

### `AT-036` causal project 证据最强

同物料多项目时，causal project 的配置化变化得分高于其他项目；其他项目允许噪声但不能产生更强证据。

### `AT-037` 预计消耗 6 个月边界

- 计算结果 `<6` → 期望对策“持续消耗”；
- `=6` 或 `>6` → “沟通供应商砍单”；
- 输入数量使用 Report 1 `overdue_open_qty`。

---

## 9. EOL、售后与项目呆滞

### `AT-038` Customer-side EOL 场景

需求变化达到阈值且 causal project 在 snapshot 为 EOL：Truth 必须 `PROJECT_OBSOLESCENCE/CUSTOMER_SIDE`，期望对策“沟通客户处理呆滞”。普通 Report 不输出该结论。

### `AT-039` EOL 时点查询

项目在 snapshot 前进入 EOL → Report 5 返回 EOL；snapshot 前仍非 EOL、之后才 EOL → 当前 Report 5 返回非 EOL。不能使用最新无时点记录覆盖历史。

### `AT-040` After-sales 正证据

无明显需求变化 + snapshot EOL + 多个未来周/月桶持续少量非零。Truth 为 AFTER_SALES；分别构造历史囤料命中与未命中夹具，两者都必须判 AFTER_SALES，证明售后先于历史囤料。

### `AT-041` After-sales 负证据

以下均不能判售后：未来全 0、只有一个孤立非零尖峰、有明显 Reduction/Delay/Mixed、项目非 EOL。阈值来自显式 Generator/Evaluation 配置。

### `AT-042` Internal-side Obsolescence

量产、无明显需求变化、不满足售后、order_date 历史囤料不命中：Truth 为 `PROJECT_OBSOLESCENCE/INTERNAL_SIDE`，期望对策“沟通事业部处理呆滞”。正样本必须同时覆盖 EOL 与非 EOL；EOL 样本的未来需求不得满足售后模式。

### `AT-043` 判断优先级

构造同时带多个低优先级证据的样本：试产必须优先；需求变化+EOL 必须先于 Stockpile；After-sales 必须先于 Stockpile；After-sales 被排除后，历史命中才为 Stockpile，历史未命中才进入 Internal-side。不得用 `lifecycle != EOL` 作为 Stockpile 或 Internal-side 的前置条件。

Phase 4 已启用 Scenario Plan 级断言：试产组织只能规划为 `TRIAL`；`AFTER_SALES` 同时覆盖 `stockpile_flag=true/false`，证明该标志不能覆盖售后优先级；`STOCKPILE` 固定为 true，Internal-side 固定为 false。真实 Evidence 判断留待 Phase 5/6。

---

## 10. Stockpile 历史版本

### `AT-044` 同日版本匹配

order_date 当天存在有效版本时选当天版本，不选更早或更晚版本。

### `AT-045` 最近历史版本匹配

order_date 当天无版本时，选之前最近有效版本；之后版本即使更新也不得参与。

### `AT-046` 无效版本跳过

最近版本无效时回退到更早有效版本。

### `AT-047` 当前命中不能覆盖历史未命中

下单时版本无 material、当前最新版本有 material：历史查询必须 `stockpile_record_found=false`。

### `AT-048` 历史命中不能被当前删除覆盖

下单时版本有有效 material、当前版本无：历史查询仍命中，Truth 可为 STOCKPILE。Stockpile 正样本必须同时覆盖 EOL 与非 EOL；EOL 样本必须已由负证据排除 After-sales。

### `AT-049` 版本存在与无版本区分

API 必须区分：无任何 as-of 有效版本；有匹配版本但物料无记录；有匹配版本且有有效记录。

### `AT-050` Stockpile 派生公式

库龄阈值语义测试立即启用：30/60/90/120/150/180/270/365 天均为累计超过阈值，较高阈值数量/金额不得大于较低阈值。金额、GAP、完成率、结余和预警的具体数值公式测试标记 `DEFERRED_TO_GENERATOR / DC-12`，不属于 Phase 1 blocked；Generator 阶段固定 Mock 公式后启用，且验证这些字段不参与五类根因判断。

---

## 11. 零需求与数值安全

### `AT-051` Report 4 零需求不除零

13 个周桶全 0 时：

```text
thirteen_week_demand_qty = 0
weekly_average_demand_qty = 0
estimated_consumption_months = null
consumption_status = NO_FORECAST_DEMAND
```

响应和日志不得出现 NaN、Infinity、数据库除零异常。

### `AT-052` Decimal 精度

数量、金额和比率使用固定精度 Decimal；相同输入跨平台哈希一致。JSON 序列化策略与 OpenAPI 一致。

### `AT-053` 负数量拒绝

除明确允许正负的净额/GAP，任何负供应、需求、PO 数量、Forecast 数量均被数据库或服务校验拒绝。

---

## 12. 参考项目与根因项目

### `AT-054` reference 与 causal 允许不同

至少一个非试产样本：`po_reference_project_id != scenario_truth.causal_project_id`。两者均与 material 有关系，Report 1 只返回参考项目。

Phase 4 默认 Synthetic Demo 将非试产 mismatch 最低覆盖率参数固定为 15%，并执行关系校验。

### `AT-055` causal_project 不泄漏

即使内部 Truth 已有根因项目，Report 1、Report 2 项目集合、Report 3 原始行、Report 5 查询和普通 API 都不得标记哪个项目是 causal。

---

## 13. Ground Truth 与 API 安全

### `AT-056` 普通数据库角色无权限

使用 `system_a_api` 连接执行 `SELECT evaluation.scenario_truth` 必须因权限失败；不能通过 search_path、函数或 View 间接读取。

### `AT-057` 公开 View 依赖扫描

遍历 PostgreSQL catalog，六个公开 View 的依赖闭包不能包含 evaluation Schema。

### `AT-058` OpenAPI 泄漏扫描

扫描 OpenAPI schemas/examples/paths，禁止出现：`scenario_truth`、`true_cause`、`true_cause_subtype`、`causal_project_id`、`demand_change_type`、`responsibility_type`、`expected_action` 及对应中文答案字段。

Phase 4 起该扫描为可执行测试；同时静态扫描 `app/api` 与 `app/schemas` 禁止导入 Evaluation Truth。

### `AT-059` 响应 Key 泄漏扫描

调用所有普通 endpoint（含空结果、错误、分页、Excel 导出）递归扫描 key/表头，禁止 Truth 字段。

### `AT-060` Report 1 特别泄漏扫描

最终列中不得有“超期类型”“原因&进展”“项目是否EOL”或同义答案列；允许 `是否超期`，因为它是入口筛选事实。

### `AT-061` 序列化白名单

将带 Truth 属性的内部测试对象误传给公开 serializer，响应仍只能包含公开 Schema 字段，不能使用无约束 ORM dump。

---

## 14. 六张最终模板还原

### `AT-062` Report 1 字段/顺序

Excel 导出业务表头与最终模板 37 列逐一相等、顺序一致；允许额外内部 ID 只存在 JSON API，不默认加入 Excel。

### `AT-063` Report 2 字段/顺序

最终模板 106 个业务列全部可还原，含试产字段、MPM、项目/客户集合、实际需求合计；不恢复任何旧字段名。核心断言固定为：`all_supply_qty`、`actual_demand_total_qty` 存在且 `supply_demand_surplus_qty=all_supply_qty-actual_demand_total_qty`。其他汇总/多余字段只作辅助展示，不得进入 Scenario 分类输入。

### `AT-064` Report 3 字段/动态月

非动态业务列与 23 列模板契约一致；七个月列导出时替换为真实 YYYYMM，底表仍为长表；累计发货符合 Material × Project × 截至版本日的累计定义。

### `AT-065` Report 4 字段/动态周

44 个模板业务列可还原；第 1～13 周与 Monday-start 的 `week_start_date` 一一对应；合计和周均正确。“供应商”严格映射 `supplier_code`，“供应商(英文)”严格映射 `supplier_name_en`。

### `AT-066` Report 5 字段/顺序

22 个模板字段完整，`项目` 通过 project_id 关联，生命周期来自 `project_lifecycle_history` 在 snapshot 时点的有效值。导出正确展开 Project 1:N Product Config 与 Product Config N:M Material，且不产生跨 Project 配置串联。

### `AT-067` Report 6 多级表头

60 个叶子业务列完整；未来六个月、结余预测、库龄的多级表头关系与最终模板一致；底表不包含固定月份物理列。

### `AT-068` 模板无字段丢失

以版本控制中的 machine-readable header manifest 对比 View/export manifest；任何删除、改名、重排必须显式更新 Data Contract 并获得业务确认。

---

## 15. 中性命名与禁用词

### `AT-069` 企业专有缩写扫描

扫描 Python、SQL、迁移、Mock 值、Excel 导出、API/OpenAPI、README、Markdown、注释、测试和 Prompt。业务方需提供/维护禁止词表；匹配结果为 0。`BG/PDT/PCBA` 加入模板展示术语白名单，但内部使用可解释英文名；`KD` 仅可作为模板辅助展示标签，完整释义仍关联 `DC-07-KD`，不得进入核心业务判断。

### `AT-070` project 命名统一

新建项目相关内部字段使用 `project`，不加企业前缀；中文业务字段使用“项目”。旧企业前缀或同义专有字段扫描为 0。

### `AT-071` 通用行业缩写内部可解释

模板中的 VMI/MRP/NCNR/PR/PO/ASN/MPQ 等若保留展示标签，内部字段必须使用可解释中性名称或有受控 glossary 映射，不能作为不可读数据库列名扩散。

---

## 16. API 契约

### `AT-072` dataset 参数强制

Report 请求缺少 dataset context 时按 API 契约返回 400，或仅在显式 `dataset=latest` 时解析；不得静默跨版本取数。

### `AT-073` 稳定分页

相同 dataset/过滤/排序的分页多次调用行顺序一致，不重复不丢失；排序追加稳定 ID tie-breaker。

### `AT-074` 动态序列使用数组

Report 3/4/6 JSON 使用 `months`/`weeks`/`buckets` 数组，不把 `202609`、`第34周` 等变成动态 Schema 属性。

### `AT-075` Stockpile API 参数一致性

同时传 `po_line_schedule_id` 和 `as_of_date` 且与其父 PO Line 的 `order_date` 不一致时返回 422；一致时正常查询。兼容传 `po_line_id` 时遵循相同规则，schedule ID 为首选事实键。

### `AT-076` 错误不泄漏内部信息

所有 4xx/5xx 响应不包含 SQL、连接串、evaluation 表名、Python stack trace 或 Truth。

---

## 17. Phase 完成标准

### Phase 0.1（本轮）

- `AGENTS.md` 与五份 `docs/*.md` 存在；
- 六模板字段全部进入 Data Contract；
- DC-01～DC-15 的已确认或获准延后事项均已从 blocked 索引移除；仅真正待业务确认项保留明确标记；
- 未实现数据库、Generator、FastAPI、Agent 或前端。

### Phase 1

- PostgreSQL/SQLAlchemy/Alembic 骨架可运行；
- 迁移在空库成功升级/降级策略明确；
- dataset_versions 与主数据骨架约束存在；
- `/health`、`/ready` 可用；
- 不提前实现 Generator/Report 业务。

### System A Done

- `AT-001`～`AT-076` 中所有已确认、适用项通过；
- 任一超期 PO 可通过六类 API 取得足够且一致的证据；
- 相同确定性输入得到相同业务世界；
- Truth 可供评测但普通 Copilot 完全不可见。

## 18. 当前 blocked / deferred 测试索引

### 18.1 Phase 1 blocked

无。Phase 1 不存在业务阻塞项。

### 18.2 `NEEDS_BUSINESS_CONFIRMATION`

| ID | 仍 blocked 的后续测试 | Phase 1 影响 |
|---|---|---|
| `DC-07-KD` | KD 完整业务释义相关的语义测试；KD 已限制为辅助展示，不参与核心判断 | 无 |
| `DC-16` | `NEEDS_BUSINESS_CONFIRMATION`：售后正式处置、保留量、保供周期与 `expected_action` 精确评测 | 无；只阻塞后续售后对策完成 |

### 18.3 已授权延后（不是 blocked）

| ID | 延后至后续阶段的测试 |
|---|---|
| `DC-03` | Report 2 辅助供需汇总、多余库存/采购/工单/PR 等最终 Mock 公式；三个核心字段与盈余公式测试已启用 |
| `DC-12` | Report 6 金额、GAP、完成率、结余、预警的最终 Mock 公式；累计库龄语义测试已启用 |

### 18.4 已固化的 Synthetic Config（不是企业规则）

| ID | 状态 | 验收范围 |
|---|---|---|
| `DC-15` | `RESOLVED_AS_SYNTHETIC_CONFIG` | 默认 Mock 阈值存在、可配置、进入 Scenario signature，并由参数化测试覆盖；不得宣称为企业真实阈值 |

Phase 4 收尾回归要求：七个量产 Pattern 分别采用单一权重为 1、其余为 0 的配置，仍必须保持八种 Pattern 非零、After-sales 囤料标记双值覆盖和 same-seed 确定性。兼容集合全零权重时按规格使用 seeded 等权抽样；负权重必须拒绝。`DC-15` 的 Data Contract、Scenario Rules、DB Schema、Architecture 与本索引必须保持同一状态；`DC-16` 继续待业务确认。

`DC-01/02/04/05/06/08/09/10/11/13/14` 均已解决，对应测试不再 blocked。

## 19. Phase 4 收尾实测记录（2026-08-28）

以下为实际执行结果，不代表后续 Evidence/Report 阶段已完成：

| 验收项 | 结果 |
|---|---|
| PostgreSQL 测试库迁移 | `007_scenario_truth → base → 007_scenario_truth` 成功；base 时两个应用 schema 与 Alembic revision 记录均已清空 |
| 实际角色登录 | `system_a_api` 读取 Truth 返回 SQLSTATE `42501`；generator 读/写权限通过；evaluator 可读、写入/更新/删除均被拒绝 |
| Scenario | same-seed、different-seed 实际 Plan 差异、幂等复用、partial-world rejection 与失败回滚均通过 |
| coverage-first | 七种量产 Pattern 的单一权重为 1 配置全部通过；每组仍覆盖八种 Pattern，且保持确定性 |
| After-sales | Demo 囤料标记 `false=4 / true=2`；双值覆盖通过，正式 `expected_action` 不擅自填充 |
| 防泄漏 | OpenAPI 静态与真实 HTTP 扫描、公共代码扫描、独立进程公共应用导入隔离、公开 JSON 示例扫描均通过 |
| DC 状态 | 五份规格的 `DC-15` 一致为 `RESOLVED_AS_SYNTHETIC_CONFIG`；`DC-16` 保持 `NEEDS_BUSINESS_CONFIRMATION` |
| 全量 pytest | `99 passed / 0 failed / 0 skipped`；1 条现有测试客户端依赖弃用警告 |
| HTTP | `/health`、`/ready`、`/api/v1/health`、`/api/v1/ready` 均为 200；验收临时 API 已关闭 |
| Forbidden-term scan | 111 个文件扫描通过，包含 docs |
| GitHub hygiene | 环境文件/数据卷/缓存忽略、可提交文件本机路径与已知本机密钥扫描、示例逐条 Truth 检查均通过 |
| Demo 回归 | 仍为 115 条 Truth；同 seed 重跑哈希与公开聚合摘要一致 |

本轮修复兼容场景权重全零的抽样失败、拒绝负权重、移除公共服务包对 Generator/Truth 的隐式导入，并补齐 `/ready` 根路径兼容入口。未改变业务判断优先级、五类根因或现有 Demo 业务内容。

Phase 4 收尾时 Git 为 `GIT_IDENTITY_BLOCKED`。之后用户已配置 repository-local 身份，Phase 5A 开始前创建 checkpoint `14f3d94fea8d62c9272536a34dae84acab897401`，该工程阻塞已解除；未添加 remote 或 push。KD 完整释义和售后正式处置仍按原确认边界保留。

## 20. Phase 5A 验收边界与测试映射

| 合同 | 当前覆盖 | 留待后续 |
|---|---|---|
| AT-010 / AT-012 | 全部 Material × Project 可解析配置；一项目多配置、一配置多物料；生命周期半开区间、无重叠、snapshot 唯一且满足 Scenario | Report 5 展示/导出 |
| AT-026 / AT-032 | 唯一共享日需求 + 中性 dated revisions，as-of 不偷看未来，所有候选项目均有 Signal | Report 3/4/6 具体派生服务 |
| AT-033～036 | 源观测前后 Reduction/Delay/Mixed、数量守恒/净减少与远期移量、causal 强于稳定非 causal | 正式共享 Forecast Calendar 的每 PO 版本窗口比较 |
| AT-038～043 | 项目 EOL 证据、售后13周/6月持续性、囤料双值；Stockpile/Internal EOL 零量负证据；Trial 优先级不变 | 正式 Forecast、历史 Stockpile 及根因推断 |

自动化测试包括：

- `test_evidence_foundation.py`：schema、全部关系、真实数量形态、source revision 日期、防未来观测、跨年/闰日、确定性、不同 seed；默认 Demo Internal-side 仅非 EOL，因此另用固定 Scenario seed=20260829 显式验证 EOL，而非修改原 Truth。
- `test_evidence_foundation_integration.py`：008 空库重建、真实 exclusion、跨 dataset FK、重复日期/负数量拒绝、完整复用、配置冲突、六类部分数据拒绝、三个上游世界缺失拒绝、写入中途故障整体回滚、模型与迁移一致性、角色登录权限。
- 既有 OpenAPI/公共进程隔离、仓库 hygiene、禁止词及全部历史测试继续执行。

测试库每次 `downgrade base → upgrade head` 后重放既有 `002_grants.sql`，因为删除 Schema 会删除其默认 ACL。原 001～007 迁移保持不变；API 不获得 Evidence raw table 读取权。

### Phase 5A 实测记录（2026-08-28）

- Pre-Phase5A checkpoint：`14f3d94fea8d62c9272536a34dae84acab897401`。
- 开发库成功从 007 升至 `008_evidence_foundation`；测试库完成 `008 → base → 008` 重建，迁移与六张新表的 SQLAlchemy metadata 一致。
- 全量：153 passed / 0 failed / 0 skipped；保留1条现有测试客户端依赖弃用警告。
- 实际 generator 角色生成 Demo 后重复调用，聚合数量与 hash 完全一致；六张新表的真实权限检查通过，API raw SELECT 被拒绝，evaluation 仍隔离。
- Demo：70 条 Lifecycle；snapshot NPI=4、MASS_PRODUCTION=12、EOL=14；60 个 Product Config、272 条 Config-Material 关系、136 个 Demand Signal、110840 个日点、255098 条中性日修订。
- Demand 日期：2025-02-01～2027-04-26；以 snapshot 2026-08-26 观察的全窗口合成需求总量：7875929.9700。
- Evidence hash：`762381c2296e7c684b3698bc669ed353f55bdb342edf8157fa4b96678d28c8a3`。
- 原 Truth 仍为115条，实际 Lifecycle requirement mismatch=0；Dataset 仍为 GENERATING，最终 business_content_hash=null。
- `/health`、`/ready`、`/api/v1/health`、`/api/v1/ready` 实际 HTTP 均为200；在线 OpenAPI 无 Truth/Generator endpoint。
- Forbidden-term scan：124 个文件通过；GitHub hygiene：环境文件/数据卷忽略、可提交文件无已知本地密钥或本机绝对路径、公开示例无逐条 Truth。

本次失败测试的诊断输出曾回显本地测试库连接凭据，未写入仓库；已为测试 URL repr 增加脱敏及回归断言。该本地凭据建议由用户轮换，不在本阶段擅自改动凭据。

未实现 Forecast Version、Monthly/13W Forecast、Supply/Demand Facts、Stockpile Facts、Report Views/API、Excel Export、Agent 或 LLM。`DC-07-KD` 和 `DC-16` 的待确认边界保持不变，不阻塞本阶段。

## 21. Phase 5A.1 修复验收（2026-08-28）

- 根因：原预算恢复/扣减脉冲不能保证被周度发布观察；共享日历采样可只观察两个低状态，从而漏掉需求变化。
- 修复：`PERSISTENT_1` 有效日状态，联合约束多个 Anchor 的初始计划及修订数量，不针对某个 weekday、不降阈值。生命周期/配置与源实体 ID 保留，具体有限计划窗口及旧参数兼容边界见 `SCENARIO_RULES.md` 第18节。
- Demo publication dry-run：115 条 Scenario schedule × 7 个 weekly offsets × 3 种有效日历（正常/最近 Baseline 无效/首个 post 无效）× 5 个 post，共 12075 次比较全部通过；REDUCTION 1470、DELAY 1680、MIXED 945、NONE 7980。分别覆盖前2～5版前缀；After-sales 保持囤料双值与持续小量，不产生明显变化。
- 增加 Monday/Tuesday/Friday/Sunday Anchor、月末/年末/年初、同日多序号、最大序号无效、整日无效、Anchor 同日排除测试。纯 Reduction、纯 Delay 均不能通过 Mixed 判据。
- 同 seed 重跑新 hash 相同；不同 Evidence seed 保持全部 demo 场景类型证据。旧脉冲幅度的非默认覆盖显式拒绝，避免忽略配置。
- 受控修复实际完成：只更新 GENERATING demo 的受影响 Evidence；Lifecycle 70 / Config 60 / Config-Material 272 / Signal 136 / Point 110840 保持实体数及稳定 ID，Revision 255098 → 130415。Lifecycle/Config 业务内容逐行相等且未写入。
- Master、Procurement、Scenario（含 causal project、lifecycle requirement 与 stockpile plan）由事务前后精确内容 hash 验证不变。Dataset 保持 GENERATING、最终 hash=null。
- 旧 Evidence hash：`762381c2296e7c684b3698bc669ed353f55bdb342edf8157fa4b96678d28c8a3`。
- 新 Evidence hash：`d2ee070ef425915488b5281b244a234a24be0a9890598a2b2d48de1400cc868e`；正常 CLI 重跑复用并一致。
- 真实 PostgreSQL：测试库 `008 → base → 008` 成功，schema 与 metadata 相符；历史001～008无diff。旧 hash/非demo/READY 安全门禁、另一 dataset 不变、插入中途故障整阶段回滚、generator/API 角色权限均通过。
- 最终全量：191 passed / 0 failed / 0 skipped；1 条既有 Starlette/httpx 弃用警告。
- 四个 `/health`、`/ready` 及版本化端点实际 HTTP 200，在线 OpenAPI 泄漏扫描通过。首次诊断请求受环境代理影响，改为本机直连后成功；临时 API 已关闭。
- Forbidden-term scan：129 文件通过；GitHub hygiene、公共代码隔离和示例防泄漏随全量测试通过。无新增业务待确认项；DC-15 resolved、DC-16/KD 原确认边界不变。
- 本修复不创建 Forecast 表或正式 WindowSelector；Phase 5B 从本修复 checkpoint 继续，Report View/API/Excel 仍未实现。

## 22. Phase 5B 验收（2026-08-28）

| 合同 | 已落地的验收 | 后续边界 |
|---|---|---|
| AT-020～025 | 正式 Anchor/WindowSelector；严格前后、每日有效最大序号、整日无效跳过、2～5 post、跨年、共享周历与稳定版本ID | Report Query/API 对外封装留Phase6 |
| AT-026～028 / AT-032 | 月/周/project/material 全链路源对账、lineage、缺少Demand拒绝、不独立随机、错误数量及错误Signal引用拒绝 | Report6同源留Phase5C |
| AT-029/030 / AT-064/065 | 月长表、13周长表、连续日期、累计发货、最多项目、合计/周均；原展示7月/13周契约不变 | View/Excel字段与列宽布局仍留Phase6 |
| AT-033～036 | 每个真实Scenario schedule按共享版本选Baseline+5post，原阈值下Reduction/Delay/Mixed/NONE与Customer-side通过，causal强于其他Project；纯Reduction/Delay不能通过Mixed | 不实现最终根因判断服务 |
| AT-051 | 9个真实物料级全零13周，合计与周均均为0，无除零 | PO消耗月数/处置仍未实现 |
| AT-056～061 | 实际generator可写新raw facts、API raw SELECT与Truth SELECT均42501；公共域模块不加载Generator/Truth，OpenAPI/公开样例无答案 | 仅未来Report Views可授权API |

新增 `009_forecast_evidence` 六表，历史001～008无修改。开发库008→009成功；专用测试库实际009→base→009，metadata与DDL一致。月首/数量非负、周索引/Monday、唯一键、同dataset唯一latest的部分索引及全部复合FK均有真实PostgreSQL测试。

六表全空生成、完整复用、六类partial拒绝、四层前置缺失拒绝、不同配置冲突、READY拒绝、故障注入整阶段rollback全部通过。已有下游Forecast facts时Evidence correction拒绝；空009 schema不阻塞隔离修复测试。

实际generator角色Demo：102 Forecast Versions（有效82/无效20，同日附加版本20）；135320 Monthly Forecast（含比较重叠月份）；11152 Material-Project Shipments；1 Weekly Snapshot；1768 Weekly Project rows；780 Weekly Material rows。版本日期2025-02-03～2026-08-24；13W首周2026-08-31、第13周2026-11-23，最后需求日2026-11-29。

实际正常CLI重跑复用，`forecast_content_hash=fe1d2700018ba9dfa31180123fa3c51c4e9dede0f0218224581b8aafd87ebec9` 不变。Same-seed确定性、different-seed发布夹具变化而源需求/场景证据不变均通过。Dataset继续GENERATING、最终业务hash=null；Phase5A.1 Evidence hash不变。

完整回归结果：262 passed / 0 failed / 0 skipped。全量启动后增加1项“缺少Demand不得随机回退”，补充执行通过；最终收集263项，全部有通过记录。另补跑新增的缺少post窗口断言与GitHub hygiene，均通过。保留1条既有Starlette/httpx弃用警告，不将其视为业务失败。

四个健康/就绪端点实际HTTP200，在线OpenAPI、公共代码隔离与JSON样例扫描通过；临时API已关闭。Forbidden-term scan：142文件通过。`.env`/数据卷忽略、无已知本地密钥/绝对路径/逐条Truth公开示例。无新业务阻塞；DC-15保持resolved，DC-16与KD仍按既有范围待确认，不阻塞本阶段。

未实现Supply/Demand、Stockpile、最终Report Views/API、Excel Export、Agent、LLM。前后重叠月是比较用source facts，不扩充最终Excel列；最终展示/查询接口仍须在Phase6明确还原合同。
