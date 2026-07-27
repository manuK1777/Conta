
from contextlib import contextmanager
import os

from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import text


load_dotenv()


DB_PATH = os.getenv("CONTA_DB_PATH", "./conta.db")
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)

# Columns added to existing tables after their initial release. create_all() only
# creates missing tables, it never alters existing ones, so new nullable columns
# need an explicit additive ALTER TABLE here to reach databases created before them.
_ADDITIVE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "facturaemitida": [
        ("cliente_direccion", "VARCHAR"),
        ("concepto", "VARCHAR"),
    ],
}


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session


def _run_additive_migrations() -> None:
    with engine.connect() as conn:
        for table, columns in _ADDITIVE_COLUMNS.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for column, col_type in columns:
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        conn.commit()


def init_db():
    SQLModel.metadata.create_all(engine)
    _run_additive_migrations()