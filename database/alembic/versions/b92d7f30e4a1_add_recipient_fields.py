"""add recipient fields

Revision ID: b92d7f30e4a1
Revises: a81c4e67d2f9
Create Date: 2026-07-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b92d7f30e4a1"
down_revision: str | Sequence[str] | None = "a81c4e67d2f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("recipient_address", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column("recipient_external_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "recipient_external_id")
    op.drop_column("contacts", "recipient_address")
