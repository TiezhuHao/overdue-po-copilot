from uuid import uuid4

import pytest
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from tests.db_helpers import insert_dataset, insert_inventory_organization, insert_material


pytestmark = pytest.mark.integration


def test_cross_dataset_material_organization_fk_is_rejected(
    database_connection: Connection,
) -> None:
    dataset_a = uuid4()
    dataset_b = uuid4()
    organization_b = uuid4()
    insert_dataset(database_connection, dataset_a, "cross-a")
    insert_dataset(database_connection, dataset_b, "cross-b")
    insert_inventory_organization(database_connection, dataset_b, organization_b, "ORG-B")

    with pytest.raises(IntegrityError):
        insert_material(database_connection, dataset_a, uuid4(), organization_b, "MAT-A")
