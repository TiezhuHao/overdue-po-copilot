import snapshot from "../data/portfolio-demo.json" with { type: "json" };
import { copilotResult, datasets, orderPage, type QueryContext } from "./contracts.ts";

const datasetList = datasets(snapshot.datasets);
const sourcePage = orderPage(snapshot.orders);
const results = snapshot.copilot_results as Record<string, unknown>;

function aborted(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException("The operation was aborted", "AbortError");
}

function contains(value: string | null, query: string | undefined) {
  return !query || (value ?? "").toLocaleLowerCase().includes(query.toLocaleLowerCase());
}

export const portfolioApi = {
  datasets: async (signal?: AbortSignal) => {
    aborted(signal);
    return datasetList;
  },
  orders: async (dataset: string, filters: Record<string, string> = {}, signal?: AbortSignal) => {
    aborted(signal);
    if (dataset !== sourcePage.dataset_version_id) throw new Error("NOT_FOUND");
    const filtered = sourcePage.items.filter(order =>
      contains(order.po_number, filters.po_number) &&
      contains(order.material_code, filters.material_code) &&
      contains(order.supplier_name, filters.supplier) &&
      contains(order.reference_project_name, filters.project) &&
      (!filters.po_line_schedule_id || order.po_line_schedule_id === filters.po_line_schedule_id)
    );
    const page = Math.max(1, Number.parseInt(filters.page ?? "1", 10) || 1);
    const pageSize = Math.max(1, Number.parseInt(filters.page_size ?? "12", 10) || 12);
    const start = (page - 1) * pageSize;
    return { ...sourcePage, page, page_size: pageSize, total: filtered.length, items: filtered.slice(start, start + pageSize) };
  },
  query: async (context: QueryContext, _userQuery: string, signal?: AbortSignal) => {
    aborted(signal);
    const schedule = context.po_line_schedule_id;
    if (!schedule || context.dataset_version_id !== sourcePage.dataset_version_id ||
        (context.snapshot_date && context.snapshot_date !== sourcePage.snapshot_date) || !results[schedule]) {
      throw new Error("NOT_FOUND");
    }
    return copilotResult(results[schedule]);
  },
};

export const portfolioProvenance = snapshot.provenance;
