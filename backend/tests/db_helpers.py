from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Connection, text


def insert_dataset(connection: Connection, dataset_id: UUID, suffix: str) -> None:
    connection.execute(
        text(
            """
            INSERT INTO platform.dataset_versions (
                dataset_version_id, version_name, random_seed, snapshot_date,
                generator_version, schema_version, generation_config,
                generation_signature, status
            ) VALUES (
                :dataset_id, :version_name, 1, :snapshot_date,
                'phase1-no-generator', 'phase1', CAST('{}' AS jsonb),
                :signature, 'GENERATING'
            )
            """
        ),
        {
            "dataset_id": dataset_id,
            "version_name": f"test-{suffix}",
            "snapshot_date": date(2026, 8, 26),
            "signature": f"signature-{suffix}",
        },
    )


def insert_inventory_organization(
    connection: Connection,
    dataset_id: UUID,
    organization_id: UUID,
    code: str,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO platform.organizations (
                dataset_version_id, organization_id, organization_code,
                organization_name, organization_type,
                inventory_organization_type, effective_from
            ) VALUES (
                :dataset_id, :organization_id, :code, :name,
                'INVENTORY_ORG', 'MASS_PRODUCTION', :effective_from
            )
            """
        ),
        {
            "dataset_id": dataset_id,
            "organization_id": organization_id,
            "code": code,
            "name": f"Organization {code}",
            "effective_from": date(2020, 1, 1),
        },
    )


def insert_material(
    connection: Connection,
    dataset_id: UUID,
    material_id: UUID,
    organization_id: UUID | None,
    code: str,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO platform.materials (
                dataset_version_id, material_id, material_code,
                material_lt_days, manufacturer_lt_days,
                minimum_pack_qty, minimum_order_qty,
                non_cancelable_non_returnable_flag,
                primary_inventory_organization_id
            ) VALUES (
                :dataset_id, :material_id, :code, 30, 45,
                :minimum_pack_qty, :minimum_order_qty, false,
                :organization_id
            )
            """
        ),
        {
            "dataset_id": dataset_id,
            "material_id": material_id,
            "code": code,
            "minimum_pack_qty": Decimal("1.0000"),
            "minimum_order_qty": Decimal("1.0000"),
            "organization_id": organization_id,
        },
    )


def insert_employee(
    connection: Connection,
    dataset_id: UUID,
    employee_id: UUID,
    organization_id: UUID,
    code: str,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO platform.employees (
                dataset_version_id, employee_id, employee_code,
                account_name, employee_name, organization_id, is_active
            ) VALUES (
                :dataset_id, :employee_id, :code, :account_name,
                :employee_name, :organization_id, true
            )
            """
        ),
        {
            "dataset_id": dataset_id,
            "employee_id": employee_id,
            "code": code,
            "account_name": code.lower(),
            "employee_name": f"Employee {code}",
            "organization_id": organization_id,
        },
    )
