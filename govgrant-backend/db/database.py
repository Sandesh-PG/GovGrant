"""SQLite engine setup, session dependency, and table creation."""
from sqlmodel import Session, SQLModel, create_engine

from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite
    echo=False,
)


def create_db_and_tables() -> None:
    """Create all tables on startup (idempotent)."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — yields a DB session per request."""
    with Session(engine) as session:
        yield session
