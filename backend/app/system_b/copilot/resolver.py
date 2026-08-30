"""Exact canonical identity resolution; never choose the most plausible row."""
import re
from app.system_b.adapters.system_a import SystemAAdapter
from app.system_b.adapters.errors import SystemAResponseValidationError
from app.system_b.copilot.models import CopilotRequest, IntentDraft, Resolution


class SelectorError(ValueError):
    pass


def selectors(request: CopilotRequest, parsed: IntentDraft):
    result = {}
    for field in ("po_number", "material_code"):
        extracted, supplied = getattr(parsed, field), getattr(request, field)
        if extracted is not None:
            # Reject truncated ASCII codes (PO-1 extracted from PO-10), without treating
            # adjacent Chinese question words as part of an identifier.
            pattern = r"(?<![A-Za-z0-9_.\-/])" + re.escape(extracted) + r"(?![A-Za-z0-9_.\-/])"
            if not extracted.strip() or len(extracted) > 120 or not re.search(pattern, request.user_query):
                raise SelectorError("UNGROUNDED_SELECTOR")
            if supplied is not None and supplied != extracted:
                raise SelectorError("CONFLICTING_SELECTOR")
        result[field] = supplied if supplied is not None else extracted
    return result


def resolve(adapter: SystemAAdapter, request: CopilotRequest, parsed: IntentDraft) -> Resolution:
    selected = selectors(request, parsed)
    if request.dataset_version_id is None:
        return Resolution(status="NEEDS_CLARIFICATION", clarification_code="MISSING_DATASET")
    if not request.po_line_schedule_id and not any(selected.values()):
        return Resolution(status="NEEDS_CLARIFICATION", clarification_code="MISSING_PO_OR_MATERIAL")
    dataset = adapter.get_dataset(request.dataset_version_id)
    if dataset.dataset_version_id != request.dataset_version_id:
        raise SystemAResponseValidationError("Dataset identity differs")
    if dataset.status != "READY":
        return Resolution(status="NEEDS_CLARIFICATION", clarification_code="DATASET_NOT_READY")
    if request.snapshot_date is not None and request.snapshot_date != dataset.snapshot_date:
        return Resolution(status="NEEDS_CLARIFICATION", clarification_code="SNAPSHOT_MISMATCH")
    matches = {}
    for page in adapter.iter_pages(adapter.purchase_orders, request.dataset_version_id,
                                   po_line_schedule_id=request.po_line_schedule_id, **selected):
        if page.dataset_version_id != request.dataset_version_id or page.snapshot_date != dataset.snapshot_date:
            raise SystemAResponseValidationError("Resolution page scope differs")
        for row in page.items:
            if row.dataset_version_id != dataset.dataset_version_id or row.snapshot_date != dataset.snapshot_date:
                raise SystemAResponseValidationError("Resolution row scope differs")
            # Source display filters may be broader than equality. Always verify exact values.
            expected = selected | {"po_line_schedule_id": request.po_line_schedule_id,
                                  "organization_id": request.organization_id,
                                  "po_line_number": request.po_line_number, "shipment_number": request.shipment_number}
            if any(value is not None and getattr(row, key) != value for key, value in expected.items()):
                continue
            if row.po_line_schedule_id is None:
                return Resolution(status="NEEDS_CLARIFICATION", clarification_code="MISSING_STABLE_ID")
            if row.po_line_schedule_id in matches:
                raise SystemAResponseValidationError("Duplicate schedule identity")
            matches[row.po_line_schedule_id] = row
            if len(matches) > 1:
                # Two proven matches are enough to refuse selection. No claim of exhaustive candidates.
                return Resolution(status="NEEDS_CLARIFICATION", clarification_code="AMBIGUOUS_PO",
                                  candidate_schedule_ids=tuple(sorted(matches, key=str)))
    if not matches:
        return Resolution(status="NOT_FOUND", clarification_code="PO_NOT_IN_REPORT")
    return Resolution(status="RESOLVED", snapshot_date=dataset.snapshot_date, po_line_schedule_id=next(iter(matches)))
