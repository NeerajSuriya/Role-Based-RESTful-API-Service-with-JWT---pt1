from sqlalchemy import inspect

from app.models import Resource, ResourceTransaction, User
from app.schemas import ResourceCreate


def test_zero_quantity_resource_can_be_available() -> None:
    resource = ResourceCreate(name="Out of stock", is_available=True)
    assert resource.quantity == 0
    assert resource.is_available is True


def test_relationships_and_database_constraints() -> None:
    user_relationships = inspect(User).relationships
    resource_relationships = inspect(Resource).relationships
    transaction_relationships = inspect(ResourceTransaction).relationships
    assert user_relationships["transactions"].mapper.class_ is ResourceTransaction
    assert resource_relationships["transactions"].mapper.class_ is ResourceTransaction
    assert transaction_relationships["user"].mapper.class_ is User
    assert transaction_relationships["resource"].mapper.class_ is Resource

    user = User.__table__
    resource = Resource.__table__
    transaction = ResourceTransaction.__table__
    assert any(constraint.name == "uq_users_email" for constraint in user.constraints)
    assert {fk.ondelete for fk in transaction.foreign_keys} == {"RESTRICT"}
    assert {index.name for index in transaction.indexes} == {
        "ix_resource_transactions_user_id",
        "ix_resource_transactions_resource_id",
        "ix_resource_transactions_status",
    }
    assert {constraint.name for constraint in resource.constraints} >= {
        "ck_resources_quantity_nonnegative",
    }
