import asyncio
from collections.abc import Callable, Generator
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import User


def validate_database_separation(test_url: str, development_url: str) -> URL:
    test = make_url(test_url)
    development = make_url(development_url)
    if test.database == development.database or (
        test.host,
        test.port,
        test.database,
    ) == (development.host, development.port, development.database):
        raise ValueError("TEST_DATABASE_URL must not target the configured application database")
    return test


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    database_url = settings.test_database_url
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL test database")

    try:
        url = validate_database_separation(database_url, settings.database_url)
    except ValueError as error:
        pytest.fail(str(error))
    if not url.drivername.startswith("postgresql") or "test" not in (url.database or "").lower():
        pytest.fail("TEST_DATABASE_URL must point to a PostgreSQL database with 'test' in its name")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        alembic_config = Config("alembic.ini")
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Generator[Session, None, None]:
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[Callable[..., httpx.Response], None, None]:
    monkeypatch.setattr(settings, "jwt_secret_key", "test-only-secret-key-at-least-32-bytes")
    auth_user = User(
        email="test-auth@example.com",
        password_hash=hash_password("test-password"),
        role="administrator",
    )
    db_session.add(auth_user)
    db_session.flush()
    authorization = {
        "Authorization": f"Bearer {create_access_token(str(auth_user.id))}"
    }

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        kwargs["headers"] = {**authorization, **kwargs.pop("headers", {})}

        async def send() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http_client:
                return await http_client.request(method, path, **kwargs)

        return asyncio.run(send())

    try:
        yield request
    finally:
        app.dependency_overrides.pop(get_db, None)
