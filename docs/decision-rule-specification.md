# Deterministic Decision Specification — 1.0.0

本规格先于Phase 3代码建立。唯一输入为BusinessDiagnosisResult和同一PO/dataset的EvidenceBundle；不重新判断原因，不读取隐藏真值，不执行采购操作。

## Source audit

| 正式来源 | 已确认处置 | 边界 |
|---|---|---|
| SCENARIO_RULES §2、§6；DATA_CONTRACT §2 Material → MPM；AT-011 | 试产交物料MPM确认处理 | 不按金额筛选；不附加取消/改期 |
| SCENARIO_RULES §2、§7、§12；AT-037；AGENTS固定公式 | 非EOL需求调整、历史囤料：消耗月数<6持续消耗，>=6沟通供应商砍单 | DELAY没有单独改期动作；砍单仅沟通建议，不执行取消，不指定数量 |
| SCENARIO_RULES §10；AT-038 | 客户侧项目呆滞：沟通客户处理呆滞 | 不能映射成内部事业部路径 |
| SCENARIO_RULES §13；AT-042 | 内部项目呆滞：沟通事业部处理呆滞 | 不归责参考项目，不默认交MPM |
| DATA_CONTRACT DC-16；SCENARIO_RULES §11 | 售后正式动作、保留量、保供周期待确认 | DECISION_SPEC_GAP，无动作 |

审查范围还包括README、现有docs和场景测试。未找到支持自动Cancel、Reschedule、冻结新增采购、supplier cancel window、额外Forecast核实/项目确认步骤的正式映射。Prompt示例不作为授权来源。不通过这些步骤补齐未知处置。

## Rule registry

所有Decision规则version=1.0.0。精确匹配诊断code + primary_rule_id + primary_rule_version；支持routing_policy_version=2.0.0。诊断参数ID/version/fingerprint原样保留，不限定测试或企业参数配置。

| Decision rule ID | Diagnosis / source rule (version) | Additional required evidence | Owner role | Action | Required checks | Priority | Exclusions / missing behavior | Source |
|---|---|---|---|---|---|---|---|---|
| decision_trial | TRIAL / business_trial (1.0.0) | R2物料级有效MPM事实及employee_id | MPM | REQUEST_MPM_CONFIRMATION | MATERIAL_MPM_AVAILABLE | 10 | 缺MPM不可决策；不要求Forecast或项目 | §6、AT-011 |
| decision_customer_obsolescence | PROJECT_OBSOLESCENCE / business_customer_obsolescence (2.0.0) | 已匹配诊断的证据trace | CUSTOMER | COMMUNICATE_CUSTOMER_OBSOLESCENCE | SOURCE_DIAGNOSIS_VALID | 20 | 不需要消耗参数；不套内部路径 | §10、AT-038 |
| decision_demand_adjustment | DEMAND_ADJUSTMENT / business_demand_adjustment (2.0.0) | 可计算PO consumption；显式消费Policy | SUPPLIER或null | NEGOTIATE_SUPPLIER_ORDER_REDUCTION或CONTINUE_CONSUMPTION | CONSUMPTION_AVAILABLE、CONSUMPTION_POLICY_AVAILABLE | 30 | 缺/部分Forecast不可决策；零需求另有规格缺口 | §2、§7、AT-037 |
| decision_after_sales | AFTER_SALES / business_after_sales (2.0.0) | 无额外要求 | null | 无 | AFTER_SALES_SPEC_AVAILABLE失败 | 40 | 始终NOT_EVALUABLE / DECISION_SPEC_GAP | DC-16 |
| decision_stockpile | STOCKPILE / business_stockpile (2.0.0) | 同需求调整 | SUPPLIER或null | 同需求调整 | 同需求调整 | 50 | 囤料事实不等于无需处理；零需求不可猜 | §12、AT-037 |
| decision_internal_obsolescence | PROJECT_OBSOLESCENCE / business_internal_obsolescence (2.0.0) | 已匹配诊断的证据trace | BUSINESS_UNIT | COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE | SOURCE_DIAGNOSIS_VALID | 60 | 不需要消耗参数；不套客户路径 | §13、AT-042 |

共同检查SOURCE_DIAGNOSIS_VALID验证输入结构、身份、派生证据、trace与已匹配主规则。NOT_ELIGIBLE → NOT_APPLICABLE；UNRESOLVED/NO_MATCH → NOT_EVALUABLE，无动作。未知rule/version → UNSUPPORTED_DIAGNOSIS_RULE，不fallback。完整证据重组仅用于验证传入派生值，不调用任何诊断规则。

## Policy and units

BusinessDecisionPolicy必须显式提供给消费分支。提供可直接选用的CONFIRMED_CONSUMPTION_POLICY：ID=confirmed_consumption、version=1.0.0、threshold_months=6，来源AT-037/SCENARIO_RULES §7/§12。该版本只接受正式值6，不支持任意修改阈值；没有隐式选择默认配置。缺Policy或缺threshold字段 → MISSING_POLICY_PARAMETER。

Analytics的estimated_consumption_weeks转换为months = weeks ×12/52，采用独立40位ROUND_HALF_EVEN局部Decimal context。比较用weeks与threshold_months×52/12，避免先舍入显示月数；6个月即26周。输入为已有Analytics的40位结果，不承诺恢复被上游舍入的信息。不修改Analytics公式。

## Owner, checks and action semantics

owner_role表示正式来源明确的业务处理方/沟通对象，不表示自动发送者或已确认执行采购员。MPM、CUSTOMER、SUPPLIER、BUSINESS_UNIT均源自正式动作对象。持续消耗没有已确认负责角色：owner_role=null，非阻断DECISION_SPEC_GAP(CONSUMPTION_OWNER)，不能凭常识补BUYER。动作仍可确定。采购执行人、具体客户/事业部联系人不是当前规则必要证据，不伪造。

MPM角色与mpm_contact分离；仅从R2物料关系附联系人。缺联系人阻断试产动作。不从参考项目或贡献项目推导联系人。

每个动作含code、owner_role、priority、required、evidence_refs、decision rule ID/version；结果保留source diagnosis全文、Policy全文/fingerprint、required_checks、unresolved_requirements及证据闭包。所有动作均为只读建议，required表示该规则的确定输出，不是执行授权。

每次只映射一个primary rule且最多一个动作，无动作依赖或重复合并需求，故不实现sequence/de-dup平台。规则priority仅用于显式registry排序，不重排Diagnosis。

## Remaining specification gaps

- DC-16：售后正式动作、保留数量、保供周期。
- ZERO_FORECAST_ACTION：13周无需求不能推定供应商砍单或继续保留。
- CONSUMPTION_OWNER：持续消耗处理角色未明确（非阻断）。
- 执行授权、具体处理数量、供应商取消窗口、改期/冻结映射均未确认；不实现。
