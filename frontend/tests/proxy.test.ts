import { test } from "node:test";
import assert from "node:assert/strict";
import { proxy } from "../lib/proxy.ts";
test("proxy denies arbitrary paths, unsupported filters and implicit dataset", async () => {
  assert.equal((await proxy(new Request("http://local/api/backend/secrets"), "secrets")).status, 404);
  assert.equal((await proxy(new Request("http://local/api/backend/orders"), "orders")).status, 422);
  assert.equal((await proxy(new Request("http://local/api/backend/orders?dataset_version_id=d&url=evil"), "orders")).status, 422);
});
test("cross-origin and policy injection blocked before upstream call", async () => {
  const body = JSON.stringify({ user_query: "分析", diagnosis_policy: {} });
  assert.equal((await proxy(new Request("http://local/api/backend/copilot", { method: "POST", body, headers: { origin: "http://elsewhere" } }), "copilot")).status, 403);
  assert.equal((await proxy(new Request("http://local/api/backend/copilot", { method: "POST", body, headers: { origin: "http://local" } }), "copilot")).status, 422);
});
test("proxy does not forward browser credentials and sanitizes upstream errors", async t => {
  t.mock.method(globalThis, "fetch", async (_target: URL, options: RequestInit) => {
    assert.deepEqual(options.headers, {}); assert.equal(options.redirect, "error"); assert.equal(options.cache, "no-store");
    return new Response("private upstream stack", { status: 500 });
  });
  const response = await proxy(new Request("http://local/api/backend/datasets", { headers: { cookie: "session=private", authorization: "private" } }), "datasets");
  assert.equal(response.status, 502); assert.ok(!(await response.text()).includes("private"));
});
