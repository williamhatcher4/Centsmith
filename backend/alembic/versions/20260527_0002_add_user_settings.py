"""Add user_settings table.

Revision ID: 20260527_0002
Revises: 20260525_0001
Create Date: 2026-05-27 00:00:00
"""

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "20260527_0002"
down_revision: Union[str, None] = "20260525_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_CATEGORIES = [
    "Groceries", "Dining", "Transportation", "Home", "Health",
    "Subscriptions", "Shopping", "Travel", "Entertainment",
    "Personal Care", "Gifts", "Other", "Transfer", "Income", "Reimbursement",
]


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("user_settings"):
        return
    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("personal_categories", sa.JSON(), nullable=False),
        sa.Column("hidden_pages", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        sa.text(
            "INSERT INTO user_settings (id, personal_categories, hidden_pages, created_at, updated_at) "
            "VALUES (1, :cats, :pages, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ).bindparams(
            cats=json.dumps(_DEFAULT_CATEGORIES),
            pages=json.dumps([]),
        )
    )


def downgrade() -> None:
    op.drop_table("user_settings")
