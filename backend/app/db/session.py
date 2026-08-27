from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def create_database_engine(database_url: str | None = None) -> Engine:
    return create_engine(
        database_url or settings.api_database_url,
        pool_pre_ping=True,
    )


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
