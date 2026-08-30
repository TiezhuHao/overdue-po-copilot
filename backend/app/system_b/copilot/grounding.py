"""Projection, presentation validation and fallback. No business calculations."""
from app.system_b.agent.models import AgentExecutionResult
from app.system_b.copilot.models import (
    GroundingPacket, GroundedFact, MetricValue, ProjectValue, EvidenceReference,
    CopilotAnswerDraft, DraftSection, DraftLine,
)


REASONS = {"TRIAL": "试产", "STOCKPILE": "历史囤料", "DEMAND_ADJUSTMENT": "需求调整",
           "AFTER_SALES": "售后需求", "PROJECT_OBSOLESCENCE": "项目呆滞"}
OWNERS = {"MPM": "物料MPM", "CUSTOMER": "客户", "SUPPLIER": "供应商", "BUSINESS_UNIT": "事业部"}
ACTIONS = {
    "REQUEST_MPM_CONFIRMATION": "交由物料MPM确认处理。",
    "CONTINUE_CONSUMPTION": "持续消耗。",
    "NEGOTIATE_SUPPLIER_ORDER_REDUCTION": "沟通供应商砍单；这不代表已执行取消。",
    "COMMUNICATE_CUSTOMER_OBSOLESCENCE": "沟通客户处理呆滞。",
    "COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE": "沟通事业部处理呆滞。",
}
HEADINGS = ("结论", "为什么", "关键数据", "建议动作", "数据 / 规则限制")


class GroundingError(ValueError):
    pass


def project_execution(result: AgentExecutionResult) -> GroundingPacket:
    """Select bounded facts exclusively from the existing AgentExecutionResult."""
    snapshot = result.request.snapshot_date
    refs = [EvidenceReference(reference_id="execution", source="AGENT", label="结构化执行结果", snapshot_date=snapshot)]
    facts, metrics, projects = [], [], []

    def fact(name, section, sentence, references=("execution",)):
        facts.append(GroundedFact(fact_id=name, section=section,
            allowed_sentences=(sentence, "根据现有结构化证据，" + sentence), evidence_reference_ids=references))

    fact("execution.status", "结论", f"本次业务分析状态为 {result.status}。")
    if result.resolved_identity:
        fact("identity.schedule", "结论", f"本次分析针对发运行 {result.resolved_identity.po_line_schedule_id}。")
    diagnosis, decision = result.diagnosis, result.decision
    reason = diagnosis.primary_reason.value if diagnosis and diagnosis.primary_reason else None
    owner = decision.owner_role.value if decision and decision.owner_role else None
    codes = tuple(action.action_code.value for action in decision.actions) if decision else ()
    if diagnosis:
        if diagnosis.primary_rule_id:
            refs.append(EvidenceReference(reference_id="diagnosis.rule", source="DIAGNOSIS",
                label=diagnosis.primary_rule_id, rule_version=diagnosis.primary_rule_version, snapshot_date=snapshot))
        if reason:
            fact("diagnosis.reason", "为什么", f"已确认的原因分类为{REASONS[reason]}（{reason}）。", ("diagnosis.rule",))
        else:
            fact("diagnosis.unresolved", "为什么", f"诊断状态为 {diagnosis.status}，当前没有确认的主原因。")
        signal_text = {
            "OVERDUE_THRESHOLD_EXCEEDED": "订单已越过超期阈值。",
            "HISTORICAL_STOCKPILE_RECORD_PRESENT": "存在历史囤料记录；单独存在记录不等于最终囤料原因。",
            "NEGATIVE_FORECAST_CHANGE": "可比较预测的数量变化为负；该支持信号不单独决定主原因。",
        }
        for signal in diagnosis.signals:
            fact("signal." + signal, "为什么", signal_text[signal])
    if decision and decision.decision_rule_id:
        refs.append(EvidenceReference(reference_id="decision.rule", source="DECISION", label=decision.decision_rule_id,
                                      rule_version=decision.decision_rule_version, snapshot_date=snapshot))
    decision_refs = ("decision.rule",) if decision and decision.decision_rule_id else ("execution",)
    if codes:
        for code in codes:
            fact(f"action.{code}", "建议动作", ACTIONS[code], decision_refs)
        fact("decision.owner", "建议动作", f"业务处理方或沟通对象为{OWNERS[owner]}。" if owner else "当前未明确负责角色，不补猜具体人员。", decision_refs)
    else:
        fact("decision.no_action", "建议动作", "当前没有可输出的确定采购动作，不自行补充取消或保留建议。", decision_refs)
    if result.analytics:
        refs.append(EvidenceReference(reference_id="analytics", source="ANALYTICS", label="确定性采购指标", snapshot_date=snapshot))
        analytics = result.analytics.metrics
        selected = (
            ("po_age_days", analytics.aging.po_age_days, "天", analytics.aging.status),
            ("threshold_days", analytics.aging.threshold_days, "天", analytics.aging.status),
            ("days_beyond_threshold", analytics.aging.days_beyond_threshold, "天", analytics.aging.status),
            ("open_qty", analytics.consumption.open_qty, "原始数量单位", analytics.consumption.status),
            ("total_forecast_qty", analytics.consumption.forecast.total_forecast_qty, "原始数量单位", analytics.consumption.forecast.status),
            ("average_weekly_demand_qty", analytics.consumption.forecast.average_weekly_demand_qty, "原始数量单位/周", analytics.consumption.forecast.status),
            ("estimated_consumption_weeks", analytics.consumption.estimated_consumption_weeks, "周", analytics.consumption.status),
        )
        labels = ("订单年龄", "超期判断阈值", "越过阈值天数", "当前开放数量", "未来13周预测需求", "平均周需求", "预计消耗时间")
        for (name, value, unit, status), label in zip(selected, labels, strict=True):
            text = str(value) if value is not None else None
            metrics.append(MetricValue(name=name, value=text, unit=unit, availability=status))
            fact("metric." + name, "关键数据", f"{label}：{text} {unit}。" if text is not None else f"{label}当前不可计算，不将未知值当作零。", ("analytics",))
        project_id = analytics.project_exposure.top_contributing_project
        if project_id:
            projects.append(ProjectValue(project_id=project_id, display_value=None))
            fact("project.contribution", "数据 / 规则限制", f"预测贡献最大项目为 {project_id}，这不表示责任归属。", ("analytics",))
    # Show bounded version references and selected categorical evidence, not the full trace.
    seen = set()
    for source in result.provenance.facts:
        keys = {key.name: key.value for key in source.entity_keys}
        version = keys.get("forecast_version_id") or keys.get("source_forecast_version_id") or keys.get("stockpile_version_id")
        if version and version not in seen and len(seen) < 6:
            seen.add(version)
            refs.append(EvidenceReference(reference_id=f"version.{version}", source=source.source,
                label=f"{source.source}证据版本", snapshot_date=source.snapshot_date, version_id=version, version_date=source.version_date))
        if source.evidence_id == "po.inventory_organization_type" and source.observed_value in ("TRIAL", "MASS_PRODUCTION"):
            fact("source.organization", "为什么", f"源库存组织类型为 {source.observed_value}。")
    if decision:
        for index, requirement in enumerate(decision.unresolved_requirements):
            fact(f"limitation.{index}", "数据 / 规则限制", f"尚未解决的要求：{requirement.requirement}（{requirement.code}）。", decision_refs)
    if diagnosis and diagnosis.rule_gaps:
        names = "、".join(sorted({gap.gap_id for gap in diagnosis.rule_gaps}))
        fact("diagnosis.gaps", "数据 / 规则限制", f"诊断仍存在规则或参数缺口：{names}。")
    if result.issues:
        names = "、".join(sorted({issue.code.value for issue in result.issues}))
        fact("execution.issues", "数据 / 规则限制", f"执行记录的限制状态：{names}。")
    fact("read_only", "数据 / 规则限制", "以上内容仅为只读分析与建议，未执行任何采购操作。")
    fact("quantity_unit", "数据 / 规则限制", "数量沿用上游原始单位，当前未确认统一计量单位。")
    return GroundingPacket(execution_status=result.status, primary_reason=reason, owner_role=owner,
        action_codes=codes, metrics=tuple(metrics), projects=tuple(projects), facts=tuple(facts), evidence_references=tuple(refs))


