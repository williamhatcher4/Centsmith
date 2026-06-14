"""Add import_profiles.date_convention (saved day-first/month-first preference).

Revision ID: 20260610_0008
Revises: 20260603_0007
Create Date: 2026-06-10 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260610_0008"
down_revision: Union[str, None] = "20260603_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("import_profiles")}
    if "date_convention" not in columns:
        # Nullable "mdy" | "dmy"; NULL means the default month-first convention,
        # so existing profiles keep their current behaviour.
        op.add_column("import_profiles", sa.Column("date_convention", sa.String(length=8), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("import_profiles")}
    if "date_convention" in columns:
        op.drop_column("import_profiles", "date_convention")
