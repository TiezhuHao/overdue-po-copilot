# 六报表精确表头清单

唯一机器契约：`backend/app/reporting/report_header_manifest.json`。本文件由同名Python模块的render_markdown生成，不单独维护列序。

仅提取明确标记“最终模板”的sheet结构、表头单元格和合并关系；未提取业务行，未把模板作为事实数据源。

column_index从1开始。display_name为叶子标题；完整header_path保留多级结构、原始文字及标点。canonical_field取自DATA_CONTRACT，不按文档分组推断Excel顺序。

动态槽位：Report 3为版本月M0～M+6；Report 4为snapshot当日或之后最近星期一起连续13周；Report 6为版本月下一自然月起连续6月。实际年月/日期由Phase6B exporter填充，manifest不固定未来日期。

Report 2实际需求合计位于DA/DB；Report 6囤料消耗预警位于AM，在结余预测与库龄之间。Report 2标题合并只到CZ，但业务表头延伸到DB；以实际叶子列为准，不据标题宽度截列。

CONFIRMED表示字段含义已固化，不保证可空来源一定有值；DEFERRED_BUSINESS_FORMULA保持空值，不编造辅助公式；AUXILIARY_ONLY只作展示，术语释义确认状态另行保留。core/auxiliary为字段用途，不是根因答案。

后续Semantic View、API、Excel必须通过同一manifest取得字段顺序；长表以动态slot元数据定位透视列，不另建字段顺序清单。

辅助sheet只登记结构与表头，不读取说明正文，也不将其当业务事实。Report 3版本日历原模板为4列；日内sequence是内部选择字段，不擅自增加模板列。

Manifest hash：`9a3584a3f52b405e9934d5d99766b6b22bd8ea6252669c455d25ce37ceaa8f44`。

## Report 1：超期PO明细

来源：`报表1_超期PO明细_最终模板.xlsx`；业务列数：37；表头行：[1]。

只读表头结构指纹：`5f4cd6e5f35c2ee4f51180d75a0d153e67a2b460df4c9ed68dc2fa0eda9f95dc`。

| Sheet | 表头行 | 角色 |
|---|---|---|
| 超期PO明细 | [1] | 业务主表 |
| 字段说明 | [1] | 辅助结构 |

| 列号 | Excel列 | display_name / 完整层级 | canonical_field | dynamic/static | core/auxiliary | business_status |
|---:|---|---|---|---|---|---|
| 1 | A | 库存组织 | `inventory_organization_code` | static | auxiliary | CONFIRMED |
| 2 | B | 库存组织类型 | `inventory_organization_type` | static | core | CONFIRMED |
| 3 | C | 业务实体 | `business_entity_name` | static | auxiliary | CONFIRMED |
| 4 | D | 订单号 | `po_number` | static | core | CONFIRMED |
| 5 | E | 订单行 | `po_line_number` | static | core | CONFIRMED |
| 6 | F | 订单行发运号 | `shipment_number` | static | core | CONFIRMED |
| 7 | G | 关闭状态 | `close_status` | static | auxiliary | CONFIRMED |
| 8 | H | 项目名称 | `reference_project_name` | static | auxiliary | CONFIRMED |
| 9 | I | 物料编码 | `material_code` | static | core | CONFIRMED |
| 10 | J | 物料描述 | `material_description` | static | auxiliary | CONFIRMED |
| 11 | K | 规格型号 | `specification_model` | static | auxiliary | CONFIRMED |
| 12 | L | 供应商编码 | `supplier_code` | static | auxiliary | CONFIRMED |
| 13 | M | 供应商名称 | `supplier_name` | static | auxiliary | CONFIRMED |
| 14 | N | 数量 | `schedule_qty` | static | core | CONFIRMED |
| 15 | O | 接收数量 | `schedule_received_qty` | static | core | CONFIRMED |
| 16 | P | 超期未交数量 | `overdue_open_qty` | static | core | CONFIRMED |
| 17 | Q | 物料属性 | `material_attribute` | static | auxiliary | CONFIRMED |
| 18 | R | 物料大类 | `material_category_level_1` | static | auxiliary | CONFIRMED |
| 19 | S | 物料中类 | `material_category_level_2` | static | auxiliary | CONFIRMED |
| 20 | T | 订单下达日期 | `order_date` | static | core | CONFIRMED |
| 21 | U | 应交日期 | `due_date` | static | auxiliary | CONFIRMED |
| 22 | V | 数据快照日期 | `snapshot_date` | static | core | CONFIRMED |
| 23 | W | 物料LT | `material_lt_days` | static | core | CONFIRMED |
| 24 | X | 超期天数 | `overdue_days` | static | core | CONFIRMED |
| 25 | Y | 是否超期 | `is_overdue` | static | core | CONFIRMED |
| 26 | Z | 订单采购员 | `order_buyer_name` | static | auxiliary | CONFIRMED |
| 27 | AA | 默认采购员 | `default_buyer_name` | static | auxiliary | CONFIRMED |
| 28 | AB | 物控员 | `material_controller_name` | static | auxiliary | CONFIRMED |
| 29 | AC | 计划经理 | `planning_manager_name` | static | auxiliary | CONFIRMED |
| 30 | AD | 计划总监 | `planning_director_name` | static | auxiliary | CONFIRMED |
| 31 | AE | 采购经理 | `purchasing_manager_name` | static | auxiliary | CONFIRMED |
| 32 | AF | 采购总监 | `purchasing_director_name` | static | auxiliary | CONFIRMED |
| 33 | AG | 通知接收人 | `notification_recipient_name` | static | auxiliary | CONFIRMED |
| 34 | AH | 参考编号（项目） | `reference_project_code` | static | auxiliary | CONFIRMED |
| 35 | AI | 是否可关闭 | `can_close` | static | auxiliary | CONFIRMED |
| 36 | AJ | 完成时间 | `completion_at` | static | auxiliary | CONFIRMED |
| 37 | AK | PO状态 | `po_status` | static | auxiliary | CONFIRMED |

