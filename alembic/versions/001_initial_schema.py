"""Initial schema with rules, users, audit.

Revision ID: 001_initial
Revises: None
Create Date: 2026-05-06

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("email", sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime()),
    )

    # --- rules ---
    op.create_table(
        "rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False, index=True),
        sa.Column("description", sa.Text()),
        sa.Column("group", sa.String(), index=True),
        sa.Column("priority", sa.Integer(), server_default="0"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("condition_dsl", sa.Text()),
        sa.Column("action", sa.String()),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_rules_group_priority", "rules", ["group", "priority"])
    op.create_index("ix_rules_enabled_group", "rules", ["enabled", "group"])

    # --- rule_versions ---
    op.create_table(
        "rule_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("rules.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String()),
        sa.Column("description", sa.Text()),
        sa.Column("group", sa.String()),
        sa.Column("priority", sa.Integer()),
        sa.Column("enabled", sa.Boolean()),
        sa.Column("condition_dsl", sa.Text()),
        sa.Column("action", sa.String()),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("details", sa.Text()),
        sa.Column("execution_time", sa.Float()),
        sa.Column("timestamp", sa.DateTime(), index=True),
        sa.Column("integrity_hash", sa.String(64)),
    )

    # --- audit_policies ---
    op.create_table(
        "audit_policies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("cron_expression", sa.String(), nullable=False, server_default="0 2 * * *"),
        sa.Column("scope", sa.String(), nullable=False, server_default="all"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("last_run_at", sa.DateTime()),
        sa.Column("next_run_at", sa.DateTime()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )

    # --- audit_reports ---
    op.create_table(
        "audit_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_id", sa.Integer(), sa.ForeignKey("audit_policies.id")),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="passed"),
        sa.Column("summary", sa.Text()),
        sa.Column("details_json", sa.Text()),
        sa.Column("integrity_violations", sa.Integer(), server_default="0"),
        sa.Column("retention_purged", sa.Integer(), server_default="0"),
        sa.Column("coverage_pct", sa.Float(), server_default="0.0"),
        sa.Column("rules_checked", sa.Integer(), server_default="0"),
        sa.Column("duration_seconds", sa.Float(), server_default="0.0"),
        sa.Column("integrity_hash", sa.String(64)),
        sa.Column("triggered_by", sa.String(), nullable=False, server_default="schedule"),
        sa.Column("executed_at", sa.DateTime(), index=True),
    )

    # --- conflicted_rules ---
    op.create_table(
        "conflicted_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_a_id", sa.Integer(), sa.ForeignKey("rules.id")),
        sa.Column("rule_b_id", sa.Integer(), sa.ForeignKey("rules.id")),
        sa.Column("conflict_type", sa.String()),
        sa.Column("details", sa.Text()),
        sa.Column("detected_at", sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table("conflicted_rules")
    op.drop_table("audit_reports")
    op.drop_table("audit_policies")
    op.drop_table("audit_logs")
    op.drop_table("rule_versions")
    op.drop_index("ix_rules_enabled_group", table_name="rules")
    op.drop_index("ix_rules_group_priority", table_name="rules")
    op.drop_table("rules")
    op.drop_table("users")
