"""Create users, resources, and resource transactions.

Revision ID: 20261025_0001
Revises:
Create Date: 2026-10-25
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261025_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), server_default=sa.text("'student'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "role IN ('administrator', 'teacher', 'student')", name="ck_users_role"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "resources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("quantity", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_resources_quantity_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "resource_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_resource_transactions_quantity_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'borrowed', 'returned')",
            name="ck_resource_transactions_status",
        ),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resource_transactions_user_id", "resource_transactions", ["user_id"])
    op.create_index("ix_resource_transactions_resource_id", "resource_transactions", ["resource_id"])
    op.create_index("ix_resource_transactions_status", "resource_transactions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_resource_transactions_status", table_name="resource_transactions")
    op.drop_index("ix_resource_transactions_resource_id", table_name="resource_transactions")
    op.drop_index("ix_resource_transactions_user_id", table_name="resource_transactions")
    op.drop_table("resource_transactions")
    op.drop_table("resources")
    op.drop_table("users")
