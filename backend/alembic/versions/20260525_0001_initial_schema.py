"""Initial schema.

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "20260525_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    return {column["name"] for column in inspect(bind).get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=50), nullable=False),
            sa.Column("display_name", sa.String(length=100), nullable=False),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("username"),
        )

    if not inspector.has_table("transactions"):
        op.create_table(
            "transactions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("transaction_date", sa.Date(), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("transaction_type", sa.String(length=10), nullable=False),
            sa.Column("classification", sa.String(length=20), nullable=True),
            sa.Column("personal_category", sa.String(length=80), nullable=True),
            sa.Column("expensed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("statement_format", sa.String(length=80), nullable=True),
            sa.Column("source_hash", sa.String(length=64), nullable=False),
            sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("source_hash", name="uq_transactions_source_hash"),
        )
        return

    columns = _column_names("transactions")
    if "expensed" not in columns:
        op.add_column(
            "transactions",
            sa.Column("expensed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if "personal_category" not in columns:
        op.add_column("transactions", sa.Column("personal_category", sa.String(length=80), nullable=True))


def downgrade() -> None:
    pass
