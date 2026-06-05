"""Add cards table and transactions.card_id.

Revision ID: 20260603_0007
Revises: 20260602_0006
Create Date: 2026-06-03 00:00:01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260603_0007"
down_revision: Union[str, None] = "20260602_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "cards" not in inspector.get_table_names():
        op.create_table(
            "cards",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("last4", sa.String(length=4), nullable=True),
            sa.Column("statement_day", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    tx_columns = {col["name"] for col in inspector.get_columns("transactions")}
    if "card_id" not in tx_columns:
        # SQLite cannot add a FK constraint to an existing table without a rebuild;
        # the column is added plain and the ON DELETE SET NULL behaviour is enforced
        # in application code (mirrors import_batch_id). Fresh schemas built from the
        # model metadata still get the declared FK.
        op.add_column("transactions", sa.Column("card_id", sa.Integer(), nullable=True))

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("transactions")}
    if "ix_transactions_card_id" not in existing_indexes:
        op.create_index("ix_transactions_card_id", "transactions", ["card_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes("transactions")}
    if "ix_transactions_card_id" in existing_indexes:
        op.drop_index("ix_transactions_card_id", table_name="transactions")

    tx_columns = {col["name"] for col in inspector.get_columns("transactions")}
    if "card_id" in tx_columns:
        op.drop_column("transactions", "card_id")

    if "cards" in inspector.get_table_names():
        op.drop_table("cards")
