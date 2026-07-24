"""add search query plan

Revision ID: 75d30dfdb905
Revises: 43ef2034d24a
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "75d30dfdb905"
down_revision: str | Sequence[str] | None = "43ef2034d24a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_runs",
        sa.Column(
            "search_queries",
            sa.JSON(),
            server_default="[]",
            nullable=False,
        ),
    )
    op.add_column(
        "search_runs",
        sa.Column(
            "search_queries_limit",
            sa.Integer(),
            server_default="8",
            nullable=False,
        ),
    )
    op.add_column(
        "search_runs",
        sa.Column(
            "raw_result_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "search_runs",
        sa.Column(
            "executed_query_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("search_runs", "executed_query_count")
    op.drop_column("search_runs", "raw_result_count")
    op.drop_column("search_runs", "search_queries_limit")
    op.drop_column("search_runs", "search_queries")
