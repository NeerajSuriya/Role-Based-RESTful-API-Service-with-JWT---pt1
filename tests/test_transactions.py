from uuid import uuid4

from app.models import Resource


def test_request_approve_borrow_return_updates_stock(client) -> None:
    user = client(
        "POST",
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "secure-password"},
    ).json()
    resource = client(
        "POST",
        "/resources",
        json={"name": "Camera", "quantity": 2, "is_available": True},
    ).json()
    payload = {"user_id": user["id"], "resource_id": resource["id"], "quantity": 2}

    requested = client("POST", "/transactions", json=payload)
    assert requested.status_code == 201
    transaction_id = requested.json()["id"]
    assert requested.json()["status"] == "pending"
    assert requested.json()["borrowed_at"] is None
    assert requested.json()["returned_at"] is None

    approved = client("POST", f"/transactions/{transaction_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert client("GET", f"/resources/{resource['id']}").json()["quantity"] == 0
    assert client("GET", f"/resources/{resource['id']}").json()["is_available"] is False
    assert client(
        "POST", "/transactions", json={**payload, "quantity": 1}
    ).status_code == 409

    borrowed = client("POST", f"/transactions/{transaction_id}/borrow")
    assert borrowed.status_code == 200
    assert borrowed.json()["status"] == "borrowed"
    assert borrowed.json()["borrowed_at"] is not None

    returned = client("POST", f"/transactions/{transaction_id}/return")
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"
    assert returned.json()["returned_at"] is not None
    final_resource = client("GET", f"/resources/{resource['id']}").json()
    assert final_resource["quantity"] == 2
    assert final_resource["is_available"] is True
    assert client("POST", f"/transactions/{transaction_id}/return").status_code == 409


def test_rejected_request_does_not_change_inventory(client) -> None:
    user = client(
        "POST",
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "secure-password"},
    ).json()
    resource = client(
        "POST",
        "/resources",
        json={"name": "Microphone", "quantity": 1, "is_available": True},
    ).json()
    request = client(
        "POST",
        "/transactions",
        json={"user_id": user["id"], "resource_id": resource["id"], "quantity": 1},
    )
    transaction_id = request.json()["id"]

    rejected = client("POST", f"/transactions/{transaction_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client("GET", f"/resources/{resource['id']}").json()["quantity"] == 1
    assert client("POST", f"/transactions/{transaction_id}/approve").status_code == 409
    assert client("POST", f"/transactions/{transaction_id}/borrow").status_code == 409


def test_approval_rejects_when_stock_changes_after_request(client, db_session) -> None:
    user = client(
        "POST",
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "secure-password"},
    ).json()
    resource = client(
        "POST",
        "/resources",
        json={"name": "Monitor", "quantity": 1, "is_available": True},
    ).json()
    request = client(
        "POST",
        "/transactions",
        json={"user_id": user["id"], "resource_id": resource["id"], "quantity": 1},
    )
    transaction_id = request.json()["id"]

    stock = db_session.get(Resource, resource["id"])
    stock.quantity = 0
    stock.is_available = False
    db_session.flush()

    approval = client("POST", f"/transactions/{transaction_id}/approve")
    assert approval.status_code == 409
    assert client("GET", f"/transactions/{transaction_id}").json()["status"] == "pending"
    assert client("POST", "/transactions/99999999/approve").status_code == 404
