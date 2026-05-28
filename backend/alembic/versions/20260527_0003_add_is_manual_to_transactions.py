"""Add is_manual column to transactions.

Revision ID: 20260527_0003
Revises: 20260527_0002
Create Date: 2026-05-27 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "20260527_0003"
down_revision: Union[str, None] = "20260527_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("transactions")}
    if "is_manual" not in cols:
        op.add_column(
            "transactions",
            sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    op.drop_column("transactions", "is_manual")
