"""add_featured_fields_to_conversation

Revision ID: d48a6f9187c2
Revises: 0d15800c46b1
Create Date: 2026-06-16 16:34:09.566442

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations

# revision identifiers, used by Alembic.
revision = 'd48a6f9187c2'
down_revision = '0d15800c46b1'
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    # Add columns as nullable first
    safe_op.add_column('conversations', sa.Column('is_featured', sa.Boolean(), nullable=True))
    safe_op.add_column('conversations', sa.Column('featured_order', sa.Integer(), nullable=True))

    # Set default values for existing rows
    op.execute("UPDATE conversations SET is_featured = FALSE WHERE is_featured IS NULL")
    op.execute("UPDATE conversations SET featured_order = 0 WHERE featured_order IS NULL")

    # Now alter columns to NOT NULL
    op.alter_column('conversations', 'is_featured', nullable=False, server_default=sa.text('FALSE'))
    op.alter_column('conversations', 'featured_order', nullable=False, server_default=sa.text('0'))

    # Create index
    safe_op.create_index(op.f('ix_conversations_is_featured'), 'conversations', ['is_featured'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_conversations_is_featured'), table_name='conversations')
    op.drop_column('conversations', 'featured_order')
    op.drop_column('conversations', 'is_featured')
