"""001_initial_schema_with_audit_integrity

Add audit integrity hash column for HMAC-SHA256 tamper detection.
Add schema_meta tracking table for migration history.

Revision ID: 977895da9fbe
Revises:
Create Date: 2026-03-26 12:55:48.570243
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '977895da9fbe'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add integrity_hash to audit_logs and create schema_meta table."""
    # 1. Add integrity_hash column for HMAC-SHA256 tamper detection
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('integrity_hash', sa.String(length=64), nullable=True)
        )

    # 2. Create schema_meta table for migration version history
    op.create_table(
        'schema_meta',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('applied_at', sa.DateTime(), nullable=True),
        sa.Column('description', sa.String(), server_default='', nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Remove integrity_hash from audit_logs and drop schema_meta."""
    op.drop_table('schema_meta')

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_column('integrity_hash')
