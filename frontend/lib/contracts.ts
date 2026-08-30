// Public API projections only. No procurement calculations or rule evaluation.
export type Dataset = { dataset_version_id: string; dataset_version_name: string; snapshot_date: string; status: string };
export type Order = {
  po_line_schedule_id: string | null; material_id: string | null; supplier_id: string | null;
  po_reference_project_id: string | null; po_number: string; po_line_number: number; shipment_number: number;
  material_code: string; material_description: string | null; supplier_name: string;
  inventory_organization_code: string; inventory_organization_type: string;
  reference_project_name: string | null; order_date: string; material_lt_days: number;
  overdue_open_qty: string | null; overdue_days: number; po_status: string;
};
export type OrderPage = { dataset_version_id: string; snapshot_date: string; page: number; page_size: number; total: number; items: Order[] };
export type Metric = { name: string; value: string | null; unit: string; availability: string };
export type Reference = { reference_id: string; source: string; label: string; snapshot_date: string; version_id: string | null; version_date: string | null; rule_version: string | null };
export type CopilotResult = {
  request_id: string; status: string; answer: string; answer_source: string;
  resolved_identity: { dataset_version_id: string; snapshot_date: string; po_line_schedule_id: string } | null;
  key_metrics: Metric[];
  diagnosis: { status: string; primary_reason: string | null; primary_rule_id: string | null; primary_rule_version: string | null; supporting_signals: string[] } | null;
  decision: { status: string; rule_id: string | null; rule_version: string | null; owner_role: string | null; actions: { action_code: string; owner_role: string | null; required: boolean }[] } | null;
  evidence_references: Reference[]; limitations: string[]; candidate_schedule_ids: string[];
  execution_reference: string | null;
};
export type QueryContext = { dataset_version_id: string; snapshot_date?: string; po_line_schedule_id?: string; po_number?: string };

export function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("INVALID_RESPONSE");
  return value as Record<string, unknown>;
}
function text(value: unknown): string { if (typeof value !== "string") throw new Error("INVALID_RESPONSE"); return value; }
function nullable(value: unknown): string | null { return value == null ? null : text(value); }
function integer(value: unknown): number { if (typeof value !== "number" || !Number.isSafeInteger(value)) throw new Error("INVALID_RESPONSE"); return value; }
function array(value: unknown): unknown[] { if (!Array.isArray(value)) throw new Error("INVALID_RESPONSE"); return value; }
export function datasets(value: unknown): Dataset[] {
  return array(record(value).items).map(value => { const d = record(value); return {
    dataset_version_id: text(d.dataset_version_id), dataset_version_name: text(d.dataset_version_name), snapshot_date: text(d.snapshot_date), status: text(d.status)
  }; });
}
export function orderPage(value: unknown): OrderPage {
  const p = record(value);
  const result = { dataset_version_id: text(p.dataset_version_id), snapshot_date: text(p.snapshot_date), page: integer(p.page), page_size: integer(p.page_size), total: integer(p.total), items: array(p.items).map(value => {
    const r = record(value);
    return { po_line_schedule_id: nullable(r.po_line_schedule_id), material_id: nullable(r.material_id), supplier_id: nullable(r.supplier_id), po_reference_project_id: nullable(r.po_reference_project_id),
      po_number: text(r.po_number), po_line_number: integer(r.po_line_number), shipment_number: integer(r.shipment_number), material_code: text(r.material_code), material_description: nullable(r.material_description), supplier_name: text(r.supplier_name),
      inventory_organization_code: text(r.inventory_organization_code), inventory_organization_type: text(r.inventory_organization_type), reference_project_name: nullable(r.reference_project_name), order_date: text(r.order_date), material_lt_days: integer(r.material_lt_days),
      overdue_open_qty: nullable(r.overdue_open_qty), overdue_days: integer(r.overdue_days), po_status: text(r.po_status) };
  }) };
  if (result.page < 1 || result.page_size < 1 || result.total < 0 || result.items.length > result.page_size) throw new Error("INVALID_RESPONSE");
  return result;
}
export function copilotResult(value: unknown): CopilotResult {
  const r = record(value);
  text(r.request_id); text(r.answer);
  if (!["COMPLETED", "NOT_FOUND", "NEEDS_CLARIFICATION", "UNRESOLVED", "NOT_APPLICABLE", "FAILED"].includes(text(r.status))) throw new Error("INVALID_RESPONSE");
  if (!["MODEL", "FALLBACK", "CLARIFICATION"].includes(text(r.answer_source))) throw new Error("INVALID_RESPONSE");
  for (const value of array(r.key_metrics)) { const m = record(value); text(m.name); nullable(m.value); text(m.unit); text(m.availability); }
  for (const value of array(r.evidence_references)) { const ref = record(value); text(ref.reference_id); text(ref.label); text(ref.source); text(ref.snapshot_date); }
  array(r.limitations).forEach(text); array(r.candidate_schedule_ids).forEach(text);
  if (r.diagnosis != null) { const d = record(r.diagnosis); text(d.status); nullable(d.primary_reason); array(d.supporting_signals).forEach(text); }
  if (r.decision != null) { const d = record(r.decision); text(d.status); nullable(d.owner_role); for (const value of array(d.actions)) { const a = record(value); text(a.action_code); nullable(a.owner_role); if (typeof a.required !== "boolean") throw new Error("INVALID_RESPONSE"); } }
  if (r.resolved_identity != null) { const identity = record(r.resolved_identity); text(identity.dataset_version_id); text(identity.snapshot_date); text(identity.po_line_schedule_id); }
  return r as unknown as CopilotResult;
}
