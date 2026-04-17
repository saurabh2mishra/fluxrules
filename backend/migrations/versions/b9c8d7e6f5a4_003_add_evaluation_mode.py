"""003_add_evaluation_mode

Add nullable evaluation_mode column to rules with stateless default.

Revision ID: b9c8d7e6f5a4
Revises: a3b4c5d6e7f8
Create Date: 2026-04-17 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b9c8d7e6f5a4"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add evaluation_mode to rules."""
    op.add_column(
        "rules",
        sa.Column("evaluation_mode", sa.String(), nullable=True, server_default="stateless"),
    )


def downgrade() -> None:
    """Drop evaluation_mode from rules."""
    op.drop_column("rules", "evaluation_mode")
