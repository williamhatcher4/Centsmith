"""Add import_batches table and transactions.import_batch_id FK.

Revision ID: 20260527_0004
Revises: 20260527_0003
Create Date: 2026-05-27 00:00:00
"""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "20260527_0004"
down_revision: Union[str, None] = "20260527_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("import_batches"):
        op.create_table(
            "import_batches",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("statement_format", sa.String(length=80), nullable=True),
            sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_by_action", sa.String(length=40), nullable=False, server_default=sa.text("'import'")),
        )

    tx_cols = {c["name"] for c in inspector.get_columns("transactions")}
    if "import_batch_id" not in tx_cols:
        op.add_column(
            "transactions",
            sa.Column("import_batch_id", sa.String(length=36), nullable=True),
        )
        # SQLite cannot add an FK constraint to an existing column without a table rebuild.
        # The relationship is enforced at the application level (and via SET NULL on delete
        # when SQLite is rebuilt by future migrations).

    # Backfill: group existing rows by (imported_at truncated to minute, statement_format)
    # and create one synthetic batch per group.
    rows = bind.execute(
        sa.text(
            "SELECT id, imported_at, statement_format FROM transactions "
            "WHERE import_batch_id IS NULL AND (is_manual = 0 OR is_manual IS NULL)"
        )
    ).fetchall()

    groups: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        imported_at = row[1]
        # Truncate to minute precision; imported_at may be a string or datetime depending on driver.
        key_imported = str(imported_at)[:16] if imported_at is not None else ""
        key_format = row[2] or ""
        groups.setdefault((key_imported, key_format), []).append(row[0])

    fallback_imported_at = datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds")
    for (imported_at_key, format_key), tx_ids in groups.items():
        if not tx_ids:
            continue
        batch_id = str(uuid.uuid4())
        op.execute(
            sa.text(
                "INSERT INTO import_batches (id, filename, statement_format, imported_at, row_count, created_by_action) "
                "VALUES (:id, :filename, :fmt, :imported_at, :count, :action)"
            ).bindparams(
                id=batch_id,
                filename="Legacy import",
                fmt=format_key or None,
                imported_at=imported_at_key or fallback_imported_at,
                count=len(tx_ids),
                action="legacy",
            )
        )
        # Stamp the matching transactions.
        op.execute(
            sa.text(
                "UPDATE transactions SET import_batch_id = :bid WHERE id IN ("
                + ",".join(str(int(i)) for i in tx_ids)
                + ")"
            ).bindparams(bid=batch_id)
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tx_cols = {c["name"] for c in inspector.get_columns("transactions")}
    if "import_batch_id" in tx_cols:
        op.drop_column("transactions", "import_batch_id")
    if inspector.has_table("import_batches"):
        op.drop_table("import_batches")
