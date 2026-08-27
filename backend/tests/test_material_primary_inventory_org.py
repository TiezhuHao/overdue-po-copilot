from uuid import uuid4

import pytest
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from tests.db_helpers import insert_dataset, insert_inventory_organization, insert_material


pytestmark = pytest.mark.integration


def test_material_requires_primary_inventory_organization(
    database_connection: Connection,
) -> None:
    dataset_id = uuid4()
    insert_dataset(database_connection, dataset_id, "material-org-required")
    with pytest.raises(IntegrityError):
        insert_material(database_connection, dataset_id, uuid4(), None, "MAT-NULL-ORG")


def test_material_accepts_same_dataset_primary_inventory_organization(
    database_connection: Connection,
) -> None:
    dataset_id = uuid4()
    organization_id = uuid4()
    insert_dataset(database_connection, dataset_id, "material-org-valid")
    insert_inventory_organization(database_connection, dataset_id, organization_id, "ORG-VALID")
    insert_material(database_connection, dataset_id, uuid4(), organization_id, "MAT-VALID")
