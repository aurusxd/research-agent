"""add celery delivery tracking

Revision ID: 9d3c0e12a4b1
Revises: 75d30dfdb905
Create Date: 2026-07-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "9d3c0e12a4b1"
down_revision: str | Sequence[str] | None = "75d30dfdb905"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "sending_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "delivery_attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_contacts_celery_task_id",
        "contacts",
        ["celery_task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_contacts_celery_task_id", table_name="contacts")
    op.drop_column("contacts", "delivery_attempts")
    op.drop_column("contacts", "sending_started_at")
    op.drop_column("contacts", "celery_task_id")
