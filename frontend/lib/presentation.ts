import type { Metric } from "./contracts.ts";

const labels: Record<string, string> = {
  TRIAL: "试产采购", STOCKPILE: "历史囤料", DEMAND_ADJUSTMENT: "需求调整", AFTER_SALES: "售后需求", PROJECT_OBSOLESCENCE: "项目呆滞",
  DIAGNOSED: "已确定原因", UNRESOLVED: "诊断 / 处置未决", NOT_EVALUABLE: "当前无法确定处置", NOT_APPLICABLE: "不适用", NOT_ELIGIBLE: "不满足诊断资格", COMPLETED: "分析完成", FAILED: "分析未完成", NEEDS_CLARIFICATION: "需要补充信息", NOT_FOUND: "未找到匹配订单", DECIDED: "已有处置建议",
  AVAILABLE: "可计算", PARTIAL: "部分可用", NOT_COMPUTABLE: "不可计算", OPEN: "开放", CLOSED: "已关闭", PARTIALLY_RECEIVED: "部分收货",
  MPM: "物料 MPM", CUSTOMER: "客户", SUPPLIER: "供应商", BUSINESS_UNIT: "事业部",
  REQUEST_MPM_CONFIRMATION: "交由物料 MPM 确认处理", CONTINUE_CONSUMPTION: "持续消耗", NEGOTIATE_SUPPLIER_ORDER_REDUCTION: "与供应商沟通砍单", COMMUNICATE_CUSTOMER_OBSOLESCENCE: "沟通客户处理呆滞", COMMUNICATE_BUSINESS_UNIT_OBSOLESCENCE: "沟通事业部处理呆滞",
  OVERDUE_THRESHOLD_EXCEEDED: "已越过超期阈值", HISTORICAL_STOCKPILE_RECORD_PRESENT: "存在历史囤料记录（不单独决定主原因）", NEGATIVE_FORECAST_CHANGE: "可比较预测出现负向变化",
  po_age_days: "PO 年龄", threshold_days: "超期阈值", days_beyond_threshold: "越过阈值", open_qty: "开放数量", total_forecast_qty: "13 周预测需求", average_weekly_demand_qty: "平均周需求", estimated_consumption_weeks: "预计消耗时间",
  LLM_NOT_CONFIGURED: "未配置模型，已使用确定性回答", LLM_TIMEOUT: "模型超时，已使用确定性回答", LLM_UNAVAILABLE: "模型不可用，已使用确定性回答", GROUNDING_REJECTED: "模型回答未通过证据校验，已安全回退",
};
export function label(code: string | null | undefined) { return code ? labels[code] ?? code : "未明确"; }
// Decimal strings remain strings. Formatting does not change their numerical value.
export function quantity(value: string | number | null | undefined): string {
  if (value == null) return "—";
  const s = String(value);
  if (/^-?\d+(\.\d+)?e[+-]?\d+$/i.test(s)) return s;
  if (!/^-?\d+(\.\d+)?$/.test(s)) return "—";
  const [whole, decimal] = s.split(".");
  const fraction = decimal?.replace(/0+$/, "");
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (fraction ? "." + fraction : "");
}
export function metricValue(metric: Metric) { return metric.value === null ? "Not computable" : quantity(metric.value); }
export function compactMetric(metric: Metric) {
  const full = metricValue(metric);
  if (/[eE][+-]?\d+$/.test(full)) return full;
  const [whole, fraction] = full.split(".");
  return fraction && fraction.length > 4 ? `${whole}.${fraction.slice(0,4)}…` : full;
}
export function errorText(error: unknown) {
  if (error instanceof Error && error.message === "NOT_FOUND") return "在当前数据集中未找到此记录，请返回工作台重新选择。";
  if (error instanceof Error && error.message === "INVALID_RESPONSE") return "服务返回的数据不完整或上下文不一致，已停止展示，请重试。";
  return "暂时无法连接数据服务。请确认 System A / System B 已启动，然后重试。";
}
