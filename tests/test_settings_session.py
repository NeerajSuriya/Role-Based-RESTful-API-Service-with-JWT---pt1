import pytest

from app.core.config import Settings
from app.db import session as database_session
from tests.conftest import validate_database_separation


def test_database_urls_load_from_environment_and_are_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    development_url = "postgresql+psycopg://dev_user:dev_password@localhost/resource_management"
    test_url = "postgresql+psycopg://test_user:test_password@localhost/resource_management_test"
    monkeypatch.setenv("DATABASE_URL", development_url)
    monkeypatch.setenv("TEST_DATABASE_URL", test_url)

    settings = Settings(_env_file=None)
    assert settings.database_url == development_url
    assert settings.test_database_url == test_url
    assert settings.database_url.rsplit("/", 1)[-1] != settings.test_database_url.rsplit("/", 1)[-1]


def test_test_database_guard_rejects_development_database() -> None:
    with pytest.raises(ValueError, match="must not target"):
        validate_database_separation(
            "postgresql+psycopg://localhost/resource_management_test",
            "postgresql+psycopg://127.0.0.1/resource_management_test",
        )


def test_test_database_guard_allows_separate_database() -> None:
    test_url = validate_database_separation(
        "postgresql+psycopg://localhost/resource_management_test",
        "postgresql+psycopg://localhost/resource_management",
    )
    assert test_url.database == "resource_management_test"


def test_database_dependency_closes_session(monkeypatch: pytest.MonkeyPatch) -> None:
    class SessionStub:
        closed = False

        def close(self) -> None:
            self.closed = True

    session = SessionStub()
    monkeypatch.setattr(database_session, "SessionLocal", lambda: session)
    dependency = database_session.get_db()

    assert next(dependency) is session
    with pytest.raises(StopIteration):
        next(dependency)
    assert session.closed
