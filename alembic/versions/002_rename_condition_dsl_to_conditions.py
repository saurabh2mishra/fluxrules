"""Rename condition_dsl column to conditions.

Revision ID: 002_rename_conditions
Revises: 001_initial
Create Date: 2026-10-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_rename_conditions"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("rules") as batch_op:
        batch_op.alter_column("condition_dsl", new_column_name="conditions")

    with op.batch_alter_table("rule_versions") as batch_op:
        batch_op.alter_column("condition_dsl", new_column_name="conditions")

    with op.batch_alter_table("conflicted_rules") as batch_op:
        batch_op.alter_column("condition_dsl", new_column_name="conditions")


def downgrade() -> None:
    with op.batch_alter_table("conflicted_rules") as batch_op:
        batch_op.alter_column("conditions", new_column_name="condition_dsl")

    with op.batch_alter_table("rule_versions") as batch_op:
        batch_op.alter_column("conditions", new_column_name="condition_dsl")

    with op.batch_alter_table("rules") as batch_op:
        batch_op.alter_column("conditions", new_column_name="condition_dsl")
