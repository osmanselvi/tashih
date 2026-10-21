"""Veritabanı bağlantısı, oturum yönetimi ve basit alan migrasyonu."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL, ensure_dirs

ensure_dirs()

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models  # noqa: F401  (modelleri kaydet)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_all sonrası eksik kalan sütunları ALTER TABLE ile ekler (eski kurulumlar)."""
    wanted = {
        "pages": {"width": "FLOAT", "height": "FLOAT", "words": "TEXT"},
        "suggestions": {
            "rect": "TEXT",
            "source": "VARCHAR(16) DEFAULT 'ai'",
            "mutation": "VARCHAR(16)",
        },
    }
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in wanted.items():
            if table not in tables:
                continue
            have = {c["name"] for c in inspector.get_columns(table)}
            for name, coltype in columns.items():
                if name not in have:
                    conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")
                    )


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
