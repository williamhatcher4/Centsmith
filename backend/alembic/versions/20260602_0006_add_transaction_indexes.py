"""Add indexes for common transaction filters and sorts.

Revision ID: 20260602_0006
Revises: 20260602_0005
Create Date: 2026-06-02 00:00:01
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "20260602_0006"
down_revision: Union[str, None] = "20260602_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_transactions_transaction_date", ["transaction_date"]),
    ("ix_transactions_classification_date", ["classification", "transaction_date"]),
    ("ix_transactions_personal_category_date", ["personal_category", "transaction_date"]),
    ("ix_transactions_expensed", ["classification", "expensed"]),
    ("ix_transactions_import_batch_id", ["import_batch_id"]),
]


def upgrade() -> None:
    bind = op.get_bind()
    existing = {ix["name"] for ix in inspect(bind).get_indexes("transactions")}
    for name, columns in _INDEXES:
        if name not in existing:
            op.create_index(name, "transactions", columns)


def downgrade() -> None:
    bind = op.get_bind()
    existing = {ix["name"] for ix in inspect(bind).get_indexes("transactions")}
    for name, _ in _INDEXES:
        if name in existing:
            op.drop_index(name, table_name="transactions")
