from uuid import uuid4

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from tests.db_helpers import insert_dataset, insert_inventory_organization, insert_material


pytestmark = pytest.mark.integration


def test_projects_may_share_name_but_not_code(database_connection: Connection) -> None:
    dataset_id = uuid4()
    insert_dataset(database_connection, dataset_id, "project-names")
    database_connection.execute(
        text(
            """
            INSERT INTO platform.projects (
                dataset_version_id, project_id, project_code, project_name
            ) VALUES
                (:dataset_id, :project_a, 'PROJECT-A', 'Alpha'),
                (:dataset_id, :project_b, 'PROJECT-B', 'Alpha')
            """
        ),
        {"dataset_id": dataset_id, "project_a": uuid4(), "project_b": uuid4()},
    )


def test_material_code_is_unique_within_dataset(database_connection: Connection) -> None:
    dataset_id = uuid4()
    organization_id = uuid4()
    insert_dataset(database_connection, dataset_id, "material-code-unique")
    insert_inventory_organization(database_connection, dataset_id, organization_id, "ORG-CODE")
    insert_material(database_connection, dataset_id, uuid4(), organization_id, "MAT-SAME")
    with pytest.raises(IntegrityError):
        insert_material(database_connection, dataset_id, uuid4(), organization_id, "MAT-SAME")


def test_material_code_may_repeat_across_datasets(database_connection: Connection) -> None:
    dataset_a = uuid4()
    dataset_b = uuid4()
    organization_a = uuid4()
    organization_b = uuid4()
    insert_dataset(database_connection, dataset_a, "material-repeat-a")
    insert_dataset(database_connection, dataset_b, "material-repeat-b")
    insert_inventory_organization(database_connection, dataset_a, organization_a, "ORG-A")
    insert_inventory_organization(database_connection, dataset_b, organization_b, "ORG-B")
    insert_material(database_connection, dataset_a, uuid4(), organization_a, "MAT-REPEAT")
    insert_material(database_connection, dataset_b, uuid4(), organization_b, "MAT-REPEAT")
