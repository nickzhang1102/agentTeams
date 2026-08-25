"""rename oncopath tables to agent teams naming

开源前整改：移除内部代号 OncoPath。
- 重命名 oncopath_launches / oncopath_embed_tokens 两表为
  agent_teams_launches / agent_teams_embed_tokens；
- 同步重命名两表的索引与唯一约束（PostgreSQL 的 RENAME TABLE
  不会级联重命名索引/约束）；
- 对齐 integration_client_key 列的 server_default 与存量数据值
  （'oncopath' -> 'agentteams'）；
- 同步 decision_runs.source 的 CHECK 约束取值与存量数据，
  否则新代码写入 'agentteams' 会违反从零升级链路建出的旧 CHECK；
- 同步 integration_clients 兼容客户端标识、system_configs 配置键
  与服务账户用户名的存量数据值。

Revision ID: a8b9c0d1e2f3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


# revision identifiers, used by Alembic.
revision = 'a8b9c0d1e2f3'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


# 索引重命名清单：(旧名, 新名)
_INDEX_RENAMES = (
    # agent_teams_launches（原 oncopath_launches）
    ('ix_oncopath_launches_agentteams_conversation_id', 'ix_agent_teams_launches_agentteams_conversation_id'),
    ('ix_oncopath_launches_agentteams_leader_session_id', 'ix_agent_teams_launches_agentteams_leader_session_id'),
    ('ix_oncopath_launches_status', 'ix_agent_teams_launches_status'),
    ('idx_oncopath_launch_source_conversation', 'idx_agent_teams_launch_source_conversation'),
    ('ix_oncopath_launches_lease_expires_at', 'ix_agent_teams_launches_lease_expires_at'),
    ('ix_oncopath_launches_integration_client_key', 'ix_agent_teams_launches_integration_client_key'),
    # agent_teams_embed_tokens（原 oncopath_embed_tokens）
    ('ix_oncopath_embed_tokens_conversation_id', 'ix_agent_teams_embed_tokens_conversation_id'),
    ('ix_oncopath_embed_tokens_expires_at', 'ix_agent_teams_embed_tokens_expires_at'),
    ('ix_oncopath_embed_tokens_leader_session_id', 'ix_agent_teams_embed_tokens_leader_session_id'),
    ('ix_oncopath_embed_tokens_source', 'ix_agent_teams_embed_tokens_source'),
    ('ix_oncopath_embed_tokens_token_hash', 'ix_agent_teams_embed_tokens_token_hash'),
    ('ix_oncopath_embed_tokens_integration_client_key', 'ix_agent_teams_embed_tokens_integration_client_key'),
)

# SystemConfig 配置键重命名清单：(旧键, 新键)
_SYSTEM_CONFIG_KEY_RENAMES = (
    ('ONCOPATH_INTEGRATION_ENABLED', 'AGENTTEAMS_INTEGRATION_ENABLED'),
    ('ONCOPATH_INTEGRATION_KEY', 'AGENTTEAMS_INTEGRATION_KEY'),
    ('ONCOPATH_EMBED_TOKEN_TTL_SECONDS', 'AGENTTEAMS_EMBED_TOKEN_TTL_SECONDS'),
    ('ONCOPATH_SERVICE_ACCOUNT_USERNAME', 'AGENTTEAMS_SERVICE_ACCOUNT_USERNAME'),
)


def _rename_indexes(safe_op, direction: str) -> None:
    for old_name, new_name in _INDEX_RENAMES:
        src, dst = (old_name, new_name) if direction == 'up' else (new_name, old_name)
        if safe_op.has_index(_table_for_index(src), src):
            op.execute(f'ALTER INDEX {src} RENAME TO {dst}')


def _table_for_index(index_name: str) -> str:
    return 'agent_teams_embed_tokens' if '_embed_tokens_' in index_name else 'agent_teams_launches'


def upgrade():
    safe_op = SafeOperations(op)

    # 1. 表重命名（外键引用由 PostgreSQL 自动跟随）
    op.rename_table('oncopath_launches', 'agent_teams_launches')
    op.rename_table('oncopath_embed_tokens', 'agent_teams_embed_tokens')

    # 2. 唯一约束与索引重命名（RENAME TABLE 不级联改名）
    op.execute(
        'ALTER TABLE agent_teams_launches '
        'RENAME CONSTRAINT uq_oncopath_launch_source_client_request '
        'TO uq_agent_teams_launch_source_client_request'
    )
    _rename_indexes(safe_op, 'up')

    # 3. server_default 对齐模型声明（'oncopath' -> 'agentteams'）
    op.alter_column(
        'agent_teams_launches', 'integration_client_key',
        existing_type=sa.String(length=50), server_default='agentteams',
    )
    op.alter_column(
        'agent_teams_embed_tokens', 'integration_client_key',
        existing_type=sa.String(length=50), server_default='agentteams',
    )

    # 4. 存量数据值对齐（decision_runs 需先摘除旧 CHECK 才能改写 source）
    op.drop_constraint('ck_decision_runs_source', 'decision_runs', type_='check')
    op.execute("UPDATE agent_teams_launches SET source = 'agentteams' WHERE source = 'oncopath'")
    op.execute("UPDATE agent_teams_launches SET integration_client_key = 'agentteams' WHERE integration_client_key = 'oncopath'")
    op.execute("UPDATE agent_teams_embed_tokens SET source = 'agentteams' WHERE source = 'oncopath'")
    op.execute("UPDATE agent_teams_embed_tokens SET integration_client_key = 'agentteams' WHERE integration_client_key = 'oncopath'")
    op.execute("UPDATE decision_runs SET source = 'agentteams' WHERE source = 'oncopath'")
    op.execute("UPDATE integration_clients SET client_key = 'agentteams' WHERE client_key = 'oncopath'")
    op.execute("UPDATE integration_clients SET adapter_key = 'agentteams' WHERE adapter_key = 'oncopath'")
    op.execute("UPDATE users SET username = 'agentteams-service' WHERE username = 'oncopath-service'")
    for old_key, new_key in _SYSTEM_CONFIG_KEY_RENAMES:
        op.execute(
            f"UPDATE system_configs SET key = '{new_key}' WHERE key = '{old_key}'"
        )
    op.execute(
        "UPDATE system_configs SET description = REPLACE(description, 'OncoPath', 'Agent Teams') "
        "WHERE description LIKE '%OncoPath%'"
    )

    # 5. 以新取值集重建 decision_runs.source 的 CHECK
    op.create_check_constraint(
        'ck_decision_runs_source',
        'decision_runs',
        "source IN ('web', 'agentteams', 'api')",
    )


def downgrade():
    safe_op = SafeOperations(op)

    # 1. 还原 decision_runs 的 CHECK 与存量数据值
    #    （先摘除新 CHECK、回写数据，再以旧取值集重建）
    op.drop_constraint('ck_decision_runs_source', 'decision_runs', type_='check')
    op.execute("UPDATE decision_runs SET source = 'oncopath' WHERE source = 'agentteams'")
    op.execute("UPDATE agent_teams_launches SET source = 'oncopath' WHERE source = 'agentteams'")
    op.execute("UPDATE agent_teams_launches SET integration_client_key = 'oncopath' WHERE integration_client_key = 'agentteams'")
    op.execute("UPDATE agent_teams_embed_tokens SET source = 'oncopath' WHERE source = 'agentteams'")
    op.execute("UPDATE agent_teams_embed_tokens SET integration_client_key = 'oncopath' WHERE integration_client_key = 'agentteams'")
    op.execute("UPDATE integration_clients SET client_key = 'oncopath' WHERE client_key = 'agentteams'")
    op.execute("UPDATE integration_clients SET adapter_key = 'oncopath' WHERE adapter_key = 'agentteams'")
    op.execute("UPDATE users SET username = 'oncopath-service' WHERE username = 'agentteams-service'")
    for old_key, new_key in _SYSTEM_CONFIG_KEY_RENAMES:
        op.execute(
            f"UPDATE system_configs SET key = '{old_key}' WHERE key = '{new_key}'"
        )
    op.execute(
        "UPDATE system_configs SET description = REPLACE(description, 'Agent Teams', 'OncoPath') "
        "WHERE description LIKE '%Agent Teams%'"
    )
    # 以旧取值集重建 decision_runs.source 的 CHECK
    op.create_check_constraint(
        'ck_decision_runs_source',
        'decision_runs',
        "source IN ('web', 'oncopath', 'api')",
    )

    # 2. server_default 还原
    op.alter_column(
        'agent_teams_launches', 'integration_client_key',
        existing_type=sa.String(length=50), server_default='oncopath',
    )
    op.alter_column(
        'agent_teams_embed_tokens', 'integration_client_key',
        existing_type=sa.String(length=50), server_default='oncopath',
    )

    # 3. 索引与唯一约束名还原
    op.execute(
        'ALTER TABLE agent_teams_launches '
        'RENAME CONSTRAINT uq_agent_teams_launch_source_client_request '
        'TO uq_oncopath_launch_source_client_request'
    )
    _rename_indexes(safe_op, 'down')

    # 4. 表名还原
    op.rename_table('agent_teams_launches', 'oncopath_launches')
    op.rename_table('agent_teams_embed_tokens', 'oncopath_embed_tokens')
