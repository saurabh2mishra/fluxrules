"""002_add_audit_policies_and_reports

Create audit_policies and audit_reports tables for scheduled full-audit
runs and production reporting.

Backward compatible: additive-only — no existing tables are modified.

Revision ID: a3b4c5d6e7f8
Revises: 977895da9fbe
Create Date: 2026-03-26 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "977895da9fbe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit_policies and audit_reports tables."""
    op.create_table(
        "audit_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cron_expression", sa.String(), nullable=False, server_default="0 2 * * *"),
        sa.Column("scope", sa.String(), nullable=False, server_default="all"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_policies_id", "audit_policies", ["id"])
    op.create_index("ix_audit_policies_name", "audit_policies", ["name"], unique=True)

    op.create_table(
        "audit_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="passed"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("integrity_violations", sa.Integer(), server_default=sa.text("0")),
        sa.Column("retention_purged", sa.Integer(), server_default=sa.text("0")),
        sa.Column("coverage_pct", sa.Float(), server_default=sa.text("0.0")),
        sa.Column("rules_checked", sa.Integer(), server_default=sa.text("0")),
        sa.Column("duration_seconds", sa.Float(), server_default=sa.text("0.0")),
        sa.Column("integrity_hash", sa.String(length=64), nullable=True),
        sa.Column("triggered_by", sa.String(), nullable=False, server_default="schedule"),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["policy_id"], ["audit_policies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_reports_id", "audit_reports", ["id"])
    op.create_index("ix_audit_reports_policy_id", "audit_reports", ["policy_id"])
    op.create_index("ix_audit_reports_executed_at", "audit_reports", ["executed_at"])


def downgrade() -> None:
    """Drop audit_reports and audit_policies tables."""
    op.drop_index("ix_audit_reports_executed_at", table_name="audit_reports")
    op.drop_index("ix_audit_reports_policy_id", table_name="audit_reports")
    op.drop_index("ix_audit_reports_id", table_name="audit_reports")
    op.drop_table("audit_reports")

    op.drop_index("ix_audit_policies_name", table_name="audit_policies")
    op.drop_index("ix_audit_policies_id", table_name="audit_policies")
    op.drop_table("audit_policies")
