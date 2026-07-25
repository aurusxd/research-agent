"""add OK.ru contact URL

Revision ID: b71f6240d9a2
Revises: 9d3c0e12a4b1
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b71f6240d9a2"
down_revision: str | Sequence[str] | None = "9d3c0e12a4b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("ok_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "ok_url")
