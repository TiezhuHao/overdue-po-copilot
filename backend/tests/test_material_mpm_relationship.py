from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from tests.db_helpers import (
    insert_dataset,
    insert_employee,
    insert_inventory_organization,
    insert_material,
)


pytestmark = pytest.mark.integration


def test_material_mpm_active_period_cannot_overlap(database_connection: Connection) -> None:
    dataset_id = uuid4()
    organization_id = uuid4()
    material_id = uuid4()
    employee_a = uuid4()
    employee_b = uuid4()
    insert_dataset(database_connection, dataset_id, "mpm-overlap")
    insert_inventory_organization(database_connection, dataset_id, organization_id, "ORG-MPM")
    insert_material(database_connection, dataset_id, material_id, organization_id, "MAT-MPM")
    insert_employee(database_connection, dataset_id, employee_a, organization_id, "MPM-A")
    insert_employee(database_connection, dataset_id, employee_b, organization_id, "MPM-B")

    statement = text(
        """
        INSERT INTO platform.material_mpm_assignments (
            dataset_version_id, material_mpm_assignment_id, material_id,
            employee_id, effective_from, effective_to
        ) VALUES (
            :dataset_id, :assignment_id, :material_id,
            :employee_id, :effective_from, :effective_to
        )
        """
    )
    database_connection.execute(
        statement,
        {
            "dataset_id": dataset_id,
            "assignment_id": uuid4(),
            "material_id": material_id,
            "employee_id": employee_a,
            "effective_from": date(2026, 1, 1),
            "effective_to": date(2026, 7, 1),
        },
    )
    with pytest.raises(IntegrityError):
        database_connection.execute(
            statement,
            {
                "dataset_id": dataset_id,
                "assignment_id": uuid4(),
                "material_id": material_id,
                "employee_id": employee_b,
                "effective_from": date(2026, 6, 1),
                "effective_to": None,
            },
        )
