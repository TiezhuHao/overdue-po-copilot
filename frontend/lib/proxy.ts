// Fixed, server-only destinations. Never forward credentials, cookies or arbitrary URLs.
const resources: Record<string, { env: string; fallback: string; path: string; method: string }> = {
  datasets: { env: "SYSTEM_A_API_BASE_URL", fallback: "http://127.0.0.1:8000/api/v1", path: "/datasets", method: "GET" },
  orders: { env: "SYSTEM_A_API_BASE_URL", fallback: "http://127.0.0.1:8000/api/v1", path: "/reports/overdue-pos", method: "GET" },
  copilot: { env: "SYSTEM_B_API_BASE_URL", fallback: "http://127.0.0.1:8100/api/v1", path: "/copilot/query", method: "POST" },
};
const allowed = new Set(["dataset_version_id", "po_line_schedule_id", "po_number", "material_code", "supplier", "project", "page", "page_size"]);
const fail = (status: number, code: string) => Response.json({ detail: { code } }, { status, headers: { "Cache-Control": "no-store" } });
export async function proxy(request: Request, resource: string): Promise<Response> {
  const config = resources[resource];
  if (!config || config.method !== request.method) return fail(404, "NOT_FOUND");
  const incoming = new URL(request.url);
  if (request.method === "POST" && request.headers.get("origin") !== incoming.origin) return fail(403, "ORIGIN_REJECTED");
  try {
    const target = new URL((process.env[config.env] || config.fallback).replace(/\/$/, "") + config.path);
    if (!["http:", "https:"].includes(target.protocol) || target.username || target.password) return fail(503, "CONFIGURATION_UNAVAILABLE");
    for (const [key, value] of incoming.searchParams) {
      if (!allowed.has(key) || value.length > 160) return fail(422, "INVALID_REQUEST");
      target.searchParams.set(key, value);
    }
    if (resource === "orders" && !target.searchParams.has("dataset_version_id")) return fail(422, "INVALID_REQUEST");
    let body: string | undefined;
    if (request.method === "POST") {
      body = await request.text();
      if (body.length > 8000) return fail(413, "INVALID_REQUEST");
      const value = JSON.parse(body);
      if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).some(key => !["user_query", "dataset_version_id", "snapshot_date", "po_line_schedule_id", "po_number"].includes(key))) return fail(422, "INVALID_REQUEST");
    }
    const result = await fetch(target, { method: config.method, body, headers: body ? { "Content-Type": "application/json" } : {}, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(resource === "copilot" ? 175000 : 20000) });
    if (!result.ok) return fail([404, 422].includes(result.status) ? result.status : 502, "UPSTREAM_UNAVAILABLE");
    return Response.json(await result.json(), { headers: { "Cache-Control": "no-store" } });
  } catch { return fail(502, "UPSTREAM_UNAVAILABLE"); }
}
