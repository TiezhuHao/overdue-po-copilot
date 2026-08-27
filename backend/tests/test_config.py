from app.core.config import Settings


def test_database_passwords_are_redacted_from_settings_repr() -> None:
    configured = Settings(
        database_url_api="postgresql+psycopg://system_a_api:top-secret@localhost/system_a"
    )
    assert "top-secret" not in repr(configured)
    assert "**********" in repr(configured)
