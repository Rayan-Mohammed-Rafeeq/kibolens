from datetime import datetime, timedelta
from datetime import timezone as tz

UTC = tz.utc

from app.models.session import UserSession
from app.models.user import User
from app.services.auth import (
    BootstrapAlreadyCompletedError, 
    bootstrap_administrator, 
    create_session,
    hash_password
)
from app.core.config import get_settings
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def bootstrap(database: Session, username: str = "admin") -> User:
    return bootstrap_administrator(
        database, 
        username, 
        f"{username}@example.com",  # Use example.com for testing
        "correct-horse-battery-staple"
    )


def create_test_session(database: Session, user: User) -> tuple[str, str]:
    """Create authenticated session for testing without going through OTP flow.
    
    Returns (session_token, csrf_token) for authenticated requests.
    TestClient requires cookies to be passed per-request via cookies parameter.
    """
    raw_token, csrf_token, _ = create_session(database, user, get_settings())
    return raw_token, csrf_token


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
    user = bootstrap(database)
    assert client.get("/api/v1/auth/me").status_code == 401

    # Verify password-only login does not create session
    invalid_login = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "wrong"}
    )
    assert invalid_login.status_code == 401
    
    # Valid password should NOT create session (returns LoginStage1Response)
    valid_password = client.post(
        "/api/v1/auth/login", 
        json={"email": "admin@example.com", "password": "correct-horse-battery-staple"}
    )
    assert valid_password.status_code == 200
    response_data = valid_password.json()
    assert response_data["requires_otp"] == True
    assert "masked_email" in response_data
    # Verify no session was created
    assert client.get("/api/v1/auth/me").status_code == 401

    # Create session via test fixture (simulates successful OTP verification)
    session_token, csrf_token = create_test_session(database, user)
    cookies = {"kibolens_session": session_token}
    
    assert client.get("/api/v1/auth/me", cookies=cookies).json()["username"] == "admin"
    assert client.post("/api/v1/conversations", json={"title": "Needs CSRF"}, cookies=cookies).status_code == 403

    logout = client.post("/api/v1/auth/logout", headers=headers(csrf_token), cookies=cookies)
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me", cookies=cookies).status_code == 401


def test_expired_session_is_rejected(client: TestClient, database: Session) -> None:
    user = bootstrap(database)
    session_token, csrf_token = create_test_session(database, user)
    cookies = {"kibolens_session": session_token}
    
    session = database.query(UserSession).one()
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    database.commit()
    assert client.get("/api/v1/auth/me", cookies=cookies).status_code == 401


def test_conversations_are_persisted_paginated_and_private(
    client: TestClient, database: Session
) -> None:
    admin = bootstrap(database)
    other = User(
        username="other", 
        email="other@example.com",
        email_normalized="other@example.com",
        password_hash=hash_password("correct-horse-battery-staple"), 
        role="user"
    )
    database.add(other)
    database.commit()
    database.refresh(other)
    
    session_token, csrf_token = create_test_session(database, admin)
    cookies = {"kibolens_session": session_token}

    created = client.post(
        "/api/v1/conversations", json={"title": "Investigate Kibo"}, headers=headers(csrf_token), cookies=cookies
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Is everything fine?"},
        headers=headers(csrf_token),
        cookies=cookies,
    )
    assert message.status_code == 201
    assert message.json()["role"] == "user"
    assert (
        client.get(f"/api/v1/conversations/{conversation_id}/messages", cookies=cookies).json()["items"][0][
            "content"
        ]
        == "Is everything fine?"
    )

    second = client.post(
        "/api/v1/conversations", json={"title": "Second"}, headers=headers(csrf_token), cookies=cookies
    )
    assert second.status_code == 201
    page = client.get("/api/v1/conversations?limit=1", cookies=cookies).json()
    assert len(page["items"]) == 1
    assert page["next_offset"] == 1

    other_session_token, other_csrf = create_test_session(database, other)
    other_cookies = {"kibolens_session": other_session_token}
    
    assert client.get(f"/api/v1/conversations/{conversation_id}", cookies=other_cookies).status_code == 404
    assert (
        client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers(other_csrf),
            cookies=other_cookies,
        ).status_code
        == 404
    )

    assert (
        client.delete(
            f"/api/v1/conversations/{conversation_id}", headers=headers(csrf_token), cookies=cookies
        ).status_code
        == 204
    )
    assert client.get(f"/api/v1/conversations/{conversation_id}", cookies=cookies).status_code == 404
    assert admin.username == "admin"


def test_investigation_creates_assistant_response(
    client: TestClient, database: Session
) -> None:
    """Test that investigation endpoint creates user message, runs AI, and adds assistant response."""
    admin = bootstrap(database)
    session_token, csrf_token = create_test_session(database, admin)
    cookies = {"kibolens_session": session_token}

    # Create conversation
    created = client.post(
        "/api/v1/conversations",
        json={"title": "AI Test"},
        headers=headers(csrf_token),
        cookies=cookies,
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    # Call investigation endpoint
    investigation = client.post(
        f"/api/v1/conversations/{conversation_id}/investigate",
        json={"content": "What is the CPU usage?"},
        headers=headers(csrf_token),
        cookies=cookies,
    )
    
    # Should return investigation response
    assert investigation.status_code == 200
    result = investigation.json()
    assert result["question"] == "What is the CPU usage?"
    assert "findings" in result
    assert "evidence" in result
    assert "data_sources" in result
    assert "routing_metadata" in result
    
    # Verify both user and assistant messages were created
    messages_response = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        cookies=cookies,
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()["items"]
    
    # Should have user message and assistant response
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What is the CPU usage?"
    assert messages[1]["role"] == "assistant"
    # Assistant message should contain findings or error message
    assert len(messages[1]["content"]) > 0