def validate_draft(packet: GroundingPacket, draft: CopilotAnswerDraft) -> CopilotAnswerDraft:
    draft = CopilotAnswerDraft.model_validate(draft.model_dump(warnings=False))
    if (draft.primary_reason != packet.primary_reason or draft.owner_role != packet.owner_role
            or tuple(draft.action_codes) != packet.action_codes):
        raise GroundingError("BUSINESS_CLAIM_MISMATCH")
    if (len(draft.metrics) != len(packet.metrics)
            or {item.name: item for item in draft.metrics} != {item.name: item for item in packet.metrics}
            or tuple(draft.projects) != packet.projects):
        raise GroundingError("METRIC_OR_PROJECT_MISMATCH")
    available = {fact.fact_id: fact for fact in packet.facts}
    headings, used = set(), set()
    for section in draft.sections:
        if section.heading in headings or not section.lines:
            raise GroundingError("INVALID_SECTION")
        headings.add(section.heading)
        for line in section.lines:
            fact = available.get(line.fact_id)
            if (fact is None or line.fact_id in used or fact.section != section.heading
                    or line.text not in fact.allowed_sentences
                    or tuple(line.evidence_reference_ids) != fact.evidence_reference_ids):
                raise GroundingError("UNSUPPORTED_WORDING_OR_REFERENCE")
            used.add(line.fact_id)
    if used != available.keys():
        raise GroundingError("OMITTED_FACT_OR_LIMITATION")
    return draft


def fallback_draft(packet: GroundingPacket) -> CopilotAnswerDraft:
    return CopilotAnswerDraft(primary_reason=packet.primary_reason, owner_role=packet.owner_role,
        action_codes=list(packet.action_codes), metrics=list(packet.metrics), projects=list(packet.projects),
        sections=[DraftSection(heading=heading, lines=[DraftLine(fact_id=fact.fact_id,
            text=fact.allowed_sentences[0], evidence_reference_ids=list(fact.evidence_reference_ids))
            for fact in packet.facts if fact.section == heading]) for heading in HEADINGS
            if any(fact.section == heading for fact in packet.facts)])


def render(draft: CopilotAnswerDraft) -> str:
    return "\n\n".join("### " + section.heading + "\n\n" + "\n".join(
        "- " + line.text + " [" + ", ".join(line.evidence_reference_ids) + "]" for line in section.lines)
        for section in draft.sections)
