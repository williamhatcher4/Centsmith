"""Add import_profiles table (saved per-bank column mappings).

Revision ID: 20260602_0005
Revises: 20260527_0004
Create Date: 2026-06-02 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "20260602_0005"
down_revision: Union[str, None] = "20260527_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("import_profiles"):
        return
    op.create_table(
        "import_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False, server_default=sa.text("'card'")),
        sa.Column("date_column", sa.Integer(), nullable=False),
        sa.Column("description_column", sa.Integer(), nullable=False),
        sa.Column("amount_column", sa.Integer(), nullable=True),
        sa.Column("debit_column", sa.Integer(), nullable=True),
        sa.Column("credit_column", sa.Integer(), nullable=True),
        sa.Column("amount_convention", sa.String(length=20), nullable=False, server_default=sa.text("'signed'")),
        sa.Column("ignored_payment_patterns", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_import_profiles_name"),
    )


def downgrade() -> None:
    op.drop_table("import_profiles")
