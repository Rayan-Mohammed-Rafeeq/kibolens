from datetime import UTC, datetime, timedelta

from app.models.session import UserSession
from app.models.user import User
from app.services.auth import BootstrapAlreadyCompletedError, bootstrap_administrator, hash_password
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def bootstrap(database: Session, username: str = "admin") -> User:
    return bootstrap_administrator(database, username, "correct-horse-battery-staple")


def login(client: TestClient, username: str = "admin") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def headers(csrf_token: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token}


def test_bootstrap_only_allows_one_administrator(database: Session) -> None:
    user = bootstrap(database)
    assert user.username == "admin"
    assert user.password_hash != "correct-horse-battery-staple"

    try:
        bootstrap(database, "second-admin")
    except BootstrapAlreadyCompletedError:
        pass
    else:
        raise AssertionError("bootstrap should reject a second administrator")


def test_login_me_logout_and_csrf_protection(client: TestClient, database: Session) -> None:
    bootstrap(database)
    assert client.get("/api/v1/auth/me").status_code == 401

    invalid_login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong"}
    )
    assert invalid_login.status_code == 401

    csrf_token = login(client)
    assert client.get("/api/v1/auth/me").json()["username"] == "admin"
    assert client.post("/api/v1/conversations", json={"title": "Needs CSRF"}).status_code == 403

    logout = client.post("/api/v1/auth/logout", headers=headers(csrf_token))
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_session_is_rejected(client: TestClient, database: Session) -> None:
    bootstrap(database)
    login(client)
    session = database.query(UserSession).one()
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    database.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_conversations_are_persisted_paginated_and_private(
    client: TestClient, database: Session
) -> None:
    admin = bootstrap(database)
    other = User(
        username="other", password_hash=hash_password("correct-horse-battery-staple"), role="user"
    )
    database.add(other)
    database.commit()
    csrf_token = login(client)

    created = client.post(
        "/api/v1/conversations", json={"title": "Investigate Kibo"}, headers=headers(csrf_token)
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Is everything fine?"},
        headers=headers(csrf_token),
    )
    assert message.status_code == 201
    assert message.json()["role"] == "user"
    assert (
        client.get(f"/api/v1/conversations/{conversation_id}/messages").json()["items"][0][
            "content"
        ]
        == "Is everything fine?"
    )

    second = client.post(
        "/api/v1/conversations", json={"title": "Second"}, headers=headers(csrf_token)
    )
    assert second.status_code == 201
    page = client.get("/api/v1/conversations?limit=1").json()
    assert len(page["items"]) == 1
    assert page["next_offset"] == 1

    other_session = TestClient(client.app)
    other_login = other_session.post(
        "/api/v1/auth/login", json={"username": "other", "password": "correct-horse-battery-staple"}
    )
    assert other_login.status_code == 200
    assert other_session.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    assert (
        other_session.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers(other_login.json()["csrf_token"]),
        ).status_code
        == 404
    )

    assert (
        client.delete(
            f"/api/v1/conversations/{conversation_id}", headers=headers(csrf_token)
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    assert admin.username == "admin"
