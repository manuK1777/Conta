
from contextlib import contextmanager
import os

from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine


load_dotenv()


DB_PATH = os.getenv("CONTA_DB_PATH", "./conta.db")
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session


def init_db():
    SQLModel.metadata.create_all(engine)