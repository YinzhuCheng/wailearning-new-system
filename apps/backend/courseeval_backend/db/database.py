from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from apps.backend.courseeval_backend.core.config import settings

engine_kwargs = {"pool_pre_ping": True}

if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def configure_sqlite_connection(dbapi_connection) -> None:  # pragma: no cover - connection hook
    for statement in (
        "PRAGMA foreign_keys=ON",
        "PRAGMA busy_timeout=30000",
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
    ):
        try:
            dbapi_connection.execute(statement)
        except Exception:
            pass


if settings.DATABASE_URL.startswith("sqlite"):
    event.listen(engine, "connect", lambda dbapi_connection, _record: configure_sqlite_connection(dbapi_connection))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