## Report 2：物料供需汇总

来源：`报表2_物料供需汇总表_最终模板.xlsx`；业务列数：106；表头行：[3]。

只读表头结构指纹：`6309af7aa3bd5214e89b9b935ac766f816875fed382208d7e970789bdd186f18`。

| Sheet | 表头行 | 角色 |
|---|---|---|
| 物料供需汇总 | [3] | 业务主表 |
| 字段说明 | [1] | 辅助结构 |
| 使用逻辑 | [1] | 辅助结构 |

| 列号 | Excel列 | display_name / 完整层级 | canonical_field | dynamic/static | core/auxiliary | business_status |
|---:|---|---|---|---|---|---|
| 1 | A | 库存组织 | `inventory_organization_code` | static | auxiliary | CONFIRMED |
| 2 | B | 计划方法 | `planning_method` | static | auxiliary | CONFIRMED |
| 3 | C | 物料编码 | `material_code` | static | core | CONFIRMED |
| 4 | D | 物料描述 | `material_description` | static | auxiliary | CONFIRMED |
| 5 | E | 采购类别 | `purchasing_category` | static | auxiliary | CONFIRMED |
| 6 | F | 替代组 | `substitute_group_code` | static | auxiliary | CONFIRMED |
| 7 | G | 供应商 | `supplier_code` | static | auxiliary | CONFIRMED |
| 8 | H | 供应商名称(英文) | `supplier_name_en` | static | auxiliary | CONFIRMED |
| 9 | I | 物料类别 | `material_category_code` | static | auxiliary | CONFIRMED |
| 10 | J | 类别说明 | `material_category_description` | static | auxiliary | CONFIRMED |
| 11 | K | 采购员 | `buyer_name` | static | auxiliary | CONFIRMED |
| 12 | L | 物控员 | `material_controller_account` | static | auxiliary | CONFIRMED |
| 13 | M | 物控员名字 | `material_controller_name` | static | auxiliary | CONFIRMED |
| 14 | N | 物控员代码 | `material_controller_code` | static | auxiliary | CONFIRMED |
| 15 | O | 主物控员名称 | `primary_material_controller_name` | static | auxiliary | CONFIRMED |
| 16 | P | MPM编号 | `mpm_code` | static | core | CONFIRMED |
| 17 | Q | MPM姓名 | `mpm_name` | static | core | CONFIRMED |
| 18 | R | MPM部门 | `mpm_department_name` | static | core | CONFIRMED |
| 19 | S | 物料提前期 | `material_lt_days` | static | auxiliary | CONFIRMED |
| 20 | T | 原厂LT | `manufacturer_lt_days` | static | auxiliary | CONFIRMED |
| 21 | U | 良品VMI库存数量 | `good_vmi_inventory_qty` | static | auxiliary | CONFIRMED |
| 22 | V | 良品非VMI库存数量 | `good_non_vmi_inventory_qty` | static | auxiliary | CONFIRMED |
| 23 | W | 不良品库存数量 | `defective_inventory_qty` | static | auxiliary | CONFIRMED |
| 24 | X | 不参与MRP库存数量 | `non_mrp_inventory_qty` | static | auxiliary | CONFIRMED |
| 25 | Y | 虚拟不良品库存 | `virtual_defective_inventory_qty` | static | auxiliary | CONFIRMED |
| 26 | Z | VMI在途订单数量 | `vmi_in_transit_order_qty` | static | auxiliary | CONFIRMED |
| 27 | AA | 非VMI在途订单数量 | `non_vmi_in_transit_order_qty` | static | auxiliary | CONFIRMED |
| 28 | AB | VMI在途送货数量 | `vmi_in_transit_delivery_qty` | static | auxiliary | CONFIRMED |
| 29 | AC | 非VMI在途送货数量 | `non_vmi_in_transit_delivery_qty` | static | auxiliary | CONFIRMED |
| 30 | AD | 采购申请数量 | `purchase_requisition_qty` | static | auxiliary | CONFIRMED |
| 31 | AE | 量产工单在制数量 | `mass_production_wip_qty` | static | auxiliary | CONFIRMED |
| 32 | AF | 非标工单在制数量 | `nonstandard_wip_qty` | static | auxiliary | CONFIRMED |
| 33 | AG | 虚拟计划单 | `virtual_planned_order_qty` | static | auxiliary | CONFIRMED |
| 34 | AH | 标准工单需求数量 | `standard_work_order_demand_qty` | static | auxiliary | CONFIRMED |
| 35 | AI | 非标准工单需求数量 | `nonstandard_work_order_demand_qty` | static | auxiliary | CONFIRMED |
| 36 | AJ | 计划单需求数量 | `planned_order_demand_qty` | static | auxiliary | CONFIRMED |
| 37 | AK | 安全库存需求数量 | `safety_stock_demand_qty` | static | auxiliary | CONFIRMED |
| 38 | AL | 人工需求数量 | `manual_demand_qty` | static | auxiliary | CONFIRMED |
| 39 | AM | 长期预测需求 | `long_term_forecast_demand_qty` | static | auxiliary | CONFIRMED |
| 40 | AN | 所有供应 | `all_supply_qty` | static | core | CONFIRMED |
| 41 | AO | 供需盈余量 | `supply_demand_surplus_qty` | static | core | CONFIRMED |
| 42 | AP | 供需汇总 | `supply_demand_summary_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 43 | AQ | 不参与MRP供需汇总 | `non_mrp_supply_demand_summary_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 44 | AR | 计划单 | `planned_order_qty` | static | auxiliary | CONFIRMED |
| 45 | AS | 已到期预测计划单 | `expired_forecast_planned_order_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 46 | AT | 未到期预测计划单 | `unexpired_forecast_planned_order_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 47 | AU | 多余不参与MRP库存 | `excess_non_mrp_inventory_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 48 | AV | 多余库存 | `excess_inventory_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 49 | AW | 多余采购数量 | `excess_purchase_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 50 | AX | 多余工单数量 | `excess_work_order_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 51 | AY | 多余pr数量 | `excess_purchase_requisition_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 52 | AZ | 最小包装 | `minimum_pack_qty` | static | auxiliary | CONFIRMED |
| 53 | BA | 最小订单量 | `minimum_order_qty` | static | auxiliary | CONFIRMED |
| 54 | BB | ncnr | `non_cancelable_non_returnable_flag` | static | auxiliary | CONFIRMED |
| 55 | BC | 组织在用项目 | `organization_active_projects` | static | auxiliary | CONFIRMED |
| 56 | BD | 集团在用项目 | `enterprise_active_projects` | static | auxiliary | CONFIRMED |
| 57 | BE | 最多项目 | `top_project` | static | auxiliary | CONFIRMED |
| 58 | BF | 所有项目 | `all_projects` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 59 | BG | 组织在用客户 | `organization_active_customers` | static | auxiliary | CONFIRMED |
| 60 | BH | 集团在用客户 | `enterprise_active_customers` | static | auxiliary | CONFIRMED |
| 61 | BI | 所有客户 | `all_customers` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 62 | BJ | 0~90天库存 | `inventory_age_0_90_qty` | static | auxiliary | CONFIRMED |
| 63 | BK | 90～180天库存 | `inventory_age_90_180_qty` | static | auxiliary | CONFIRMED |
| 64 | BL | 180～360天库存 | `inventory_age_180_360_qty` | static | auxiliary | CONFIRMED |
| 65 | BM | 360～540天库存 | `inventory_age_360_540_qty` | static | auxiliary | CONFIRMED |
| 66 | BN | 540+天库存 | `inventory_age_540_plus_qty` | static | auxiliary | CONFIRMED |
| 67 | BO | 0~90天库存剩余 | `remaining_inventory_age_0_90_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 68 | BP | 90～180天库存剩余 | `remaining_inventory_age_90_180_qty` | static | auxiliary | CONFIRMED |
| 69 | BQ | 180～360天库存剩余 | `remaining_inventory_age_180_360_qty` | static | auxiliary | CONFIRMED |
| 70 | BR | 360～540库存剩余 | `remaining_inventory_age_360_540_qty` | static | auxiliary | CONFIRMED |
| 71 | BS | 540+库存剩余 | `remaining_inventory_age_540_plus_qty` | static | auxiliary | CONFIRMED |
| 72 | BT | 规格型号 | `specification_model` | static | auxiliary | CONFIRMED |
| 73 | BU | 累计下单 | `cumulative_ordered_qty` | static | auxiliary | CONFIRMED |
| 74 | BV | 累计交付 | `cumulative_delivered_qty` | static | auxiliary | CONFIRMED |
| 75 | BW | OPEN PO | `open_po_qty` | static | auxiliary | CONFIRMED |
| 76 | BX | LT内需求数量 | `demand_within_lt_qty` | static | auxiliary | CONFIRMED |
| 77 | BY | 超物料LT Excess PO | `excess_po_beyond_material_lt_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 78 | BZ | KD最小包需求 | `kit_minimum_pack_demand_qty` | static | auxiliary | AUXILIARY_ONLY |
| 79 | CA | 良品VMI库存数量(试产) | `trial_good_vmi_inventory_qty` | static | auxiliary | CONFIRMED |
| 80 | CB | 良品非VMI库存数量(试产) | `trial_good_non_vmi_inventory_qty` | static | auxiliary | CONFIRMED |
| 81 | CC | 不良品库存数量(试产) | `trial_defective_inventory_qty` | static | auxiliary | CONFIRMED |
| 82 | CD | 虚拟不良品库存(试产) | `trial_virtual_defective_inventory_qty` | static | auxiliary | CONFIRMED |
| 83 | CE | VMI在途订单数量(试产) | `trial_vmi_in_transit_order_qty` | static | auxiliary | CONFIRMED |
| 84 | CF | 非VMI在途订单数量(试产) | `trial_non_vmi_in_transit_order_qty` | static | auxiliary | CONFIRMED |
| 85 | CG | VMI在途送货数量(试产) | `trial_vmi_in_transit_delivery_qty` | static | auxiliary | CONFIRMED |
| 86 | CH | 非VMI在途送货数量(试产) | `trial_non_vmi_in_transit_delivery_qty` | static | auxiliary | CONFIRMED |
| 87 | CI | 采购申请数量(试产) | `trial_purchase_requisition_qty` | static | auxiliary | CONFIRMED |
| 88 | CJ | 量产工单在制数量(试产) | `trial_mass_production_wip_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 89 | CK | 非标工单在制数量(试产) | `trial_nonstandard_wip_qty` | static | auxiliary | CONFIRMED |
| 90 | CL | 标准工单需求数量(试产) | `trial_standard_work_order_demand_qty` | static | auxiliary | CONFIRMED |
| 91 | CM | 非标准工单需求数量(试产) | `trial_nonstandard_work_order_demand_qty` | static | auxiliary | CONFIRMED |
| 92 | CN | 计划单需求数量(试产) | `trial_planned_order_demand_qty` | static | auxiliary | CONFIRMED |
| 93 | CO | 人工需求数量(试产) | `trial_manual_demand_qty` | static | auxiliary | CONFIRMED |
| 94 | CP | 长期预测需求(试产) | `trial_long_term_forecast_demand_qty` | static | auxiliary | CONFIRMED |
| 95 | CQ | 所有供应(试产) | `trial_all_supply_qty` | static | auxiliary | CONFIRMED |
| 96 | CR | 供需盈余量(试产) | `trial_supply_demand_surplus_qty` | static | auxiliary | CONFIRMED |
| 97 | CS | 供需汇总(试产) | `trial_supply_demand_summary_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 98 | CT | 计划单(试产) | `trial_planned_order_qty` | static | auxiliary | CONFIRMED |
| 99 | CU | 已到期预测计划单(试产) | `trial_expired_forecast_planned_order_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 100 | CV | 未到期预测计划单(试产) | `trial_unexpired_forecast_planned_order_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 101 | CW | 多余库存(试产) | `trial_excess_inventory_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 102 | CX | 多余采购数量(试产) | `trial_excess_purchase_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 103 | CY | 多余工单数量(试产) | `trial_excess_work_order_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 104 | CZ | 多余pr数量(试产) | `trial_excess_purchase_requisition_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 105 | DA | 实际需求合计 | `actual_demand_total_qty` | static | core | CONFIRMED |
| 106 | DB | 实际需求合计(试产) | `trial_actual_demand_total_qty` | static | auxiliary | CONFIRMED |

## Report 3：计划备料半年预测

来源：`报表3_计划备料半年预测表_最终模板.xlsx`；业务列数：23；表头行：[3]。

只读表头结构指纹：`aa4c71c711bb1bfc80c027f6393d246c99885f7f6c82b923ceb55d55f7fdd2b3`。

| Sheet | 表头行 | 角色 |
|---|---|---|
| 计划备料半年预测 | [3] | 业务主表 |
| 版本日历 | [1] | 辅助结构 |
| 字段说明 | [1] | 辅助结构 |

| 列号 | Excel列 | display_name / 完整层级 | canonical_field | dynamic/static | core/auxiliary | business_status |
|---:|---|---|---|---|---|---|
| 1 | A | 物料编码 | `material_code` | static | core | CONFIRMED |
| 2 | B | BG | `business_group_name` | static | auxiliary | CONFIRMED |
| 3 | C | 事业部 | `business_unit_name` | static | auxiliary | CONFIRMED |
| 4 | D | 计划部 | `planning_department_name` | static | auxiliary | CONFIRMED |
| 5 | E | 项目 | `project_name` | static | core | CONFIRMED |
| 6 | F | 客户项目 | `customer_project_name` | static | auxiliary | CONFIRMED |
| 7 | G | 客户 | `customer_name` | static | auxiliary | CONFIRMED |
| 8 | H | 品牌 | `brand_name` | static | auxiliary | CONFIRMED |
| 9 | I | 产品类型 | `product_type` | static | auxiliary | CONFIRMED |
| 10 | J | 出货类型 | `shipment_type` | static | auxiliary | CONFIRMED |
| 11 | K | 业务模式 | `business_mode` | static | auxiliary | CONFIRMED |
| 12 | L | 数据来源 | `forecast_source` | static | auxiliary | CONFIRMED |
| 13 | M | 数据版本 | `forecast_version_name` | static | core | CONFIRMED |
| 14 | N | 版本日期 | `forecast_version_date` | static | core | CONFIRMED |
| 15 | O | 预测月1 | `forecast_qty_m0` | dynamic (month 1) | core | CONFIRMED |
| 16 | P | 预测月2 | `forecast_qty_m1` | dynamic (month 2) | core | CONFIRMED |
| 17 | Q | 预测月3 | `forecast_qty_m2` | dynamic (month 3) | core | CONFIRMED |
| 18 | R | 预测月4 | `forecast_qty_m3` | dynamic (month 4) | core | CONFIRMED |
| 19 | S | 预测月5 | `forecast_qty_m4` | dynamic (month 5) | core | CONFIRMED |
| 20 | T | 预测月6 | `forecast_qty_m5` | dynamic (month 6) | core | CONFIRMED |
| 21 | U | 预测月7 | `forecast_qty_m6` | dynamic (month 7) | core | CONFIRMED |
| 22 | V | 汇总 | `forecast_total_qty` | static | core | CONFIRMED |
| 23 | W | 累计发货 | `cumulative_shipped_qty` | static | core | CONFIRMED |

## Report 4：最新版13周预测

来源：`报表4_最新版13周预测表_最终模板.xlsx`；业务列数：44；表头行：[2, 3]。

只读表头结构指纹：`77f4ec1bd977bc289132e9c6dc3e7d8fb1ebf3cdf8e8472ddb1228bf12194ad9`。

| Sheet | 表头行 | 角色 |
|---|---|---|
| 最新版13周预测 | [2, 3] | 业务主表 |
| 字段说明 | [1] | 辅助结构 |
| 与报表2关联 | [1] | 辅助结构 |

| 列号 | Excel列 | display_name / 完整层级 | canonical_field | dynamic/static | core/auxiliary | business_status |
|---:|---|---|---|---|---|---|
| 1 | A | 物料编码 | `material_code` | static | core | CONFIRMED |
| 2 | B | 组织编码 | `organization_code` | static | auxiliary | CONFIRMED |
| 3 | C | 规格型号 | `specification_model` | static | auxiliary | CONFIRMED |
| 4 | D | 组织在用项目 | `organization_active_projects` | static | auxiliary | CONFIRMED |
| 5 | E | 集团在用项目 | `enterprise_active_projects` | static | auxiliary | CONFIRMED |
| 6 | F | 最多项目 | `top_project` | static | auxiliary | CONFIRMED |
| 7 | G | 品牌 | `brand_name` | static | auxiliary | CONFIRMED |
| 8 | H | 物料说明 | `material_description` | static | auxiliary | CONFIRMED |
| 9 | I | 替代组 | `substitute_group_code` | static | auxiliary | CONFIRMED |
| 10 | J | 供应商 | `supplier_code` | static | auxiliary | CONFIRMED |
| 11 | K | 供应商(英文) | `supplier_name_en` | static | auxiliary | CONFIRMED |
| 12 | L | 在用配置 | `active_configurations` | static | auxiliary | CONFIRMED |
| 13 | M | PCBA配置 | `assembled_board_configurations` | static | auxiliary | CONFIRMED |
| 14 | N | 采购员 | `buyer_name` | static | auxiliary | CONFIRMED |
| 15 | O | 物控员 | `material_controller_account` | static | auxiliary | CONFIRMED |
| 16 | P | 物控员名字 | `material_controller_name` | static | auxiliary | CONFIRMED |
| 17 | Q | 物控员代码 | `material_controller_code` | static | auxiliary | CONFIRMED |
| 18 | R | MPQ | `minimum_pack_qty` | static | auxiliary | CONFIRMED |
| 19 | S | 加工中提前期 | `in_process_lt_days` | static | auxiliary | CONFIRMED |
| 20 | T | OPEN PR | `open_purchase_requisition_qty` | static | auxiliary | CONFIRMED |
| 21 | U | OPEN PO | `open_po_qty` | static | auxiliary | CONFIRMED |
| 22 | V | ASN | `advance_shipping_notice_qty` | static | auxiliary | CONFIRMED |
| 23 | W | 其他供应 | `other_supply_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 24 | X | 不良品子库 | `defective_subinventory_qty` | static | auxiliary | CONFIRMED |
| 25 | Y | 虚拟不良品库存 | `virtual_defective_inventory_qty` | static | auxiliary | CONFIRMED |
| 26 | Z | 良品子库 | `good_subinventory_qty` | static | auxiliary | CONFIRMED |
| 27 | AA | 库存已抵扣需求 | `inventory_net_of_demand_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 28 | AB | 历史累计下单总量 | `historical_cumulative_ordered_qty` | static | auxiliary | CONFIRMED |
| 29 | AC | 数据快照日期 | `snapshot_date` | static | core | CONFIRMED |
| 30 | AD | 第1周 | `week_01_forecast_qty` | dynamic (week 1) | core | CONFIRMED |
| 31 | AE | 第2周 | `week_02_forecast_qty` | dynamic (week 2) | core | CONFIRMED |
| 32 | AF | 第3周 | `week_03_forecast_qty` | dynamic (week 3) | core | CONFIRMED |
| 33 | AG | 第4周 | `week_04_forecast_qty` | dynamic (week 4) | core | CONFIRMED |
| 34 | AH | 第5周 | `week_05_forecast_qty` | dynamic (week 5) | core | CONFIRMED |
| 35 | AI | 第6周 | `week_06_forecast_qty` | dynamic (week 6) | core | CONFIRMED |
| 36 | AJ | 第7周 | `week_07_forecast_qty` | dynamic (week 7) | core | CONFIRMED |
| 37 | AK | 第8周 | `week_08_forecast_qty` | dynamic (week 8) | core | CONFIRMED |
| 38 | AL | 第9周 | `week_09_forecast_qty` | dynamic (week 9) | core | CONFIRMED |
| 39 | AM | 第10周 | `week_10_forecast_qty` | dynamic (week 10) | core | CONFIRMED |
| 40 | AN | 第11周 | `week_11_forecast_qty` | dynamic (week 11) | core | CONFIRMED |
| 41 | AO | 第12周 | `week_12_forecast_qty` | dynamic (week 12) | core | CONFIRMED |
| 42 | AP | 第13周 | `week_13_forecast_qty` | dynamic (week 13) | core | CONFIRMED |
| 43 | AQ | 13周需求合计 | `thirteen_week_demand_qty` | static | core | CONFIRMED |
| 44 | AR | 周均需求 | `weekly_average_demand_qty` | static | core | CONFIRMED |

## Report 5：产品配置查询

来源：`报表5_产品配置查询表_最终模板.xlsx`；业务列数：22；表头行：[3]。

只读表头结构指纹：`0983a73589589f708277edab39a380bdb4311491b940a37c0e61f6a297a98244`。

| Sheet | 表头行 | 角色 |
|---|---|---|
| 产品配置查询 | [3] | 业务主表 |
| 字段说明 | [1] | 辅助结构 |
| 使用逻辑 | [1] | 辅助结构 |

| 列号 | Excel列 | display_name / 完整层级 | canonical_field | dynamic/static | core/auxiliary | business_status |
|---:|---|---|---|---|---|---|
| 1 | A | 行号 | `row_number` | static | auxiliary | CONFIRMED |
| 2 | B | 产品配置类型 | `product_config_type` | static | auxiliary | CONFIRMED |
| 3 | C | 产品配置名 | `product_config_name` | static | auxiliary | CONFIRMED |
| 4 | D | 产品名称 | `product_name` | static | auxiliary | CONFIRMED |
| 5 | E | 版本 | `product_config_version` | static | auxiliary | CONFIRMED |
| 6 | F | 物料编码 | `material_code` | static | core | CONFIRMED |
| 7 | G | 客户料号 | `customer_material_code` | static | auxiliary | CONFIRMED |
| 8 | H | 所属事业部 | `business_unit_name` | static | core | CONFIRMED |
| 9 | I | 计划部门 | `planning_department_name` | static | core | CONFIRMED |
| 10 | J | 项目 | `project_name` | static | core | CONFIRMED |
| 11 | K | 客户项目名 | `customer_project_name` | static | auxiliary | CONFIRMED |
| 12 | L | 研发代表 | `research_representative_name` | static | auxiliary | CONFIRMED |
| 13 | M | 修改者 | `modified_by_name` | static | auxiliary | CONFIRMED |
| 14 | N | 修改时间 | `modified_at` | static | auxiliary | CONFIRMED |
| 15 | O | 状态 | `product_config_status` | static | auxiliary | CONFIRMED |
| 16 | P | 产品一级 | `product_category_level_1` | static | auxiliary | CONFIRMED |
| 17 | Q | 产品二级 | `product_category_level_2` | static | auxiliary | CONFIRMED |
| 18 | R | 产品三级 | `product_category_level_3` | static | auxiliary | CONFIRMED |
| 19 | S | 产品生命周期阶段 | `lifecycle_stage` | static | core | CONFIRMED |
| 20 | T | 客户ID | `customer_code` | static | auxiliary | CONFIRMED |
| 21 | U | 客户代号 | `customer_short_code` | static | auxiliary | CONFIRMED |
| 22 | V | PDT团队名 | `product_team_name` | static | auxiliary | CONFIRMED |

## Report 6：囤料明细

来源：`报表6_囤料明细_最终模板.xlsx`；业务列数：60；表头行：[3, 4, 5]。

只读表头结构指纹：`a466ca0b52d4be200054274b1c29473029473aef2030f13e0e92e0c973ab6e86`。

| Sheet | 表头行 | 角色 |
|---|---|---|
| 囤料明细 | [3, 4, 5] | 业务主表 |
| 字段说明 | [1] | 辅助结构 |
| 使用逻辑 | [1] | 辅助结构 |

| 列号 | Excel列 | display_name / 完整层级 | canonical_field | dynamic/static | core/auxiliary | business_status |
|---:|---|---|---|---|---|---|
| 1 | A | 数据版本 | `stockpile_version_name` | static | core | CONFIRMED |
| 2 | B | 版本日期 | `stockpile_version_date` | static | core | CONFIRMED |
| 3 | C | 囤料性质 | `stockpile_nature` | static | auxiliary | CONFIRMED |
| 4 | D | 采购类别 | `purchasing_category` | static | auxiliary | CONFIRMED |
| 5 | E | 分析类别 | `analysis_category` | static | auxiliary | CONFIRMED |
| 6 | F | 料号 | `material_code` | static | core | CONFIRMED |
| 7 | G | 型号 | `model` | static | auxiliary | CONFIRMED |
| 8 | H | 物料描述 | `material_description` | static | auxiliary | CONFIRMED |
| 9 | I | 库存单价 | `inventory_unit_price` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 10 | J | 协议单价 | `agreement_unit_price` | static | auxiliary | CONFIRMED |
| 11 | K | 计划囤料数量 | `planned_stockpile_qty` | static | core | CONFIRMED |
| 12 | L | 计划囤料金额(万元) | `planned_stockpile_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 13 | M | 库存数量 | `inventory_qty` | static | auxiliary | CONFIRMED |
| 14 | N | 七天需求数量 | `seven_day_demand_qty` | static | auxiliary | CONFIRMED |
| 15 | O | 总囤料数量（扣除7天需求） | `net_stockpile_qty_after_7d_demand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 16 | P | 总囤料金额(万元) | `total_stockpile_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 17 | Q | 囤料数量GAP分析(计划-实际) | `stockpile_qty_gap` | static | auxiliary | CONFIRMED |
| 18 | R | 囤货完成率 | `stockpile_completion_ratio` | static | auxiliary | CONFIRMED |
| 19 | S | 超目标囤料金额(万元) | `excess_target_stockpile_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 20 | T | 囤料不足预警 | `stockpile_shortage_warning` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 21 | U | 需求预测数量-未来半年 → 未来第1月 | `future_month_01_demand_qty` | dynamic (month 1) | core | CONFIRMED |
| 22 | V | 需求预测数量-未来半年 → 未来第2月 | `future_month_02_demand_qty` | dynamic (month 2) | core | CONFIRMED |
| 23 | W | 需求预测数量-未来半年 → 未来第3月 | `future_month_03_demand_qty` | dynamic (month 3) | core | CONFIRMED |
| 24 | X | 需求预测数量-未来半年 → 未来第4月 | `future_month_04_demand_qty` | dynamic (month 4) | core | CONFIRMED |
| 25 | Y | 需求预测数量-未来半年 → 未来第5月 | `future_month_05_demand_qty` | dynamic (month 5) | core | CONFIRMED |
| 26 | Z | 需求预测数量-未来半年 → 未来第6月 | `future_month_06_demand_qty` | dynamic (month 6) | core | CONFIRMED |
| 27 | AA | 结余预测（库存-消耗）(万元) → 超30天未消耗 → 数量 | `remaining_after_30d_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 28 | AB | 结余预测（库存-消耗）(万元) → 超30天未消耗 → 金额 | `remaining_after_30d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 29 | AC | 结余预测（库存-消耗）(万元) → 超60天未消耗 → 数量 | `remaining_after_60d_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 30 | AD | 结余预测（库存-消耗）(万元) → 超60天未消耗 → 金额 | `remaining_after_60d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 31 | AE | 结余预测（库存-消耗）(万元) → 超90天未消耗 → 数量 | `remaining_after_90d_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 32 | AF | 结余预测（库存-消耗）(万元) → 超90天未消耗 → 金额 | `remaining_after_90d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 33 | AG | 结余预测（库存-消耗）(万元) → 超120天未消耗 → 数量 | `remaining_after_120d_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 34 | AH | 结余预测（库存-消耗）(万元) → 超120天未消耗 → 金额 | `remaining_after_120d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 35 | AI | 结余预测（库存-消耗）(万元) → 超150天未消耗 → 数量 | `remaining_after_150d_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 36 | AJ | 结余预测（库存-消耗）(万元) → 超150天未消耗 → 金额 | `remaining_after_150d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 37 | AK | 结余预测（库存-消耗）(万元) → 超180天未消耗 → 数量 | `remaining_after_180d_qty` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 38 | AL | 结余预测（库存-消耗）(万元) → 超180天未消耗 → 金额 | `remaining_after_180d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 39 | AM | 囤料消耗预警 | `stockpile_consumption_warning` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 40 | AN | 库龄分布(万元) → 超30天 → 数量 | `inventory_age_over_30d_qty` | static | auxiliary | CONFIRMED |
| 41 | AO | 库龄分布(万元) → 超30天 → 金额 | `inventory_age_over_30d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 42 | AP | 库龄分布(万元) → 超60天 → 数量 | `inventory_age_over_60d_qty` | static | auxiliary | CONFIRMED |
| 43 | AQ | 库龄分布(万元) → 超60天 → 金额 | `inventory_age_over_60d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 44 | AR | 库龄分布(万元) → 超90天 → 数量 | `inventory_age_over_90d_qty` | static | auxiliary | CONFIRMED |
| 45 | AS | 库龄分布(万元) → 超90天 → 金额 | `inventory_age_over_90d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 46 | AT | 库龄分布(万元) → 超120天 → 数量 | `inventory_age_over_120d_qty` | static | auxiliary | CONFIRMED |
| 47 | AU | 库龄分布(万元) → 超120天 → 金额 | `inventory_age_over_120d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 48 | AV | 库龄分布(万元) → 超150天 → 数量 | `inventory_age_over_150d_qty` | static | auxiliary | CONFIRMED |
| 49 | AW | 库龄分布(万元) → 超150天 → 金额 | `inventory_age_over_150d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 50 | AX | 库龄分布(万元) → 超180天 → 数量 | `inventory_age_over_180d_qty` | static | auxiliary | CONFIRMED |
| 51 | AY | 库龄分布(万元) → 超180天 → 金额 | `inventory_age_over_180d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 52 | AZ | 库龄分布(万元) → 超270天 → 数量 | `inventory_age_over_270d_qty` | static | auxiliary | CONFIRMED |
| 53 | BA | 库龄分布(万元) → 超270天 → 金额 | `inventory_age_over_270d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 54 | BB | 库龄分布(万元) → 超365天 → 数量 | `inventory_age_over_365d_qty` | static | auxiliary | CONFIRMED |
| 55 | BC | 库龄分布(万元) → 超365天 → 金额 | `inventory_age_over_365d_amount_ten_thousand` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 56 | BD | 囤料呆滞预警 | `stockpile_obsolescence_warning` | static | auxiliary | DEFERRED_BUSINESS_FORMULA |
| 57 | BE | 责任人 | `owner_name` | static | auxiliary | CONFIRMED |
| 58 | BF | 责任人部门 | `owner_department_name` | static | auxiliary | CONFIRMED |
| 59 | BG | 责任经理 | `owner_manager_name` | static | auxiliary | CONFIRMED |
| 60 | BH | 责任总监 | `owner_director_name` | static | auxiliary | CONFIRMED |
