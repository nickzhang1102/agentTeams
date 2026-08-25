"""add OncoPath launch leases

Revision ID: f2b3c4d5e6a7
Revises: e7f8a9b0c1d2
Create Date: 2026-07-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


revision = 'f2b3c4d5e6a7'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    safe = SafeOperations(op)
    safe.add_column('oncopath_launches', sa.Column('lease_owner', sa.String(length=64), nullable=True))
    safe.add_column('oncopath_launches', sa.Column('lease_expires_at', sa.DateTime(), nullable=True))
    safe.add_column('oncopath_launches', sa.Column('heartbeat_at', sa.DateTime(), nullable=True))
    safe.add_column(
        'oncopath_launches',
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
    )
    safe.create_index(
        'ix_oncopath_launches_lease_expires_at',
        'oncopath_launches',
        ['lease_expires_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_oncopath_launches_lease_expires_at', table_name='oncopath_launches')
    op.drop_column('oncopath_launches', 'attempt_count')
    op.drop_column('oncopath_launches', 'heartbeat_at')
    op.drop_column('oncopath_launches', 'lease_expires_at')
    op.drop_column('oncopath_launches', 'lease_owner')
