from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.models.platform.dataset import DatasetVersion


def test_dataset_model_contract() -> None:
    table = DatasetVersion.__table__
    assert table.schema == "platform"
    assert isinstance(table.c.generation_config.type, JSONB)
    assert table.c.dataset_version_id.default is None
    assert table.c.dataset_version_id.server_default is None
    assert {column.name for column in table.primary_key.columns} == {"dataset_version_id"}

    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("version_name",) in unique_sets
    assert ("generation_signature",) in unique_sets

    checks = " ".join(
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )
    for status in ("GENERATING", "READY", "FAILED", "RETIRED"):
        assert status in checks
