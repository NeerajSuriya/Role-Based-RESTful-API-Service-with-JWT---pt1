from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Resource, ResourceTransaction, User


def create_user(db: Session, **values: object) -> User:
    user = User(**values)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_resource(db: Session, **values: object) -> Resource:
    resource = Resource(**values)
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def get_resource(db: Session, resource_id: int) -> Resource | None:
    return db.get(Resource, resource_id)


def list_resources(
    db: Session,
    *,
    search: str | None = None,
    category: str | None = None,
    is_available: bool | None = None,
) -> list[Resource]:
    statement = select(Resource).order_by(Resource.id)
    if search is not None:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(Resource.name.ilike(pattern), Resource.description.ilike(pattern))
        )
    if category is not None:
        statement = statement.where(Resource.category == category)
    if is_available is not None:
        statement = statement.where(Resource.is_available.is_(is_available))
    return list(db.scalars(statement))


def update_resource(db: Session, resource: Resource, **changes: object) -> Resource:
    for key, value in changes.items():
        setattr(resource, key, value)
    db.commit()
    db.refresh(resource)
    return resource


def delete_resource(db: Session, resource: Resource) -> None:
    db.delete(resource)
    db.commit()


class InvalidTransactionTransition(ValueError):
    pass


class InsufficientResourceQuantity(ValueError):
    pass


def create_transaction(db: Session, **values: object) -> ResourceTransaction:
    transaction = ResourceTransaction(**values)
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def transition_transaction(
    db: Session, transaction_id: int, action: str
) -> ResourceTransaction | None:
    transitions = {
        "approve": ("pending", "approved"),
        "reject": ("pending", "rejected"),
        "borrow": ("approved", "borrowed"),
        "return": ("borrowed", "returned"),
    }
    expected, target = transitions[action]
    transaction = db.scalar(
        select(ResourceTransaction)
        .where(ResourceTransaction.id == transaction_id)
        .with_for_update()
    )
    if transaction is None:
        return None
    if transaction.status != expected:
        raise InvalidTransactionTransition

    if action in {"approve", "return"}:
        resource = db.scalar(
            select(Resource).where(Resource.id == transaction.resource_id).with_for_update()
        )
        if resource is None:
            raise InvalidTransactionTransition
        if action == "approve":
            if not resource.is_available or resource.quantity < transaction.quantity:
                raise InsufficientResourceQuantity
            resource.quantity -= transaction.quantity
            resource.is_available = resource.quantity > 0
        else:
            resource.quantity += transaction.quantity
            resource.is_available = True

    transaction.status = target
    now = datetime.now(timezone.utc)
    if action == "borrow":
        transaction.borrowed_at = now
    elif action == "return":
        transaction.returned_at = now
    db.commit()
    db.refresh(transaction)
    return transaction


def get_transaction(db: Session, transaction_id: int) -> ResourceTransaction | None:
    return db.get(ResourceTransaction, transaction_id)


def list_transactions(
    db: Session, *, user_id: int | None = None, resource_id: int | None = None
) -> list[ResourceTransaction]:
    statement = select(ResourceTransaction).order_by(ResourceTransaction.id)
    if user_id is not None:
        statement = statement.where(ResourceTransaction.user_id == user_id)
    if resource_id is not None:
        statement = statement.where(ResourceTransaction.resource_id == resource_id)
    return list(db.scalars(statement))
