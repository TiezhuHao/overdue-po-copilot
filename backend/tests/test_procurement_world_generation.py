from random import Random

import pytest

from app.core.ids import deterministic_uuid
from app.generators.config import GenerationConfig
from app.generators.context import GenerationContext
from app.generators.master_data.generator import MasterDataGenerator
from app.generators.procurement.config import ProcurementGenerationConfig
from app.generators.procurement.generator import ProcurementGenerator
from app.generators.procurement.signature import procurement_generation_signature
from app.generators.procurement.validation import (
    ProcurementWorldValidationError,
    ProcurementWorldValidator,
)
from app.generators.signature import generation_signature


def _master(seed: int = 123):
    config = GenerationConfig.small_test(random_seed=seed)
    signature = generation_signature(config)
    dataset_id = deterministic_uuid(signature, "dataset_version", signature)
    context = GenerationContext(dataset_id, signature, config, Random(config.random_seed))
    return MasterDataGenerator().generate(context), dataset_id, signature, config.snapshot_date


def _procurement(master_seed: int = 123, procurement_seed: int = 321):
    master, dataset_id, dataset_signature, snapshot = _master(master_seed)
    config = ProcurementGenerationConfig.small_test(random_seed=procurement_seed)
    signature = procurement_generation_signature(dataset_signature, config)
    world = ProcurementGenerator().generate(dataset_id, snapshot, signature, config, master)
    return world, master, dataset_id, signature, snapshot, config


def test_procurement_counts_relationships_lt_and_default_single_shipment() -> None:
    world, master, dataset_id, _, _, config = _procurement()
    assert len(world.po_headers) == config.po_header_count
    assert config.po_header_count <= len(world.po_lines) <= config.po_header_count * 2
    assert len(world.po_line_schedules) == len(world.po_lines)
    assert {row.shipment_number for row in world.po_line_schedules} == {1}
    organizations = {row.organization_id: row for row in master.organizations}
    assert {
        organizations[row.inventory_organization_id].inventory_organization_type
        for row in world.po_headers
    } == {"TRIAL", "MASS_PRODUCTION"}
    ProcurementWorldValidator().validate(world, master, dataset_id)


def test_same_seed_is_deterministic_and_different_seed_changes_world() -> None:
    first, _, _, signature, _, _ = _procurement()
    second, _, _, _, _, _ = _procurement()
    changed, _, _, changed_signature, _, _ = _procurement(procurement_seed=322)
    assert first.procurement_content_hash(signature) == second.procurement_content_hash(signature)
    assert [row.po_header_id for row in first.po_headers] == [row.po_header_id for row in second.po_headers]
    assert first.procurement_content_hash(signature) != changed.procurement_content_hash(changed_signature)


def test_master_dataset_changes_procurement_ids() -> None:
    first, _, _, _, _, _ = _procurement(master_seed=123)
    second, _, _, _, _, _ = _procurement(master_seed=124)
    assert first.po_headers[0].po_number == second.po_headers[0].po_number
    assert first.po_headers[0].po_header_id != second.po_headers[0].po_header_id


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("supplier", "active primary supplier"),
        ("project", "not related to material"),
        ("buyer", "active buyer"),
    ],
)
def test_validator_rejects_unrelated_master_references(mutation: str, message: str) -> None:
    world, master, dataset_id, _, _, _ = _procurement()
    line = world.po_lines[0]
    header = next(row for row in world.po_headers if row.po_header_id == line.po_header_id)
    if mutation == "supplier":
        header.supplier_id = next(
            row.supplier_id for row in master.suppliers if row.supplier_id != header.supplier_id
        )
    elif mutation == "project":
        related = {
            row.project_id for row in master.material_projects if row.material_id == line.material_id
        }
        line.po_reference_project_id = next(
            row.project_id for row in master.projects if row.project_id not in related
        )
    else:
        header.order_buyer_employee_id = next(
            row.employee_id
            for row in master.employees
            if row.employee_id != header.order_buyer_employee_id
        )
    with pytest.raises(ProcurementWorldValidationError, match=message):
        ProcurementWorldValidator().validate(world, master, dataset_id)


def test_validator_rejects_line_schedule_totals_and_wrong_organization() -> None:
    world, master, dataset_id, _, _, _ = _procurement()
    world.po_line_schedules[0].schedule_qty += 1
    with pytest.raises(ProcurementWorldValidationError, match="shipment total"):
        ProcurementWorldValidator().validate(world, master, dataset_id)


def test_validator_rejects_header_type_and_material_organization_mismatch() -> None:
    world, master, dataset_id, _, _, _ = _procurement()
    header = world.po_headers[0]
    header.inventory_organization_id = next(
        row.organization_id
        for row in master.organizations
        if row.organization_type == "BUSINESS_UNIT"
    )
    with pytest.raises(ProcurementWorldValidationError, match="inventory organization"):
        ProcurementWorldValidator().validate(world, master, dataset_id)

    world, master, dataset_id, _, _, _ = _procurement()
    line = world.po_lines[0]
    header = next(row for row in world.po_headers if row.po_header_id == line.po_header_id)
    header.inventory_organization_id = next(
        row.organization_id
        for row in master.organizations
        if row.organization_type == "INVENTORY_ORG"
        and row.organization_id != header.inventory_organization_id
    )
    with pytest.raises(ProcurementWorldValidationError, match="differs from header"):
        ProcurementWorldValidator().validate(world, master, dataset_id)
