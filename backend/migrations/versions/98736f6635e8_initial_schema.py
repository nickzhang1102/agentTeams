"""initial schema

Revision ID: 98736f6635e8
Revises:
Create Date: 2026-06-03 11:12:00.944444

"""
from alembic import op
import sqlalchemy as sa

from migrations.safe_ops import SafeOperations


# revision identifiers, used by Alembic.
revision = '98736f6635e8'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    safe_op = SafeOperations(op)
    # === 用户与权限 ===
    safe_op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(50), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('email', sa.String(100), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('lockout_reason', sa.String(255), nullable=True),
    )
    safe_op.create_index('ix_users_username', 'users', ['username'], unique=True)
    safe_op.create_index('ix_users_email', 'users', ['email'], unique=True)
    safe_op.create_index('ix_users_is_admin', 'users', ['is_admin'], unique=False)

    # === 对话管理 ===
    safe_op.create_table('conversations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('is_archived', sa.Boolean(), server_default='false'),
        sa.Column('is_review_mode', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('share_token', sa.String(20), nullable=True),
        sa.Column('category', sa.String(20), server_default='other'),
        sa.Column('status', sa.String(20), server_default='new'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    safe_op.create_index('ix_conversations_user_id', 'conversations', ['user_id'], unique=False)
    safe_op.create_index('ix_conversations_is_archived', 'conversations', ['is_archived'], unique=False)
    safe_op.create_index('ix_conversations_share_token', 'conversations', ['share_token'], unique=True)
    safe_op.create_index('ix_conversations_category', 'conversations', ['category'], unique=False)
    safe_op.create_index('ix_conversations_status', 'conversations', ['status'], unique=False)

    # === 文件管理 ===
    safe_op.create_table('files',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_type', sa.String(100), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_files_conversation_id', 'files', ['conversation_id'], unique=False)
    safe_op.create_index('ix_files_message_id', 'files', ['message_id'], unique=False)
    safe_op.create_index('ix_files_user_id', 'files', ['user_id'], unique=False)

    # === Leader 会话 ===
    safe_op.create_table('leader_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('user_message', sa.Text(), nullable=False),
        sa.Column('state', sa.String(20), server_default='idle'),
        sa.Column('assessment_score', sa.Integer(), nullable=True),
        sa.Column('risk_level', sa.String(10), server_default='medium'),
        sa.Column('selected_agents', sa.String(500), nullable=True),
        sa.Column('started_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('total_tokens', sa.Integer(), server_default='0'),
        sa.Column('total_cost', sa.Numeric(10, 4), server_default='0.0'),
        sa.Column('stop_requested', sa.Boolean(), server_default='false'),
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    safe_op.create_index('ix_leader_sessions_conversation_id', 'leader_sessions', ['conversation_id'], unique=False)

    # === 消息 ===
    safe_op.create_table('messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=True),
        sa.Column('content', sa.JSON(), nullable=True),
        sa.Column('raw_content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('leader_session_id', sa.Integer(), sa.ForeignKey('leader_sessions.id', ondelete='CASCADE'), nullable=True),
        sa.Column('message_type', sa.String(20), server_default='normal'),
        sa.Column('is_review_mode', sa.Boolean(), server_default='false'),
        sa.Column('sequence_number', sa.Integer(), nullable=True),
    )
    safe_op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'], unique=False)
    safe_op.create_index('ix_messages_created_at', 'messages', ['created_at'], unique=False)
    safe_op.create_index('ix_messages_message_type', 'messages', ['message_type'], unique=False)
    safe_op.create_index('idx_leader_message_sequence', 'messages', ['leader_session_id', 'sequence_number'], unique=True, postgresql_where='leader_session_id IS NOT NULL')
    safe_op.create_index('idx_conversation_created', 'messages', ['conversation_id', 'created_at'], unique=False)

    # === Leader Agent 结果 ===
    safe_op.create_table('leader_agent_results',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('leader_session_id', sa.Integer(), sa.ForeignKey('leader_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('agent_id', sa.String(50), nullable=False),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('tokens_used', sa.Integer(), server_default='0'),
        sa.Column('execution_time', sa.Float(), server_default='0.0'),
        sa.Column('iterations', sa.Integer(), server_default='1'),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_leader_agent_results_conversation_id', 'leader_agent_results', ['conversation_id'], unique=False)
    safe_op.create_index('ix_leader_agent_results_leader_session_id', 'leader_agent_results', ['leader_session_id'], unique=False)
    safe_op.create_index('ix_leader_agent_results_agent_id', 'leader_agent_results', ['agent_id'], unique=False)
    safe_op.create_unique_constraint('unique_agent_result_sequence', 'leader_agent_results', ['leader_session_id', 'sequence_number'])
    safe_op.create_index('idx_agent_result_conversation_created', 'leader_agent_results', ['conversation_id', 'created_at'], unique=False)

    # === Leader 最终报告 ===
    safe_op.create_table('leader_final_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('leader_session_id', sa.Integer(), sa.ForeignKey('leader_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('report', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_leader_final_reports_conversation_id', 'leader_final_reports', ['conversation_id'], unique=False)
    safe_op.create_unique_constraint('uq_leader_final_report_session', 'leader_final_reports', ['leader_session_id'])
    safe_op.create_index('idx_final_report_conversation_created', 'leader_final_reports', ['conversation_id', 'created_at'], unique=False)

    # === 工具调用日志 ===
    safe_op.create_table('tool_call_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('leader_session_id', sa.Integer(), sa.ForeignKey('leader_sessions.id'), nullable=True),
        sa.Column('agent_id', sa.String(50), nullable=True),
        sa.Column('tool_name', sa.String(100), nullable=False),
        sa.Column('tool_input', sa.JSON(), server_default='{}'),
        sa.Column('tool_output', sa.JSON(), server_default='{}'),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('execution_time', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_tool_call_logs_conversation_id', 'tool_call_logs', ['conversation_id'], unique=False)
    safe_op.create_index('ix_tool_call_logs_leader_session_id', 'tool_call_logs', ['leader_session_id'], unique=False)
    safe_op.create_index('ix_tool_call_logs_agent_id', 'tool_call_logs', ['agent_id'], unique=False)
    safe_op.create_index('ix_tool_call_logs_tool_name', 'tool_call_logs', ['tool_name'], unique=False)
    safe_op.create_index('ix_tool_call_logs_created_at', 'tool_call_logs', ['created_at'], unique=False)

    # === Agent 配置 ===
    safe_op.create_table('agent_configs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('agent_id', sa.String(50), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_exists', sa.Boolean(), server_default='true'),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('priority', sa.Integer(), server_default='0'),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('model', sa.String(50), nullable=True),
        sa.Column('total_calls', sa.Integer(), server_default='0'),
        sa.Column('success_calls', sa.Integer(), server_default='0'),
        sa.Column('failed_calls', sa.Integer(), server_default='0'),
        sa.Column('total_tokens', sa.Integer(), server_default='0'),
        sa.Column('avg_execution_time', sa.Float(), server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    safe_op.create_index('ix_agent_configs_agent_id', 'agent_configs', ['agent_id'], unique=True)

    # === 性能指标 ===
    safe_op.create_table('performance_metrics',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('metric_type', sa.String(50), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('metric_unit', sa.String(20), nullable=True),
        sa.Column('extra_data', sa.JSON(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_performance_metrics_metric_type', 'performance_metrics', ['metric_type'], unique=False)
    safe_op.create_index('ix_performance_metrics_created_at', 'performance_metrics', ['created_at'], unique=False)

    # === 系统配置 ===
    safe_op.create_table('system_configs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    safe_op.create_index('ix_system_configs_key', 'system_configs', ['key'], unique=True)

    # === 用户余额 ===
    safe_op.create_table('user_balances',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('balance', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_purchased', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_gifted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    safe_op.create_index('ix_user_balances_user_id', 'user_balances', ['user_id'], unique=True)

    # === CDKey ===
    safe_op.create_table('cdkeys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('card_type', sa.String(20), nullable=False),
        sa.Column('times', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(10, 2), nullable=False),
        sa.Column('status', sa.String(20), server_default='unused'),
        sa.Column('used_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('batch_no', sa.String(50), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_cdkeys_code', 'cdkeys', ['code'], unique=True)
    safe_op.create_index('ix_cdkeys_status', 'cdkeys', ['status'], unique=False)
    safe_op.create_index('ix_cdkeys_used_by', 'cdkeys', ['used_by'], unique=False)
    safe_op.create_index('ix_cdkeys_batch_no', 'cdkeys', ['batch_no'], unique=False)

    # === 使用记录 ===
    safe_op.create_table('usage_records',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('leader_session_id', sa.Integer(), sa.ForeignKey('leader_sessions.id'), nullable=True),
        sa.Column('times_used', sa.Integer(), server_default='1'),
        sa.Column('tokens_used', sa.Integer(), server_default='0'),
        sa.Column('cost_estimate', sa.Numeric(10, 4), server_default='0.0'),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('refund_reason', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_usage_records_user_id', 'usage_records', ['user_id'], unique=False)
    safe_op.create_index('ix_usage_records_conversation_id', 'usage_records', ['conversation_id'], unique=False)
    safe_op.create_index('ix_usage_records_leader_session_id', 'usage_records', ['leader_session_id'], unique=False)
    safe_op.create_index('idx_usage_user_created', 'usage_records', ['user_id', 'created_at'], unique=False)
    safe_op.create_index('idx_usage_status', 'usage_records', ['status'], unique=False)

    # === 购买订单 ===
    safe_op.create_table('purchase_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('cdkey_id', sa.Integer(), sa.ForeignKey('cdkeys.id'), nullable=True),
        sa.Column('order_type', sa.String(20), server_default='cdkey'),
        sa.Column('amount', sa.Numeric(10, 2), server_default='0.0'),
        sa.Column('times', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(20), server_default='completed'),
        sa.Column('remark', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_purchase_orders_user_id', 'purchase_orders', ['user_id'], unique=False)
    safe_op.create_index('ix_purchase_orders_cdkey_id', 'purchase_orders', ['cdkey_id'], unique=False)

    # === CDKey 兑换尝试 ===
    safe_op.create_table('cdkey_redeem_attempts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('attempt_code', sa.String(20), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('error_message', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_cdkey_redeem_attempts_user_id', 'cdkey_redeem_attempts', ['user_id'], unique=False)
    safe_op.create_index('ix_cdkey_redeem_attempts_ip_address', 'cdkey_redeem_attempts', ['ip_address'], unique=False)
    safe_op.create_index('ix_cdkey_redeem_attempts_created_at', 'cdkey_redeem_attempts', ['created_at'], unique=False)
    safe_op.create_index('idx_redeem_attempt_user_created', 'cdkey_redeem_attempts', ['user_id', 'created_at'], unique=False)
    safe_op.create_index('idx_redeem_attempt_ip_created', 'cdkey_redeem_attempts', ['ip_address', 'created_at'], unique=False)

    # === 安全日志 ===
    safe_op.create_table('security_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_security_logs_user_id', 'security_logs', ['user_id'], unique=False)
    safe_op.create_index('ix_security_logs_action', 'security_logs', ['action'], unique=False)
    safe_op.create_index('ix_security_logs_ip_address', 'security_logs', ['ip_address'], unique=False)
    safe_op.create_index('ix_security_logs_created_at', 'security_logs', ['created_at'], unique=False)
    safe_op.create_index('idx_security_log_user_created', 'security_logs', ['user_id', 'created_at'], unique=False)

    # === Harness 会话映射 ===
    safe_op.create_table('harness_session_mappings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('leader_session_id', sa.Integer(), sa.ForeignKey('leader_sessions.id'), nullable=False),
        sa.Column('harness_session_id', sa.String(100), nullable=False),
        sa.Column('harness_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    safe_op.create_index('ix_harness_session_mappings_leader_session_id', 'harness_session_mappings', ['leader_session_id'], unique=False)
    safe_op.create_unique_constraint('uq_harness_session_id', 'harness_session_mappings', ['harness_session_id'])

    # === Agent MCP 权限 ===
    safe_op.create_table('agent_mcp_permissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('agent_id', sa.String(100), nullable=False),
        sa.Column('mcp_tool_pattern', sa.String(200), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    safe_op.create_index('ix_agent_mcp_permissions_agent_id', 'agent_mcp_permissions', ['agent_id'], unique=False)
    safe_op.create_unique_constraint('uq_agent_mcp_pattern', 'agent_mcp_permissions', ['agent_id', 'mcp_tool_pattern'])
    safe_op.create_index('idx_agent_mcp_enabled', 'agent_mcp_permissions', ['agent_id', 'enabled'], unique=False)

    # === Agent 优先级规则 ===
    safe_op.create_table('agent_priority_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('trigger_scene', sa.String(50), nullable=True),
        sa.Column('trigger_risk_level', sa.String(10), nullable=True),
        sa.Column('trigger_category', sa.String(50), nullable=True),
        sa.Column('agent_id', sa.String(100), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('rule_priority', sa.Integer(), server_default='0'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    safe_op.create_index('idx_trigger_conditions', 'agent_priority_rules', ['trigger_scene', 'trigger_risk_level', 'trigger_category'], unique=False)
    safe_op.create_index('idx_agent_id', 'agent_priority_rules', ['agent_id'], unique=False)
    safe_op.create_index('idx_rule_priority_active', 'agent_priority_rules', ['rule_priority', 'is_active'], unique=False)

    # === 知识库文档 ===
    safe_op.create_table('knowledge_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('original_path', sa.String(500), nullable=True),
        sa.Column('markdown_path', sa.String(500), nullable=True),
        sa.Column('category', sa.String(20), server_default='regulation'),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_type', sa.String(20), nullable=True),
        sa.Column('content_hash', sa.String(32), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('indexed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pending'),
        sa.Column('ocr_error', sa.Text(), nullable=True),
        sa.Column('ocr_processed_at', sa.DateTime(), nullable=True),
        sa.Column('graphify_error', sa.Text(), nullable=True),
        sa.Column('graphify_processed_at', sa.DateTime(), nullable=True),
        sa.Column('graph_nodes', sa.Integer(), nullable=True),
        sa.Column('graph_edges', sa.Integer(), nullable=True),
    )
    safe_op.create_index('ix_knowledge_documents_content_hash', 'knowledge_documents', ['content_hash'], unique=False)
    safe_op.create_index('idx_knowledge_category', 'knowledge_documents', ['category'], unique=False)
    safe_op.create_index('idx_knowledge_status', 'knowledge_documents', ['status'], unique=False)
    safe_op.create_index('idx_knowledge_uploaded_by', 'knowledge_documents', ['uploaded_by'], unique=False)

    # === 知识库分类 ===
    safe_op.create_table('knowledge_categories',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.String(20), nullable=False),
        sa.Column('label', sa.String(50), nullable=False),
        sa.Column('description', sa.String(200), nullable=True),
        sa.Column('icon', sa.String(50), server_default='Document'),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    safe_op.create_unique_constraint('uq_knowledge_category_key', 'knowledge_categories', ['key'])
    safe_op.create_index('idx_knowledge_category_sort', 'knowledge_categories', ['sort_order'], unique=False)
    safe_op.create_index('idx_knowledge_category_active', 'knowledge_categories', ['is_active'], unique=False)


def downgrade():
    # Drop all tables in reverse order
    op.drop_table('knowledge_categories')
    op.drop_table('knowledge_documents')
    op.drop_table('agent_priority_rules')
    op.drop_table('agent_mcp_permissions')
    op.drop_table('harness_session_mappings')
    op.drop_table('security_logs')
    op.drop_table('cdkey_redeem_attempts')
    op.drop_table('purchase_orders')
    op.drop_table('usage_records')
    op.drop_table('cdkeys')
    op.drop_table('user_balances')
    op.drop_table('system_configs')
    op.drop_table('performance_metrics')
    op.drop_table('agent_configs')
    op.drop_table('tool_call_logs')
    op.drop_table('leader_final_reports')
    op.drop_table('leader_agent_results')
    op.drop_table('messages')
    op.drop_table('leader_sessions')
    op.drop_table('files')
    op.drop_table('conversations')
    op.drop_table('users')