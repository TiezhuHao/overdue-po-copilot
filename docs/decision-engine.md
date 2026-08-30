# System B Decision Engine — Phase 3

Analytics回答What（数字），Diagnosis回答Why（原因），Decision回答What to do（结构化处置），未来Agent负责How to interact。Decision不执行采购操作、不发消息、不访问HTTP/数据库，也不调用诊断规则重新选原因。

正式来源、逐条required evidence、owner、checks、exclusions、priority及缺口见 [decision-rule-specification.md](decision-rule-specification.md)。规格先于代码建立。

## Modules and input

- `decision/models.py`：不可变DecisionContext、BusinessDecisionPolicy、Action、Result和状态。
- `decision/rules.py`：六个有序显式DecisionRule，精确绑定主诊断类型/规则/版本；不含根因谓词。
- `decision/engine.py`：校验血缘，匹配primary，核验分支依赖，映射动作及证据闭包。

入口`decide(context)`只接受BusinessDiagnosisResult、同一EvidenceBundle和可选显式消费Policy。PO的dataset/snapshot/header/line/schedule/material/organization身份必须一致。再使用已有Assembler核验Canonical输入和派生事实，拒绝拼接外来指标；不调用`diagnose`、`diagnose_business`或`select_primary`。

这是进程内可信Diagnosis的类型/血缘校验，不是签名认证：不能证明调用者从未伪造一个语义上自洽的Diagnosis。由受信任上层串联Diagnosis和Decision，不能让外部用户自行提交原因来执行操作。损坏输入抛ValidationError、EvidenceAssemblyError或DecisionInputError，不能将损坏数据转换成业务结论。

```python
from app.system_b.decision.models import DecisionContext, CONFIRMED_CONSUMPTION_POLICY
from app.system_b.decision.engine import decide

# bundle and diagnosis come from the existing assembler / diagnosis entry points.
result = decide(DecisionContext(
    diagnosis=diagnosis,
    evidence=bundle,
    policy=CONFIRMED_CONSUMPTION_POLICY,
))
```

不增加API或HTTP orchestration。调用者先收集Canonical输入；各规则只把实际需要的证据作为动作前提。试产无需Forecast、项目、囤料或消费Policy；客户/内部处置使用已匹配诊断的来源，不重新判断lifecycle。

## Policy and actions

Decision规则版本1.0.0，支持诊断routing版本2.0.0；TRIAL主规则1.0.0，其余主规则2.0.0。未知组合不可决策；客户/内部PROJECT_OBSOLESCENCE绑定不同规则、动作和处理方。

消费Policy是`confirmed_consumption / 1.0.0`，正式6个月阈值来自AT-037与场景规则；调用者显式选择，不默认注入。该版本不接受未经确认的新阈值。未传Policy或threshold_months=null时消费分支不可决策。Policy全文、fingerprint和实际`used_policy_fields`进入结果；非消费分支不使用该阈值。

月数由Analytics周数×12/52得到；动作比较周数与6×52/12，阈值当天走沟通供应商砍单。40位ROUND_HALF_EVEN的局部context覆盖整个决策，包括验证，隔离调用方Decimal precision/rounding/flags。未修改Analytics公式；40位输入结果更早发生的舍入无法恢复。

只实现REQUEST_MPM_CONFIRMATION、CONTINUE_CONSUMPTION、NEGOTIATE_SUPPLIER_ORDER_REDUCTION、COMMUNICATE_CUSTOMER_OBSOLESCENCE、COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE。供应商动作仅沟通砍单，不是立即取消，不包含取消数量、时间窗口或执行授权。下降/后移没有额外改期映射。

Action有action_code、owner_role、priority、required、evidence_refs、decision_rule_id/version和可选mpm_contact。owner_role表示业务处理方/沟通对象，不等同于执行采购员。持续消耗负责角色未确认，null+非阻断规格缺口；不暗加BUYER。MPM联系人仅来自R2物料关联；缺employee_id或有效来源时试产不产生动作。其它处理方不附伪造联系人。

每次仅一个主规则、最多一个动作，不需要sequence或去重平台。priority是registry顺序，required表示规则输出，不是自动执行许可。

## Availability and trace

| State | Behavior |
|---|---|
| DECIDED | 必要检查通过，有一个确定动作；可携带非阻断角色缺口 |
| NOT_APPLICABLE | 诊断NOT_ELIGIBLE，无动作 |
| NOT_EVALUABLE | 诊断UNRESOLVED/NO_MATCH、未知版本、缺关键证据/参数或处置规格，无动作 |

required_checks逐项包含稳定code、passed和evidence_refs。unresolved_requirements包含code、requirement、blocking、source；code为DIAGNOSIS_UNRESOLVED、UNSUPPORTED_DIAGNOSIS_RULE、MISSING_REQUIRED_EVIDENCE、MISSING_POLICY_PARAMETER、DECISION_SPEC_GAP。

source_diagnosis保留原结果全文，包括primary rule/version、诊断Policy/参数/fingerprint、支持信号和trace。Decision保存匹配规则/版本及自己的Policy；Action refs覆盖来源诊断与动作新增MPM/消耗证据，evidence_trace递归包含所有derived_from父事实。因规则只选primary，无合并导致的来源丢失。R3/R4证据的版本、日期、实体键原样保留。

零Forecast绝不视为无限消耗或自动砍单。当前完整诊断通常先因零贡献而UNRESOLVED，Decision尊重该结果；若消费分支收到零需求不可计算证据，则明确ZERO_FORECAST_ACTION规格缺口。部分/缺Forecast不会当成0。

售后Diagnosis可以成立，但DC-16处置未确认，因此after-sales Decision始终NOT_EVALUABLE，无保留全部/取消全部的伪动作。持续消耗owner、零需求处置、售后正式策略和采购执行授权仍待业务确认。

## Verification

在backend运行`python -m pytest tests/test_system_b_decision.py -q`。固定Canonical fixtures覆盖六条业务路径、EOL/非EOL、需求后移、6个月前/当日/之后、零/非法数量、缺MPM/Policy/Forecast、未知版本、来源篡改、确定性、Decimal隔离及依赖边界；不依赖真实System A、数据库、当前日期或网络。
