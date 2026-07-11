from sqlmodel import Session, SQLModel, create_engine, text
from app.config import get_settings

_settings = get_settings()

_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(_settings.database_url, echo=_settings.database_echo, connect_args=_connect_args)


def init_db() -> None:
    """Create all tables if they don't already exist."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency that yields a DB session."""
    with Session(engine) as session:
        yield session


def check_connection() -> bool:
    """Lightweight connectivity probe used by the health endpoint and
    startup validation. Returns False instead of raising, so callers can
    build a health report without try/except everywhere."""
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
        return True
    except Exception:
        return False
