from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from app.core.config import settings
from app.core.security import verify_password
from app.models import User


def test_register_login_and_password_hashing(client, db_session) -> None:
    email = f"{uuid4()}@example.com"
    password = "a-secure-password"
    registered = client(
        "POST", "/auth/register", json={"email": email, "password": password}
    )
    assert registered.status_code == 201
    assert "password_hash" not in registered.json()

    user = db_session.query(User).filter_by(email=email).one()
    assert user.password_hash != password
    assert verify_password(password, user.password_hash)

    login = client("POST", "/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"
    assert client(
        "GET", "/resources", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    ).status_code == 200


def test_registration_and_login_validation(client) -> None:
    assert client(
        "POST",
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "short"},
    ).status_code == 422
    assert client(
        "POST",
        "/auth/login",
        json={"email": f"{uuid4()}@example.com", "password": "unknown-user"},
    ).status_code == 401


def test_login_rejects_bad_password_and_malformed_hash(client, db_session) -> None:
    bad_password = client(
        "POST",
        "/auth/login",
        json={"email": "test-auth@example.com", "password": "incorrect-password"},
    )
    assert bad_password.status_code == 401

    user = db_session.query(User).filter_by(email="test-auth@example.com").one()
    user.password_hash = "not-a-valid-password-hash"
    db_session.flush()
    malformed = client(
        "POST",
        "/auth/login",
        json={"email": user.email, "password": "test-password"},
    )
    assert malformed.status_code == 401


def test_protected_endpoint_rejects_missing_invalid_and_expired_tokens(client) -> None:
    assert client("GET", "/resources", headers={"Authorization": ""}).status_code == 401
    assert client(
        "GET", "/resources", headers={"Authorization": "Bearer invalid"}
    ).status_code == 401

    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    assert client(
        "GET", "/resources", headers={"Authorization": f"Bearer {expired}"}
    ).status_code == 401
