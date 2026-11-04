"""Keep comparison issues in saved evaluation results.

Adds ``evaluation_results.comparison_issues``, the JSON list of comparisons
that could not be made (``EvaluationResult.comparison_issues``), so
``explain()`` after a restart still has them.

``evaluation_results`` was created by ``Base.metadata.create_all`` rather than
by a migration, so a database may or may not have it. This migration brings
the table under Alembic: it creates the table when it is missing, and
otherwise adds the column, keeping every saved row (their issues are ``[]``).

Revision ID: 003_comparison_issues
Revises: 002_rename_conditions
Create Date: 2026-11-04

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_comparison_issues"
down_revision: Union[str, None] = "002_rename_conditions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("evaluation_results"):
        op.create_table(
            "evaluation_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("execution_id", sa.String(), nullable=False),
            sa.Column("ruleset_id", sa.String(), nullable=True),
            sa.Column("fired_rules", sa.Text(), nullable=False),
            sa.Column("actions", sa.Text(), nullable=False),
            sa.Column("trace", sa.Text(), nullable=False),
            sa.Column("comparison_issues", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "ix_evaluation_results_execution_id",
            "evaluation_results",
            ["execution_id"],
            unique=True,
        )
        return
    columns = {column["name"] for column in inspector.get_columns("evaluation_results")}
    if "comparison_issues" not in columns:
        with op.batch_alter_table("evaluation_results") as batch_op:
            batch_op.add_column(
                sa.Column("comparison_issues", sa.Text(), nullable=False, server_default="[]")
            )


def downgrade() -> None:
    # The table is Alembic's from this migration on, so going below it drops
    # the table, as downgrading 001 drops the tables 001 created.
    op.drop_index("ix_evaluation_results_execution_id", table_name="evaluation_results")
    op.drop_table("evaluation_results")
