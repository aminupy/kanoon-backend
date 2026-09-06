"""add durable archive markers for boolean-active content

Revision ID: c6e4a12b7f90
Revises: 8f3a2d6b9c10
Create Date: 2026-09-04 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6e4a12b7f90"
down_revision: str | Sequence[str] | None = "8f3a2d6b9c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "honor_categories",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "staff_members",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("staff_members", "archived_at")
    op.drop_column("honor_categories", "archived_at")
