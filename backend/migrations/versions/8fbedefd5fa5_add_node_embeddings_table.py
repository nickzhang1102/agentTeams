"""add node_embeddings table for graphrag semantic search

Revision ID: 8fbedefd5fa5
Revises: 2ba1c3410b4a
Create Date: 2026-06-20

"""
from alembic import op
import sqlalchemy as sa
from migrations.safe_ops import SafeOperations

# revision identifiers, used by Alembic.
revision = '8fbedefd5fa5'
down_revision = '2ba1c3410b4a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    safe_op = SafeOperations(op)
    # 启用 pgvector 扩展（幂等，Docker 环境已由 init-db.sql 创建）
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # 创建 node_embeddings 表
    safe_op.create_table(
        'node_embeddings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('node_id', sa.String(255), nullable=False),
        sa.Column('label', sa.String(500), nullable=False),
        sa.Column('graph_version', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'node_id', name='uq_node_embedding_user_node'),
    )

    # 添加 VECTOR 列（使用原生 SQL，Alembic 不识别 pgvector 类型）
    if not safe_op.has_column('node_embeddings', 'embedding'):
        op.execute('ALTER TABLE node_embeddings ADD COLUMN embedding vector(1024)')

    # 创建普通索引
    safe_op.create_index('idx_node_embedding_user', 'node_embeddings', ['user_id'])

    # 创建 HNSW 向量索引（cosine 距离）
    if not safe_op.has_index('node_embeddings', 'idx_node_embedding_hnsw'):
        op.execute(
            'CREATE INDEX idx_node_embedding_hnsw ON node_embeddings '
            'USING hnsw (embedding vector_cosine_ops) '
            'WITH (m = 16, ef_construction = 64)'
        )


def downgrade() -> None:
    op.drop_table('node_embeddings')
    # 注意：不删除 vector 扩展，可能被其他功能使用
