from collections.abc import Generator
import os
import pytest

# IMPORTANT: Set test environment BEFORE any imports that use get_settings()
os.environ["KIBOLENS_ENVIRONMENT"] = "test"
os.environ["KIBOLENS_DATABASE_URL"] = "sqlite://"
os.environ["KIBOLENS_ALLOWED_EMAILS"] = "admin@example.com,other@example.com,rayanmohammedrafeeq@gmail.com,rakinmohammedrafeeq@gmail.com"
# Force LLM provider to ollama for tests to avoid network calls to cloud providers
os.environ["KIBOLENS_LLM_PROVIDER"] = "ollama"

from app.api.dependencies import get_db
from app.api.routes.auth import throttle
from app.database.base import Base
from app.main import app
from app.models import (  # noqa: F401
    Conversation,
    EvidenceRecord,
    Incident,
    IncidentEvent,
    IncidentSequence,
    Message,
    User,
    UserSession,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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
