from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


connect_args: dict[str, bool] = {}
if settings.use_sqlite:
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401
    from sqlalchemy import inspect, text

    Base.metadata.create_all(bind=engine)

    # Idempotent column adds for tables that pre-existed without later columns.
    # SQLAlchemy's create_all does not ALTER existing tables, and we don't run
    # Alembic in this project. Each entry: (table, column, "ADD COLUMN ..." DDL).
    additive_columns: list[tuple[str, str, str]] = [
        ("query_logs", "source", "ALTER TABLE query_logs ADD COLUMN source VARCHAR(16)"),
    ]
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in additive_columns:
            if not inspector.has_table(table):
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            if column not in existing:
                conn.execute(text(ddl))

