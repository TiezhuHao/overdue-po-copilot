# Phase 1C — System A evidence contracts

目标是追溯使用的事实，不输出原因、责任或动作。代码仍只有六个 Report GET endpoint。新增字段完整映射与筛选规则见 [data-contracts.md](data-contracts.md)。

| Evidence | Source | Join key（均含 dataset_version_id） | Time/version | Used by future layer |
|---|---|---|---|---|
| PO | R1 / 原 Header→Line→Schedule | po_header_id、po_line_id、po_line_schedule_id | order_date、dataset snapshot；一行Schedule | 已有Aging/PO consumption；未来证据引用 |
| Material | R1–R6 / Material master | material_id；有组织范围时加organization_id | 固定dataset世界 | 跨表关联，禁止名称Join |
| Project | R1参考项目、R3预测项目、R4贡献项目、R5配置项目 | po_reference_project_id 或 project_id，语义不同 | R3 version、R4 weekly snapshot、R5 dataset snapshot | 未来项目证据关联，不能直接表示责任 |
| Supply-demand | R2 / 组件聚合 | supply_demand_snapshot_id、material_id、organization_id | supply_snapshot_date | 已有源供需差；未来来源审计 |
| Inventory / MPM | R2 / Inventory及所引物料MPM配置 | inventory_snapshot_id、mpm.employee_id | inventory_snapshot_date | 库存与物料联系人证据；不绑定项目 |
| Monthly Forecast | R3 / 月事实 | schedule、material、project、forecast_version_id、forecast_month | version date+sequence；daily-final-valid；公开7月horizon | 显式同月变化；未来版本窗口证据 |
| Weekly Forecast | R4 / 物料周及项目周事实 | weekly_forecast_snapshot_id、material、organization、week；项目再加project | forecast_snapshot_date、week_start_date、source_forecast_version_id | 已有消费/覆盖，未来项目贡献分析 |
| Configuration / lifecycle | R5 / Config×Material及Project lifecycle | product_config_id、material_id、project_id | dataset snapshot时有效；config version是独立业务版本 | 未来配置/生命周期证据；历史轨迹尚未公开 |
| Stockpile | R6 / Material-level versioned records | stockpile_record_id、stockpile_version_id、material、organization | version date+sequence；显式as_of；月/库龄绑定同版 | 历史证据查找；不生成是否应囤料的结论 |

## Implementation boundary

- 沿用所有既有稳定内部键，没有新增业务表、数据字段或生成逻辑；没有生成价格、项目责任或诊断标签。
- 新增 migration `012_evidence_contract` 仅创建五个窄视图：forecast_version_evidence、weekly_snapshot_evidence、supply_snapshot_evidence、stockpile_forecast_evidence、stockpile_age_evidence。用途分别为版本序号、周快照来源、供需/库存来源ID及历史版月/库龄子记录。
- 现有视图已提供其余身份与项目周事实；不修改001–011、不改变六个canonical view或Excel manifest。API只能读reporting与既有dataset metadata，原表及evaluation权限不开放。012降级只删除新增视图，升级不修改数据。
- 路径：受限原始事实 → 白名单reporting views → REST schema/projection → B DTO/mapping → Canonical → 已有Analytics。B没有数据库依赖，也不自动选previous/current。
- R4新增数组没有排名。每一行贡献是实际project×week事实，未出现的项目不凭空造记录。B拒绝重复周、日期/宽槽冲突与重复项目周键；跨项目数量对账由真实数据库契约测试验证，不在Adapter增加指标运算。
- 项目名称、物料编码可用于展示查找；Evidence引用必须带dataset和稳定ID。一个PO Header可有多Line，每Line可有多Schedule；不以PO号去重。

## Historical stockpile usage

先取得R1 canonical PO，再调用 `adapter.stockpile(po.dataset_version_id, material_id=po.material_id, as_of_date=po.order_date)`。没有用当前记录代替历史记录，也不将PO reference project强行赋给Material级Stockpile。

`stockpile_selection`同时记录查询截止日及选中的版本ID/date/sequence。若版本均null，则截止日以前没有有效版本；若版本非null而total=0，则在所选版没有匹配筛选的记录。不因某物料缺记录就回退到更老版本。显式version可读有效旧修订，默认as-of选择同日最大有效sequence。超出dataset cutoff的请求422；history中的合法未来fixture永远不可提前命中。

历史模式仅展示有版本依据的数量、月预测和库龄；协议价和未有历史来源的辅助字段为null。默认当前模式沿用原展示值。current Stockpile与overdue PO不一定有交集，测试使用真实历史事实验证身份而非修改Generator制造交集。

## Supply composition findings

既有模型可以证明：`all_supply_qty`由SUPPLY组件合计；available inventory不含quality-hold/blocked；schedule未收货量拆成OPEN_PO和IN_TRANSIT，两者相加等于其开放量，R2.open_po_qty已包含两者。不能再加一次在途；IN_TRANSIT是合成组件，不是ASN。

需求是snapshot起7/14/7日不重叠窗口的既有Mock变换，与13周Forecast不同。组件源事实有snapshot、material、organization与PO/inventory引用。模型没有ASN实体、PR转PO关联及采购承诺状态；预留OTHER_CONFIRMED_SUPPLY这个组件名称不能证明全部供应的承诺语义。因此本轮不定义confirmed/planned supply，不改变Analytics的UNCONFIRMED_SUPPLY_COMPOSITION。

## Price and remaining gaps

PoLine没有可靠unit_price/currency。R6协议价属于物料供应商关系，不是订单成交价格；不新增随机价格，不计算overdue amount。剩余候选：PO价格/币种、UOM、ASN/PR/承诺与排重模型、完整Forecast版本目录/任意窗口、历史项目生命周期查询、旧展示列全面强类型化。Top 3的原始贡献证据已公开，但计算与归因均不属于本阶段。

## Verification

`test_evidence_contracts.py`覆盖新增DTO、旧响应兼容、投影白名单及错误时间/身份拒绝。`test_evidence_contract_integration.py`通过真实REST与Adapter验证六表Join、PO消费可计算、版本与月份比较、周贡献对账、历史边界/子明细/跨dataset隔离、012降升不改事实。既有report/API角色与泄漏测试继续执行，最终需完整pytest回归。
