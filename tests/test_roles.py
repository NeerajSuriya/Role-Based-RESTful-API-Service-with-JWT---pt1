from uuid import uuid4

from app.core.security import create_access_token
from app.models import User


def test_student_permissions_and_ownership(client, db_session) -> None:
    resource = client(
        "POST",
        "/resources",
        json={"name": "Laptop", "quantity": 2, "is_available": True},
    ).json()
    student = client(
        "POST",
        "/auth/register",
        json={
            "email": f"{uuid4()}@example.com",
            "password": "secure-password",
            "role": "administrator",
        },
    ).json()
    assert db_session.get(User, student["id"]).role == "student"
    other_student = client(
        "POST",
        "/auth/register",
        json={"email": f"{uuid4()}@example.com", "password": "secure-password"},
    ).json()
    token = client(
        "POST",
        "/auth/login",
        json={"email": student["email"], "password": "secure-password"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client("GET", "/resources", headers=headers).status_code == 200
    assert client(
        "POST", "/resources", json={"name": "Denied"}, headers=headers
    ).status_code == 403
    assert client("GET", f"/users/{other_student['id']}", headers=headers).status_code == 403
    assert client("GET", f"/users/{student['id']}", headers=headers).status_code == 200

    payload = {"user_id": student["id"], "resource_id": resource["id"], "quantity": 1}
    created = client("POST", "/transactions", json=payload, headers=headers)
    assert created.status_code == 201
    transaction_id = created.json()["id"]
    assert client(
        "POST", f"/transactions/{transaction_id}/approve", headers=headers
    ).status_code == 403
    assert client(
        "POST", f"/transactions/{transaction_id}/reject", headers=headers
    ).status_code == 403
    assert client(
        "POST", "/transactions", json={**payload, "user_id": other_student["id"]}, headers=headers
    ).status_code == 403
    assert len(client("GET", "/transactions", headers=headers).json()) == 1
    assert client(
        "GET", f"/transactions?user_id={other_student['id']}", headers=headers
    ).status_code == 403
    assert client("GET", f"/transactions/{transaction_id}", headers=headers).status_code == 200

    other_token = client(
        "POST",
        "/auth/login",
        json={"email": other_student["email"], "password": "secure-password"},
    ).json()["access_token"]
    assert client(
        "GET", f"/transactions/{transaction_id}", headers={"Authorization": f"Bearer {other_token}"}
    ).status_code == 403


def test_teacher_and_administrator_can_manage_resources(client, db_session) -> None:
    teacher = User(
        email=f"{uuid4()}@example.com",
        password_hash="unused",
        role="teacher",
    )
    db_session.add(teacher)
    db_session.flush()
    teacher_token = create_access_token(str(teacher.id))
    response = client(
        "POST",
        "/resources",
        json={"name": "Teacher resource"},
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert response.status_code == 201
    assert client(
        "DELETE",
        f"/resources/{response.json()['id']}",
        headers={"Authorization": f"Bearer {teacher_token}"},
    ).status_code == 204

    admin = client("POST", "/resources", json={"name": "Admin resource"})
    assert admin.status_code == 201
