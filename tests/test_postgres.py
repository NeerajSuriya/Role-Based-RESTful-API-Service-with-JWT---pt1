from uuid import uuid4

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Resource, ResourceTransaction, User


def test_migration_schema(test_engine) -> None:
    inspector = inspect(test_engine)
    assert {"users", "resources", "resource_transactions", "alembic_version"}.issubset(
        inspector.get_table_names()
    )
    assert {"uq_users_email", "ck_users_role"}.issubset(
        {constraint["name"] for constraint in inspector.get_unique_constraints("users")}
        | {constraint["name"] for constraint in inspector.get_check_constraints("users")}
    )
    assert {"borrowed_at", "returned_at"}.issubset(
        {column["name"] for column in inspector.get_columns("resource_transactions")}
    )
    assert {
        "ix_resource_transactions_user_id",
        "ix_resource_transactions_resource_id",
        "ix_resource_transactions_status",
    }.issubset({index["name"] for index in inspector.get_indexes("resource_transactions")})


def test_user_create_read_and_duplicate(client) -> None:
    email = f"{uuid4()}@example.com"
    payload = {"email": email, "password": "secure-test-password"}
    created = client("POST", "/auth/register", json=payload)
    assert created.status_code == 201
    assert "password_hash" not in created.json()

    user_id = created.json()["id"]
    assert client("GET", f"/users/{user_id}").json()["email"] == email
    assert client("POST", "/auth/register", json=payload).status_code == 409
    assert client("GET", f"/users/{user_id}").status_code == 200
    assert client("GET", "/users/99999999").status_code == 404


def test_resource_crud_and_validation(client) -> None:
    created = client("POST", "/resources", json={"name": "Projector", "quantity": 3})
    assert created.status_code == 201
    resource_id = created.json()["id"]
    assert client("GET", f"/resources/{resource_id}").json()["quantity"] == 3

    updated = client("PATCH", f"/resources/{resource_id}", json={"quantity": 5})
    assert updated.status_code == 200
    assert updated.json()["quantity"] == 5
    assert client("POST", "/resources", json={"name": "Invalid", "quantity": -1}).status_code == 422
    zero_quantity = client(
        "POST", "/resources", json={"name": "Out of stock", "is_available": True}
    )
    assert zero_quantity.status_code == 201
    assert zero_quantity.json()["is_available"] is True

    assert client("DELETE", f"/resources/{resource_id}").status_code == 204
    assert client("GET", f"/resources/{resource_id}").status_code == 404
    assert client("DELETE", "/resources/99999999").status_code == 404


def test_resource_search_and_filters(client) -> None:
    client(
        "POST",
        "/resources",
        json={
            "name": "Blue Laptop",
            "description": "Portable computer",
            "category": "electronics",
            "quantity": 2,
            "is_available": True,
        },
    )
    client(
        "POST",
        "/resources",
        json={
            "name": "Laptop Stand",
            "category": "accessories",
            "quantity": 4,
            "is_available": False,
        },
    )

    assert len(client("GET", "/resources?search=LAPTOP").json()) == 2
    assert len(client("GET", "/resources?search=portable").json()) == 1
    assert len(client("GET", "/resources?category=electronics").json()) == 1
    assert len(client("GET", "/resources?is_available=true").json()) == 1
    assert len(
        client("GET", "/resources?search=laptop&category=electronics&is_available=true").json()
    ) == 1
    assert client("GET", "/resources?search=").status_code == 422
    assert client("GET", "/resources?category=").status_code == 422


def test_transaction_and_related_queries(client) -> None:
    user = client(
        "POST",
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "secure-test-password"},
    ).json()
    resource = client(
        "POST", "/resources", json={"name": "Tablet", "quantity": 2, "is_available": True}
    ).json()
    payload = {"user_id": user["id"], "resource_id": resource["id"], "quantity": 1}

    assert client("POST", "/transactions", json={**payload, "quantity": 0}).status_code == 422
    created = client("POST", "/transactions", json=payload)
    assert created.status_code == 201
    transaction_id = created.json()["id"]
    assert client("GET", f"/transactions/{transaction_id}").json()["status"] == "pending"
    assert len(client("GET", f"/transactions?user_id={user['id']}").json()) == 1
    assert len(client("GET", f"/transactions?resource_id={resource['id']}").json()) == 1
    assert client("DELETE", f"/resources/{resource['id']}").status_code == 409


def test_transaction_foreign_keys(client) -> None:
    resource = client("POST", "/resources", json={"name": "Book"}).json()
    user = client(
        "POST",
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "secure-test-password"},
    ).json()
    assert client(
        "POST",
        "/transactions",
        json={"user_id": 99999999, "resource_id": resource["id"], "quantity": 1},
    ).status_code == 404
    assert client(
        "POST",
        "/transactions",
        json={"user_id": user["id"], "resource_id": 99999999, "quantity": 1},
    ).status_code == 404


def test_database_constraints(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        db_session.add(Resource(name="Invalid quantity", quantity=-1))
        db_session.commit()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.add(
            ResourceTransaction(user_id=99999999, resource_id=99999999, quantity=1)
        )
        db_session.commit()
    db_session.rollback()

    email = f"{uuid4()}@example.com"
    db_session.add_all(
        [User(email=email, password_hash="hash"), User(email=email, password_hash="hash")]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
