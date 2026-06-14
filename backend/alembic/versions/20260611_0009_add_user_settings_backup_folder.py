"""Add user_settings.backup_folder (optional custom backup destination).

Revision ID: 20260611_0009
Revises: 20260610_0008
Create Date: 2026-06-11 00:00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260611_0009"
down_revision: Union[str, None] = "20260610_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("user_settings")}
    if "backup_folder" not in columns:
        # Nullable absolute directory path; NULL means the default
        # ``backups/`` folder beside the database.
        op.add_column("user_settings", sa.Column("backup_folder", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    columns = {col["name"] for col in inspector.get_columns("user_settings")}
    if "backup_folder" in columns:
        op.drop_column("user_settings", "backup_folder")
