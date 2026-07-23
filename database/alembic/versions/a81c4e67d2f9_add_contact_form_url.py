"""add contact form URL

Revision ID: a81c4e67d2f9
Revises: fce3847f9ced
Create Date: 2026-07-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a81c4e67d2f9"
down_revision: str | Sequence[str] | None = "fce3847f9ced"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("contact_form_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "contact_form_url")
