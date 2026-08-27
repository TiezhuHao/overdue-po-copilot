from random import Random

import pytest

from app.core.ids import deterministic_uuid
from app.generators.config import GenerationConfig
from app.generators.context import GenerationContext
from app.generators.master_data.generator import MasterDataGenerator
from app.generators.signature import generation_signature
from app.generators.validation import MasterDataValidator, MasterWorldValidationError


def _world(config: GenerationConfig):
    signature = generation_signature(config)
    dataset_id = deterministic_uuid(signature, "dataset_version", signature)
    context = GenerationContext(dataset_id, signature, config, Random(config.random_seed))
    return MasterDataGenerator().generate(context), dataset_id, signature


def test_master_world_shape_relationships_and_validation() -> None:
    config = GenerationConfig.small_test()
    world, dataset_id, _ = _world(config)
    assert len(world.organizations) == config.organization_count
    assert len(world.employees) == config.employee_count
    assert len(world.materials) == config.material_count
    assert len(world.projects) == config.project_count
    assert len(world.customers) == config.customer_count
    assert len(world.suppliers) == config.supplier_count
    assert {row.inventory_organization_type for row in world.organizations} >= {
        "TRIAL",
        "MASS_PRODUCTION",
        None,
    }
    assert all(row.manager_employee_id != row.employee_id for row in world.employees)
    assert all(row.director_employee_id != row.employee_id for row in world.employees)
    assert all(row.material_lt_days >= 0 for row in world.materials)
    assert len({row.project_name for row in world.projects}) < len(world.projects)
    assert {row.material_id for row in world.material_projects} == {
        row.material_id for row in world.materials
    }
    assert {row.project_id for row in world.material_projects} == {
        row.project_id for row in world.projects
    }
    MasterDataValidator().validate(world, dataset_id, config.snapshot_date)


def test_same_input_is_byte_stable_and_different_seed_changes_content() -> None:
    config = GenerationConfig.small_test()
    first, _, signature = _world(config)
    second, _, _ = _world(config)
    changed, _, changed_signature = _world(GenerationConfig.small_test(random_seed=124))
    assert first.master_content_hash(signature) == second.master_content_hash(signature)
    assert first.master_content_hash(signature) != changed.master_content_hash(changed_signature)


def test_validator_rejects_missing_active_mpm() -> None:
    config = GenerationConfig.small_test()
    world, dataset_id, _ = _world(config)
    material_id = world.materials[0].material_id
    world.material_mpm_assignments = [
        row for row in world.material_mpm_assignments if row.material_id != material_id
    ]
    with pytest.raises(MasterWorldValidationError, match="active MPM"):
        MasterDataValidator().validate(world, dataset_id, config.snapshot_date)
