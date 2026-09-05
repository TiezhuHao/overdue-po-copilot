import { test } from "node:test";
import assert from "node:assert/strict";
import { portfolioApi, portfolioProvenance } from "../lib/portfolio-demo.ts";

test("portfolio snapshot is the accepted release dataset and never claims model output", async () => {
  assert.equal(portfolioProvenance.dataset_version_name, "demo-master-v1");
  assert.equal(portfolioProvenance.snapshot_date, "2026-08-26");
  assert.equal(portfolioProvenance.generation_signature, "7ccb43f1db06ecc1970e9bde2a0cda0b6d014b05d02d1fd9e67660e1d5769e9b");
  assert.equal(portfolioProvenance.business_content_hash, "f91717e3af70a518caf31673fd5f733f1e12b2dfb9598b1e7c0cec20c36ac199");
  assert.equal(portfolioProvenance.openai_used, false);
  const dataset = (await portfolioApi.datasets())[0];
  const orders = await portfolioApi.orders(dataset.dataset_version_id);
  assert.equal(orders.items.length, 12);
  for (const order of orders.items) {
    assert.ok(order.po_line_schedule_id);
    const result = await portfolioApi.query({ dataset_version_id: dataset.dataset_version_id, snapshot_date: dataset.snapshot_date, po_line_schedule_id: order.po_line_schedule_id! }, "为什么？");
    assert.equal(result.answer_source, "FALLBACK");
    assert.equal(result.resolved_identity?.po_line_schedule_id, order.po_line_schedule_id);
    assert.equal(result.resolved_identity?.dataset_version_id, dataset.dataset_version_id);
  }
});

test("portfolio list keeps deterministic client-side filtering and exact lookup", async () => {
  const dataset = (await portfolioApi.datasets())[0];
  const filtered = await portfolioApi.orders(dataset.dataset_version_id, { po_number: "PO-000015" });
  assert.equal(filtered.total, 1);
  assert.equal(filtered.items[0].po_line_number, 3);
  await assert.rejects(portfolioApi.orders("wrong-dataset"), /NOT_FOUND/);
});
