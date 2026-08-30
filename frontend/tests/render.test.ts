import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { CopilotResult, Metric } from "../lib/contracts.ts";

// Use the existing TypeScript compiler and Node runner; no component/E2E framework.
const require = createRequire(import.meta.url);
type CompilingModule = NodeModule & { _compile: (source: string, filename: string) => void };
function compile(module: NodeModule, filename: string) {
  (module as CompilingModule)._compile(ts.transpileModule(readFileSync(filename, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText, filename);
}
require.extensions[".tsx"] = compile;
require.extensions[".ts"] = compile;
const { MetricCard, ResultCards, Loading, ErrorBox } = require("../components/ui.tsx") as {
  MetricCard: React.ComponentType<{ metric: Metric }>;
  ResultCards: React.ComponentType<{ result: CopilotResult }>;
  Loading: React.ComponentType<{ text?: string }>;
  ErrorBox: React.ComponentType<{ message: string }>;
};
const result: CopilotResult = { request_id: "test", status: "UNRESOLVED", answer: "", answer_source: "FALLBACK", resolved_identity: null, key_metrics: [], diagnosis: { status: "UNRESOLVED", primary_reason: null, primary_rule_id: null, primary_rule_version: null, supporting_signals: [] }, decision: { status: "NOT_EVALUABLE", rule_id: null, rule_version: null, owner_role: null, actions: [] }, evidence_references: [], limitations: [], candidate_schedule_ids: [], execution_reference: null };
test("Dashboard shared loading and error states have accessible text", () => {
  assert.match(renderToStaticMarkup(React.createElement(Loading)), /role="status"/);
  assert.match(renderToStaticMarkup(React.createElement(ErrorBox, { message: "服务不可用" })), /role="alert"/);
});
test("Detail unknown metric is explicitly not computable, not zero", () => {
  const html = renderToStaticMarkup(React.createElement(MetricCard, { metric: { name: "estimated_consumption_weeks", value: null, unit: "周", availability: "NOT_COMPUTABLE" } }));
  assert.match(html, /Not computable/); assert.doesNotMatch(html, /<strong[^>]*>0</);
});
test("Unresolved diagnosis does not imply a confirmed reason", () => {
  const html = renderToStaticMarkup(React.createElement(ResultCards, { result }));
  assert.match(html, /Insufficient evidence/); assert.match(html, /当前没有确定的采购动作/);
});
test("After-sales specification gap retains DC-16 and no fabricated action", () => {
  const html = renderToStaticMarkup(React.createElement(ResultCards, { result: { ...result, limitations: ["DECISION_SPEC_GAP DC-16"] } }));
  assert.match(html, /Decision specification incomplete/); assert.match(html, /DC-16/); assert.doesNotMatch(html, /action-row/);
});
test("Confirmed action and owner are presented from the API without reinterpretation", () => {
  const html = renderToStaticMarkup(React.createElement(ResultCards, { result: { ...result, decision: { status: "DECIDED", rule_id: "rule", rule_version: "1", owner_role: "CUSTOMER", actions: [{ action_code: "COMMUNICATE_CUSTOMER_OBSOLESCENCE", owner_role: "CUSTOMER", required: true }] } } }));
  assert.match(html, /沟通客户处理呆滞/); assert.doesNotMatch(html, /沟通事业部处理呆滞/);
});
