"""add search runs

Revision ID: c3d9a29f40b2
Revises: b92d7f30e4a1
Create Date: 2026-07-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3d9a29f40b2"
down_revision: str | Sequence[str] | None = "b92d7f30e4a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("excluded_keywords", sa.JSON(), nullable=False),
        sa.Column("requested_limit", sa.Integer(), nullable=False),
        sa.Column("min_relevance_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("found_count", sa.Integer(), nullable=False),
        sa.Column("saved_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("agent_result", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_search_runs_status"),
        "search_runs",
        ["status"],
        unique=False,
    )
    op.add_column(
        "contacts",
        sa.Column("search_run_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_contacts_search_run_id"),
        "contacts",
        ["search_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_contacts_search_run_id_search_runs",
        "contacts",
        "search_runs",
        ["search_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_contacts_search_run_id_search_runs",
        "contacts",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_contacts_search_run_id"),
        table_name="contacts",
    )
    op.drop_column("contacts", "search_run_id")
    op.drop_index(
        op.f("ix_search_runs_status"),
        table_name="search_runs",
    )
    op.drop_table("search_runs")
