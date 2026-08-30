import { test } from "node:test";
import assert from "node:assert/strict";
import { api } from "../lib/client.ts";
import { copilotResult, orderPage } from "../lib/contracts.ts";
import { quantity, metricValue, compactMetric, errorText } from "../lib/presentation.ts";

const result = { request_id: "fixture", status: "UNRESOLVED", answer_source: "FALLBACK", answer: "证据不足", resolved_identity: null, key_metrics: [], diagnosis: null, decision: null, evidence_references: [], limitations: ["DC-16"], candidate_schedule_ids: [], execution_reference: null };
test("Decimal presentation preserves zero, null and all significant digits", () => {
  assert.equal(quantity("12345678901234567890.0100"), "12,345,678,901,234,567,890.01");
  assert.equal(quantity("0.0000"), "0"); assert.equal(quantity(null), "—");
  assert.equal(quantity("1E-20"), "1E-20");
  assert.equal(compactMetric({ name: "demand", value: "1.23456789E-20", unit: "数量", availability: "AVAILABLE" }), "1.23456789E-20");
  assert.equal(metricValue({ name: "forecast", value: null, unit: "周", availability: "NOT_COMPUTABLE" }), "Not computable");
});
test("invalid or partial payload cannot masquerade as a valid response", () => {
  assert.throws(() => orderPage({ items: [] }));
  assert.throws(() => copilotResult({ ...result, status: "MODEL_GUESSED" }));
  assert.throws(() => copilotResult({ ...result, key_metrics: [{ name: "age", value: 4 }] }));
});
test("client keeps explicit dataset, filtering and REST pagination", async t => {
  let url = "";
  t.mock.method(globalThis, "fetch", async (input: string) => { url = input; return Response.json({ dataset_version_id: "dataset", snapshot_date: "2026-08-26", page: 2, page_size: 12, total: 0, items: [] }); });
  const page = await api.orders("dataset", { po_number: "PO & 1", page: "2", page_size: "12" });
  assert.equal(new URL(url, "http://local").searchParams.get("po_number"), "PO & 1");
  assert.equal(page.page, 2); assert.equal(page.items.length, 0);
});
test("Copilot success, clarification, failure and business unresolved remain separate", async t => {
  for (const status of ["COMPLETED", "NEEDS_CLARIFICATION", "FAILED", "UNRESOLVED", "NOT_APPLICABLE", "NOT_FOUND"]) {
    const mock = t.mock.method(globalThis, "fetch", async (_url: string, options: RequestInit) => {
      assert.equal(JSON.parse(String(options.body)).po_line_schedule_id, "schedule");
      return Response.json({ ...result, status });
    });
    assert.equal((await api.query({ dataset_version_id: "dataset", po_line_schedule_id: "schedule" }, "为什么？")).status, status);
    mock.mock.restore();
  }
});
test("cross-scope results and raw errors are never rendered", async t => {
  const mock = t.mock.method(globalThis, "fetch", async () => Response.json({ ...result, resolved_identity: { dataset_version_id: "other", snapshot_date: "2026-08-26", po_line_schedule_id: "schedule" } }));
  await assert.rejects(api.query({ dataset_version_id: "dataset" }, "分析"), /INVALID_RESPONSE/);
  mock.mock.restore();
  t.mock.method(globalThis, "fetch", async () => new Response("private raw exception", { status: 500 }));
  await assert.rejects(api.datasets(), /UPSTREAM_UNAVAILABLE/);
  assert.ok(!errorText(new Error("private raw exception")).includes("private"));
});
