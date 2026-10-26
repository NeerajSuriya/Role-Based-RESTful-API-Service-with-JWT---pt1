"""Track transaction borrowing and return timestamps.

Revision ID: 20261025_0002
Revises: 20261025_0001
Create Date: 2026-10-25
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261025_0002"
down_revision: str | None = "20261025_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resource_transactions", sa.Column("borrowed_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "resource_transactions", sa.Column("returned_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("resource_transactions", "returned_at")
    op.drop_column("resource_transactions", "borrowed_at")
