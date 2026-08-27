from uuid import UUID

import pytest

from app.core.ids import deterministic_uuid


def test_deterministic_uuid_is_stable() -> None:
    first = deterministic_uuid("dataset-signature", "material", "MAT-001")
    second = deterministic_uuid("dataset-signature", "material", "MAT-001")
    assert first == second
    assert isinstance(first, UUID)
    assert first.version == 5


def test_deterministic_uuid_changes_with_business_identity() -> None:
    assert deterministic_uuid("material", "MAT-001") != deterministic_uuid(
        "material", "MAT-002"
    )


@pytest.mark.parametrize("parts", [(), ("",), ("material", "  ")])
def test_deterministic_uuid_rejects_missing_identity(parts: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        deterministic_uuid(*parts)
