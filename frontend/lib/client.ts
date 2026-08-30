import { datasets, orderPage, copilotResult, type QueryContext } from "./contracts.ts";

export class ApiError extends Error {
  readonly code: string;
  constructor(code: string) { super(code); this.code = code; }
}
async function request(path: string, options: RequestInit = {}) {
  try {
    const response = await fetch(`/api/backend/${path}`, { ...options, cache: "no-store", signal: options.signal ?? AbortSignal.timeout(180000) });
    if (!response.ok) throw new ApiError(response.status === 404 ? "NOT_FOUND" : response.status === 422 ? "INVALID_REQUEST" : "UPSTREAM_UNAVAILABLE");
    return await response.json() as unknown;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError("UPSTREAM_UNAVAILABLE");
  }
}
export const api = {
  datasets: async (signal?: AbortSignal) => datasets(await request("datasets", { signal })),
  orders: async (dataset: string, filters: Record<string, string> = {}, signal?: AbortSignal) => {
    const params = new URLSearchParams({ ...filters, dataset_version_id: dataset });
    const page = orderPage(await request(`orders?${params}`, { signal }));
    if (page.dataset_version_id !== dataset) throw new ApiError("INVALID_RESPONSE");
    return page;
  },
  query: async (context: QueryContext, user_query: string, signal?: AbortSignal) => {
    const result = copilotResult(await request("copilot", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...context, user_query }), signal }));
    if (result.resolved_identity && (result.resolved_identity.dataset_version_id !== context.dataset_version_id ||
      (context.po_line_schedule_id && result.resolved_identity.po_line_schedule_id !== context.po_line_schedule_id) ||
      (context.snapshot_date && result.resolved_identity.snapshot_date !== context.snapshot_date))) throw new ApiError("INVALID_RESPONSE");
    return result;
  }
};
