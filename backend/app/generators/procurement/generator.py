from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from random import Random
from typing import Any
from uuid import UUID

from app.core.ids import deterministic_uuid
from app.generators.master_data.world import MasterWorld
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.procurement.world import ProcurementWorld
from app.models.platform import PoHeader, PoLine, PoLineSchedule


def _active(row: Any, as_of: Any) -> bool:
    return row.effective_from <= as_of and (row.effective_to is None or as_of < row.effective_to)


class ProcurementGenerator:
    def generate(
        self,
        dataset_version_id: UUID,
        snapshot_date: Any,
        procurement_signature: str,
        config: ProcurementGenerationConfig,
        master: MasterWorld,
    ) -> ProcurementWorld:
        rng = Random(config.random_seed)
        organizations = {row.organization_id: row for row in master.organizations}
        materials = {row.material_id: row for row in master.materials}

        primary_supplier: dict[UUID, UUID] = {
            row.material_id: row.supplier_id
            for row in master.material_supplier_assignments
            if row.assignment_type == "PRIMARY" and _active(row, snapshot_date)
        }
        buyer: dict[UUID, UUID] = {
            row.material_id: row.employee_id
            for row in master.material_responsibility_assignments
            if row.responsibility_type == "BUYER" and _active(row, snapshot_date)
        }
        projects: dict[UUID, list[UUID]] = defaultdict(list)
        for row in master.material_projects:
            if _active(row, snapshot_date):
                projects[row.material_id].append(row.project_id)
        for values in projects.values():
            values.sort(key=str)

        groups: dict[tuple[UUID, UUID, UUID], list[Any]] = defaultdict(list)
        for material in master.materials:
            key = (
                material.primary_inventory_organization_id,
                primary_supplier[material.material_id],
                buyer[material.material_id],
            )
            groups[key].append(material)
        trial_groups = [
            key for key in groups if organizations[key[0]].inventory_organization_type == "TRIAL"
        ]
        mass_groups = [
            key for key in groups if organizations[key[0]].inventory_organization_type == "MASS_PRODUCTION"
        ]
        trial_groups.sort(key=lambda value: tuple(map(str, value)))
        mass_groups.sort(key=lambda value: tuple(map(str, value)))

        parent_by_id = {row.organization_id: row.parent_organization_id for row in master.organizations}
        business_entities = {
            row.organization_id for row in master.organizations if row.organization_type == "BUSINESS_ENTITY"
        }

        def business_entity_for(organization_id: UUID) -> UUID:
            current: UUID | None = organization_id
            while current is not None:
                if current in business_entities:
                    return current
                current = parent_by_id[current]
            raise ValueError("inventory organization has no business entity ancestor")

        headers: list[PoHeader] = []
        lines: list[PoLine] = []
        schedules: list[PoLineSchedule] = []
        trial_target = max(1, min(config.po_header_count - 1, round(config.po_header_count * config.trial_po_ratio)))
        overdue_target = round(config.po_header_count * config.overdue_candidate_ratio)

        for header_index in range(1, config.po_header_count + 1):
            group_pool = trial_groups if header_index <= trial_target else mass_groups
            group_key = group_pool[rng.randrange(len(group_pool))]
            organization_id, supplier_id, buyer_id = group_key
            group_materials = sorted(groups[group_key], key=lambda row: row.material_code)
            po_number = f"PO-{header_index:06d}"
            header_id = deterministic_uuid(procurement_signature, "po_header", po_number)
            line_count = rng.randint(config.min_lines_per_po, config.max_lines_per_po)
            target_overdue = header_index <= overdue_target
            line_statuses: list[str] = []

            for line_number in range(1, line_count + 1):
                material = group_materials[rng.randrange(len(group_materials))]
                lt_days = material.material_lt_days
                if target_overdue:
                    extra_days = rng.randint(
                        1, int(config.generation_options.get("max_extra_overdue_days", 180))
                    )
                    order_date = snapshot_date - timedelta(days=lt_days + 240 + extra_days)
                else:
                    order_date = snapshot_date - timedelta(days=rng.randint(5, lt_days + 230))
                due_date = order_date + timedelta(days=lt_days)
                ordered_qty = Decimal(rng.randint(config.min_quantity, config.max_quantity))

                if rng.random() < config.open_po_ratio:
                    if ordered_qty > 1 and rng.random() < config.partial_receipt_ratio:
                        received_qty = Decimal(rng.randint(1, int(ordered_qty) - 1))
                        line_status = "PARTIALLY_RECEIVED"
                    else:
                        received_qty = Decimal("0")
                        line_status = "OPEN"
                else:
                    received_qty = ordered_qty
                    line_status = "CLOSED"
                line_statuses.append(line_status)

                project_ids = projects[material.material_id]
                project_id = project_ids[rng.randrange(len(project_ids))]
                line_key = f"{po_number}:{line_number}"
                line_id = deterministic_uuid(procurement_signature, "po_line", line_key)
                completion_at = (
                    datetime.combine(due_date, time(12), tzinfo=timezone.utc)
                    if line_status == "CLOSED"
                    else None
                )
                lines.append(
                    PoLine(
                        dataset_version_id=dataset_version_id,
                        po_line_id=line_id,
                        po_header_id=header_id,
                        po_line_number=line_number,
                        material_id=material.material_id,
                        po_reference_project_id=project_id,
                        ordered_qty=ordered_qty,
                        received_qty=received_qty,
                        order_date=order_date,
                        due_date=due_date,
                        material_lt_days_at_order=lt_days,
                        can_close=received_qty == ordered_qty,
                        completion_at=completion_at,
                        line_status=line_status,
                    )
                )
                schedules.append(
                    PoLineSchedule(
                        dataset_version_id=dataset_version_id,
                        po_line_schedule_id=deterministic_uuid(
                            procurement_signature, "po_line_schedule", f"{line_key}:1"
                        ),
                        po_line_id=line_id,
                        shipment_number=1,
                        schedule_qty=ordered_qty,
                        schedule_received_qty=received_qty,
                        due_date=due_date,
                        close_status="CLOSED" if received_qty == ordered_qty else "OPEN",
                    )
                )

            if all(status == "CLOSED" for status in line_statuses):
                po_status, close_status = "CLOSED", "CLOSED"
            elif any(status == "PARTIALLY_RECEIVED" for status in line_statuses) or any(
                status == "CLOSED" for status in line_statuses
            ):
                po_status, close_status = "PARTIALLY_RECEIVED", "OPEN"
            else:
                po_status, close_status = "OPEN", "OPEN"
            headers.append(
                PoHeader(
                    dataset_version_id=dataset_version_id,
                    po_header_id=header_id,
                    po_number=po_number,
                    business_entity_id=business_entity_for(organization_id),
                    inventory_organization_id=organization_id,
                    supplier_id=supplier_id,
                    order_buyer_employee_id=buyer_id,
                    po_status=po_status,
                    close_status=close_status,
                )
            )
        return ProcurementWorld(headers, lines, schedules)
