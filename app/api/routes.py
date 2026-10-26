from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models import Resource, User
from app.schemas import (
    ResourceCreate,
    ResourceRead,
    ResourceTransactionCreate,
    ResourceTransactionRead,
    ResourceUpdate,
    TokenRead,
    UserLogin,
    UserRead,
    UserRegister,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: DbSession,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    subject = decode_access_token(credentials.credentials)
    if subject is None or not subject.isdecimal():
        raise unauthorized
    user = crud.get_user(db, int(subject))
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    def check(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return check


StaffUser = Annotated[User, Depends(require_roles("administrator", "teacher"))]


def _conflict(db: Session, detail: str) -> HTTPException:
    db.rollback()
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _transition_transaction(
    transaction_id: int, action: str, db: Session
) -> ResourceTransactionRead:
    try:
        transaction = crud.transition_transaction(db, transaction_id, action)
    except crud.InsufficientResourceQuantity:
        raise _conflict(db, "Insufficient available resource quantity") from None
    except crud.InvalidTransactionTransition:
        raise _conflict(db, "Invalid transaction state transition") from None
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction


@router.post("/auth/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: DbSession) -> UserRead:
    try:
        return crud.create_user(
            db, email=payload.email, password_hash=hash_password(payload.password)
        )
    except IntegrityError:
        raise _conflict(db, "A user with this email already exists") from None


@router.post("/auth/login", response_model=TokenRead)
def login(payload: UserLogin, db: DbSession) -> TokenRead:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.is_active or not verify_password(
        payload.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        token = create_access_token(str(user.id))
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        ) from None
    return TokenRead(access_token=token)


@router.get("/users/{user_id}", response_model=UserRead)
def read_user(user_id: int, db: DbSession, current_user: CurrentUser) -> UserRead:
    if user_id != current_user.id and current_user.role != "administrator":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    user = crud.get_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/resources", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
def create_resource(
    payload: ResourceCreate, db: DbSession, _: StaffUser
) -> ResourceRead:
    return crud.create_resource(db, **payload.model_dump())


@router.get("/resources", response_model=list[ResourceRead])
def read_resources(
    db: DbSession,
    _: CurrentUser,
    search: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
    category: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    is_available: bool | None = None,
) -> list[ResourceRead]:
    return crud.list_resources(
        db, search=search, category=category, is_available=is_available
    )


@router.get("/resources/{resource_id}", response_model=ResourceRead)
def read_resource(
    resource_id: int, db: DbSession, _: CurrentUser
) -> ResourceRead:
    resource = crud.get_resource(db, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.patch("/resources/{resource_id}", response_model=ResourceRead)
def update_resource(
    resource_id: int, payload: ResourceUpdate, db: DbSession, _: StaffUser
) -> ResourceRead:
    resource = crud.get_resource(db, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    changes = payload.model_dump(exclude_unset=True)
    try:
        return crud.update_resource(db, resource, **changes)
    except IntegrityError:
        raise _conflict(db, "Resource update conflicts with existing data") from None


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resource(resource_id: int, db: DbSession, _: StaffUser) -> None:
    resource = crud.get_resource(db, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        crud.delete_resource(db, resource)
    except IntegrityError:
        raise _conflict(db, "Resource has transactions and cannot be deleted") from None


@router.post(
    "/transactions",
    response_model=ResourceTransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    payload: ResourceTransactionCreate, db: DbSession, current_user: CurrentUser
) -> ResourceTransactionRead:
    if current_user.role == "student" and payload.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Students can only request resources for themselves")
    if crud.get_user(db, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    resource = crud.get_resource(db, payload.resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if not resource.is_available or payload.quantity > resource.quantity:
        raise _conflict(db, "Insufficient available resource quantity")
    try:
        return crud.create_transaction(db, **payload.model_dump())
    except IntegrityError:
        raise _conflict(db, "Transaction conflicts with existing data") from None


@router.post("/transactions/{transaction_id}/approve", response_model=ResourceTransactionRead)
def approve_transaction(
    transaction_id: int, db: DbSession, _: StaffUser
) -> ResourceTransactionRead:
    return _transition_transaction(transaction_id, "approve", db)


@router.post("/transactions/{transaction_id}/reject", response_model=ResourceTransactionRead)
def reject_transaction(
    transaction_id: int, db: DbSession, _: StaffUser
) -> ResourceTransactionRead:
    return _transition_transaction(transaction_id, "reject", db)


@router.post("/transactions/{transaction_id}/borrow", response_model=ResourceTransactionRead)
def borrow_transaction(
    transaction_id: int, db: DbSession, _: StaffUser
) -> ResourceTransactionRead:
    return _transition_transaction(transaction_id, "borrow", db)


@router.post("/transactions/{transaction_id}/return", response_model=ResourceTransactionRead)
def return_transaction(
    transaction_id: int, db: DbSession, _: StaffUser
) -> ResourceTransactionRead:
    return _transition_transaction(transaction_id, "return", db)


@router.get("/transactions", response_model=list[ResourceTransactionRead])
def read_transactions(
    db: DbSession,
    current_user: CurrentUser,
    user_id: Annotated[int | None, Query(gt=0)] = None,
    resource_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[ResourceTransactionRead]:
    if current_user.role == "student":
        if user_id is not None and user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Students can only view their own transactions")
        user_id = current_user.id
    if user_id is not None and crud.get_user(db, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    if resource_id is not None and crud.get_resource(db, resource_id) is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return crud.list_transactions(db, user_id=user_id, resource_id=resource_id)


@router.get("/transactions/{transaction_id}", response_model=ResourceTransactionRead)
def read_transaction(
    transaction_id: int, db: DbSession, current_user: CurrentUser
) -> ResourceTransactionRead:
    transaction = crud.get_transaction(db, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if current_user.role == "student" and transaction.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Students can only view their own transactions")
    return transaction
