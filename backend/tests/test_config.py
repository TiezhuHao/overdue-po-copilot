from app.core.config import Settings


def test_database_passwords_are_redacted_from_settings_repr() -> None:
    configured = Settings(
        database_url_api="postgresql+psycopg://system_a_api:top-secret@localhost/system_a"
    )
    assert "top-secret" not in repr(configured)
    assert "**********" in repr(configured)


def test_pytest_database_url_argument_repr_is_redacted() -> None:
    from tests.conftest import _RedactedDatabaseURL

    value = _RedactedDatabaseURL("postgresql+psycopg://test:fixture-password@localhost/example_test")
    assert "fixture-password" not in repr(value)
    assert "fixture-password" in str(value)
