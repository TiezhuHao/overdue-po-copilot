from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from app.generators.master_data.world import MasterWorld
from app.generators.procurement.world import ProcurementWorld


class ProcurementWorldValidationError(ValueError):
    pass


def _active(row: Any, as_of: Any) -> bool:
    return row.effective_from <= as_of and (row.effective_to is None or as_of < row.effective_to)


class ProcurementWorldValidator:
    def validate(
        self,
        world: ProcurementWorld,
        master: MasterWorld,
        dataset_version_id: Any,
    ) -> None:
        errors: list[str] = []
        for name in world.COLLECTION_NAMES:
            if any(row.dataset_version_id != dataset_version_id for row in getattr(world, name)):
                errors.append(f"{name} contains a cross-dataset row")

        organizations = {row.organization_id: row for row in master.organizations}
        employees = {row.employee_id for row in master.employees}
        suppliers = {row.supplier_id for row in master.suppliers}
        materials = {row.material_id: row for row in master.materials}
        projects = {row.project_id for row in master.projects}
        headers = {row.po_header_id: row for row in world.po_headers}
        lines = {row.po_line_id: row for row in world.po_lines}

        if len(headers) != len(world.po_headers) or len(lines) != len(world.po_lines):
            errors.append("duplicate procurement identifiers")
        if len({row.po_number for row in world.po_headers}) != len(world.po_headers):
            errors.append("duplicate PO number")

        supplier_relations = master.material_supplier_assignments
        project_relations = master.material_projects
        buyer_relations = master.material_responsibility_assignments

        for header in world.po_headers:
            business_entity = organizations.get(header.business_entity_id)
            inventory_org = organizations.get(header.inventory_organization_id)
            if business_entity is None or business_entity.organization_type != "BUSINESS_ENTITY":
                errors.append("PO header business entity is invalid")
            if inventory_org is None or inventory_org.organization_type != "INVENTORY_ORG":
                errors.append("PO header inventory organization is invalid")
            if header.supplier_id not in suppliers or header.order_buyer_employee_id not in employees:
                errors.append("PO header master reference is invalid")

        schedules_by_line: dict[Any, list[Any]] = defaultdict(list)
        for schedule in world.po_line_schedules:
            schedules_by_line[schedule.po_line_id].append(schedule)
            if schedule.po_line_id not in lines:
                errors.append("schedule parent line is missing")
            if schedule.schedule_qty < 0 or schedule.schedule_received_qty < 0:
                errors.append("schedule quantity is negative")
            if schedule.schedule_received_qty > schedule.schedule_qty:
                errors.append("schedule received quantity exceeds schedule quantity")

        line_numbers: set[tuple[Any, int]] = set()
        shipment_numbers: set[tuple[Any, int]] = set()
        for schedule in world.po_line_schedules:
            key = (schedule.po_line_id, schedule.shipment_number)
            if key in shipment_numbers:
                errors.append("duplicate shipment number")
            shipment_numbers.add(key)

        for line in world.po_lines:
            header = headers.get(line.po_header_id)
            material = materials.get(line.material_id)
            if header is None or material is None:
                errors.append("PO line parent or material is missing")
                continue
            key = (line.po_header_id, line.po_line_number)
            if key in line_numbers:
                errors.append("duplicate PO line number")
            line_numbers.add(key)
            if line.po_reference_project_id not in projects:
                errors.append("PO reference project is missing")
            if material.primary_inventory_organization_id != header.inventory_organization_id:
                errors.append("PO line material organization differs from header")
            if line.material_lt_days_at_order != material.material_lt_days:
                errors.append("PO line LT differs from material master")
            if line.due_date != line.order_date + timedelta(days=line.material_lt_days_at_order):
                errors.append("PO line due date is inconsistent with order date and LT")
            valid_supplier = any(
                row.material_id == line.material_id
                and row.supplier_id == header.supplier_id
                and row.assignment_type == "PRIMARY"
                and _active(row, line.order_date)
                for row in supplier_relations
            )
            if not valid_supplier:
                errors.append("PO supplier is not the material active primary supplier")
            valid_project = any(
                row.material_id == line.material_id
                and row.project_id == line.po_reference_project_id
                and _active(row, line.order_date)
                for row in project_relations
            )
            if not valid_project:
                errors.append("PO reference project is not related to material")
            valid_buyer = any(
                row.material_id == line.material_id
                and row.employee_id == header.order_buyer_employee_id
                and row.responsibility_type == "BUYER"
                and _active(row, line.order_date)
                for row in buyer_relations
            )
            if not valid_buyer:
                errors.append("PO buyer is not the material active buyer")
            child_schedules = schedules_by_line[line.po_line_id]
            if not child_schedules:
                errors.append("PO line has no shipment schedule")
            if sum(row.schedule_qty for row in child_schedules) != line.ordered_qty:
                errors.append("PO line quantity differs from shipment total")
            if sum(row.schedule_received_qty for row in child_schedules) != line.received_qty:
                errors.append("PO line received quantity differs from shipment total")
            if line.received_qty < 0 or line.received_qty > line.ordered_qty:
                errors.append("PO line received quantity is invalid")

        forbidden = {
            "cause",
            "cause_type",
            "true_cause",
            "causal_project_id",
            "demand_change_type",
            "responsibility_type",
            "expected_action",
            "lifecycle_state",
        }
        columns = {
            column.key
            for record in world.all_records()
            for column in record.__table__.columns
        }
        if columns & forbidden:
            errors.append("procurement facts expose diagnostic answer fields")
        if errors:
            raise ProcurementWorldValidationError("; ".join(dict.fromkeys(errors)))
