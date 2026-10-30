from collections.abc import Generator

import pytest
from app.api.dependencies import get_db
from app.api.routes.auth import throttle
from app.database.base import Base
from app.main import app
from app.models import Conversation, Message, User, UserSession  # noqa: F401
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def database() -> Generator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(database: Session) -> Generator[TestClient]:
    def override_database() -> Generator[Session]:
        yield database

    app.dependency_overrides[get_db] = override_database
    throttle.attempts.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
