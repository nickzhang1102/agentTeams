"""Admin 监控与设置 API 测试（FastAPI TestClient）

测试管理员性能监控、工具调试、系统设置功能：
- 性能概览统计
- Token 消耗趋势
- Agent 执行排名
- 工具调用日志列表与详情
- 工具使用统计
- 系统设置查询与更新
- 权限控制

迁移自 Flask test_client，使用 conftest 提供的 fixture。
"""
import pytest
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    User, Conversation, AgentConfig, ToolCallLog,
    SystemConfig, LeaderAgentResult, LeaderSession, Message
)
from db import Base
from sqlalchemy import text


# ==================== 测试数据 fixture ====================

@pytest.fixture
def sample_monitoring_data(client, admin_auth_header):
    """创建测试用监控数据（通过独立 Session）"""
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username='adminuser').first()
        assert user is not None, "adminuser 应已被 conftest 创建"

        # 创建对话和 LeaderSession
        conv = Conversation(user_id=user.id, title='测试对话')
        session.add(conv)
        session.flush()

        leader_session = LeaderSession(
            conversation_id=conv.id,
            user_message='测试消息',
            state='completed'
        )
        session.add(leader_session)
        session.flush()

        # 创建 LeaderAgentResult（含 tokens_used）
        now = datetime.now(timezone.utc)
        result1 = LeaderAgentResult(
            conversation_id=conv.id,
            leader_session_id=leader_session.id,
            agent_id='cardiology-expert',
            agent_name='心血管内科专家',
            status='success',
            content='结果1',
            tokens_used=5000,
            execution_time=2.5,
            sequence_number=1,
            created_at=now - timedelta(days=2)
        )
        result2 = LeaderAgentResult(
            conversation_id=conv.id,
            leader_session_id=leader_session.id,
            agent_id='respiratory-expert',
            agent_name='呼吸内科专家',
            status='success',
            content='结果2',
            tokens_used=3000,
            execution_time=1.8,
            sequence_number=2,
            created_at=now - timedelta(days=1)
        )
        session.add_all([result1, result2])

        team_config_message = Message.create_leader_message(
            conversation_id=conv.id,
            leader_session_id=leader_session.id,
            message_type='team_config',
            content={
                'mode': 'parallel',
                'agent_details': [
                    {
                        'agent_id': 'cardiology-expert',
                        'agent_name': '心血管内科专家',
                        'role_description': '先做心血管方向评估'
                    },
                    {
                        'agent_id': 'respiratory-expert',
                        'agent_name': '呼吸内科专家',
                        'role_description': '同步做呼吸方向评估'
                    }
                ],
                'dag_plan': {
                    'nodes': [
                        {
                            'id': 'agent_1',
                            'agent_id': 'cardiology-expert',
                            'agent_name': '心血管内科专家',
                            'role_description': '先做心血管方向评估',
                            'priority': 40
                        },
                        {
                            'id': 'agent_2',
                            'agent_id': 'respiratory-expert',
                            'agent_name': '呼吸内科专家',
                            'role_description': '同步做呼吸方向评估',
                            'priority': 40
                        }
                    ],
                    'execution_batches': [
                        {
                            'priority': 40,
                            'agents': ['cardiology-expert', 'respiratory-expert']
                        }
                    ]
                }
            },
            sequence_number=1
        )
        session.add(team_config_message)

        # 创建 AgentConfig
        agent1 = AgentConfig(
            agent_id='cardiology-expert',
            name='心血管内科专家',
            total_calls=100,
            success_calls=95,
            failed_calls=5,
            total_tokens=50000,
            avg_execution_time=2.5
        )
        agent2 = AgentConfig(
            agent_id='respiratory-expert',
            name='呼吸内科专家',
            total_calls=50,
            success_calls=45,
            failed_calls=5,
            total_tokens=30000,
            avg_execution_time=1.8
        )
        session.add_all([agent1, agent2])

        # 创建 ToolCallLog
        tool_log1 = ToolCallLog(
            conversation_id=conv.id,
            agent_id='cardiology-expert',
            tool_name='web_search',
            tool_input={'query': '心脏病诊断'},
            tool_output={'results': ['...']},
            status='success',
            execution_time=1.5,
            created_at=now - timedelta(hours=5)
        )
        tool_log2 = ToolCallLog(
            conversation_id=conv.id,
            agent_id='respiratory-expert',
            tool_name='file_read',
            tool_input={'path': '/tmp/test.txt'},
            tool_output={},
            status='failed',
            error_message='文件不存在',
            execution_time=0.5,
            created_at=now - timedelta(hours=3)
        )
        tool_log3 = ToolCallLog(
            conversation_id=conv.id,
            agent_id='cardiology-expert',
            tool_name='web_search',
            tool_input={'query': '高血压治疗'},
            tool_output={'results': ['...']},
            status='success',
            execution_time=2.0,
            created_at=now - timedelta(hours=1)
        )
        session.add_all([tool_log1, tool_log2, tool_log3])

        # 创建 SystemConfig
        config1 = SystemConfig(
            key='OPENHARNESS_ENABLED',
            value='true',
            description='是否启用OpenHarness工具生态'
        )
        config2 = SystemConfig(
            key='MAX_TOKENS_PER_REQUEST',
            value='4096',
            description='单次请求最大Token数'
        )
        session.add_all([config1, config2])
        session.commit()

        return {
            'conv_id': conv.id,
            'leader_session_id': leader_session.id
        }
    finally:
        session.close()


# ==================== 权限控制测试 ====================

def test_performance_overview_requires_admin(client, auth_header):
    """测试性能概览需要管理员权限"""
    response = client.get('/api/admin/performance/overview', headers=auth_header)
    assert response.status_code == 403


def test_performance_tokens_requires_admin(client, auth_header):
    """测试Token趋势需要管理员权限"""
    response = client.get('/api/admin/performance/tokens', headers=auth_header)
    assert response.status_code == 403


def test_performance_agents_requires_admin(client, auth_header):
    """测试Agent排名需要管理员权限"""
    response = client.get('/api/admin/performance/agents', headers=auth_header)
    assert response.status_code == 403


def test_tool_logs_requires_admin(client, auth_header):
    """测试工具日志需要管理员权限"""
    response = client.get('/api/admin/tools/logs', headers=auth_header)
    assert response.status_code == 403


def test_tool_stats_requires_admin(client, auth_header):
    """测试工具统计需要管理员权限"""
    response = client.get('/api/admin/tools/stats', headers=auth_header)
    assert response.status_code == 403


def test_settings_requires_admin(client, auth_header):
    """测试系统设置需要管理员权限"""
    response = client.get('/api/admin/settings', headers=auth_header)
    assert response.status_code == 403


# ==================== 性能概览测试 ====================

def test_performance_overview_success(client, admin_auth_header, sample_monitoring_data):
    """测试获取性能概览成功"""
    response = client.get('/api/admin/performance/overview', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    # 验证返回结构
    assert 'period' in data
    assert 'token_usage' in data
    assert 'cost' in data
    assert 'agent_execution' in data
    assert 'errors' in data

    # 验证 token_usage 结构
    assert 'total' in data['token_usage']
    assert 'daily_avg' in data['token_usage']
    assert 'trend' in data['token_usage']

    # 验证 cost 结构
    assert 'total' in data['cost']
    assert 'daily_avg' in data['cost']

    # 验证 agent_execution 结构
    assert 'total_calls' in data['agent_execution']
    assert 'avg_time' in data['agent_execution']
    assert 'success_rate' in data['agent_execution']

    # 验证 errors 结构
    assert 'total' in data['errors']
    assert 'rate' in data['errors']


def test_performance_overview_period(client, admin_auth_header, sample_monitoring_data):
    """测试不同时间范围的性能概览"""
    for period in ['day', 'week', 'month']:
        response = client.get(
            f'/api/admin/performance/overview?period={period}',
            headers=admin_auth_header
        )
        assert response.status_code == 200
        assert response.json()['period'] == period


def test_performance_overview_invalid_period(client, admin_auth_header, sample_monitoring_data):
    """测试无效时间范围默认回退为week"""
    response = client.get(
        '/api/admin/performance/overview?period=invalid',
        headers=admin_auth_header
    )
    assert response.status_code == 200
    assert response.json()['period'] == 'week'


def test_performance_overview_with_data(client, admin_auth_header, sample_monitoring_data):
    """测试有数据时的性能概览统计值"""
    response = client.get(
        '/api/admin/performance/overview?period=week',
        headers=admin_auth_header
    )
    assert response.status_code == 200
    data = response.json()

    # 有 2 个 LeaderAgentResult，分别 5000 和 3000 tokens
    assert data['token_usage']['total'] == 8000
    assert data['token_usage']['daily_avg'] > 0

    # Agent 统计：150 total_calls, 140 success_calls
    assert data['agent_execution']['total_calls'] == 150
    assert data['agent_execution']['success_rate'] > 0

    # 错误统计：1 failed 在 3 条 tool_call_logs 中
    assert data['errors']['total'] == 1


def test_leader_session_detail_includes_execution_plan(client, admin_auth_header, sample_monitoring_data):
    """测试 Leader 会话详情返回 team_config / dag_plan / 顺序化 agent_results"""
    session_id = sample_monitoring_data['leader_session_id']

    response = client.get(f'/api/admin/leader/sessions/{session_id}', headers=admin_auth_header)
    assert response.status_code == 200

    data = response.json()
    assert data['id'] == session_id
    assert data['team_config']['mode'] == 'parallel'
    assert len(data['team_config']['agent_details']) == 2
    assert len(data['dag_plan']['nodes']) == 2
    assert len(data['dag_plan']['execution_batches']) == 1
    assert data['dag_plan']['execution_batches'][0]['agents'] == [
        'cardiology-expert',
        'respiratory-expert'
    ]
    assert [item['agent_id'] for item in data['agent_results']] == [
        'cardiology-expert',
        'respiratory-expert'
    ]


# ==================== Token 趋势测试 ====================

def test_performance_tokens_success(client, admin_auth_header, sample_monitoring_data):
    """测试获取Token趋势成功"""
    response = client.get('/api/admin/performance/tokens', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    assert 'granularity' in data
    assert 'data' in data
    assert isinstance(data['data'], list)


def test_performance_tokens_day_granularity(client, admin_auth_header, sample_monitoring_data):
    """测试按天粒度获取Token趋势"""
    response = client.get(
        '/api/admin/performance/tokens?granularity=day',
        headers=admin_auth_header
    )
    assert response.status_code == 200
    data = response.json()
    assert data['granularity'] == 'day'

    # 应有数据
    if len(data['data']) > 0:
        entry = data['data'][0]
        assert 'date' in entry
        assert 'tokens' in entry
        assert 'cost' in entry


def test_performance_tokens_hour_granularity(client, admin_auth_header, sample_monitoring_data):
    """测试按小时粒度获取Token趋势"""
    response = client.get(
        '/api/admin/performance/tokens?granularity=hour',
        headers=admin_auth_header
    )
    assert response.status_code == 200
    data = response.json()
    assert data['granularity'] == 'hour'


def test_performance_tokens_date_range(client, admin_auth_header, sample_monitoring_data):
    """测试指定日期范围获取Token趋势"""
    now = datetime.now(timezone.utc)
    # 使用不带时区后缀的格式以兼容 fromisoformat
    start = (now - timedelta(days=5)).strftime('%Y-%m-%dT%H:%M:%S')
    end = now.strftime('%Y-%m-%dT%H:%M:%S')

    response = client.get(
        f'/api/admin/performance/tokens?start_date={start}&end_date={end}',
        headers=admin_auth_header
    )
    assert response.status_code == 200


def test_performance_tokens_invalid_date(client, admin_auth_header, sample_monitoring_data):
    """测试无效日期格式"""
    response = client.get(
        '/api/admin/performance/tokens?start_date=invalid-date',
        headers=admin_auth_header
    )
    assert response.status_code == 400


def test_performance_tokens_empty_data(client, admin_auth_header):
    """测试无数据时返回空数组"""
    response = client.get('/api/admin/performance/tokens', headers=admin_auth_header)
    assert response.status_code == 200
    assert response.json()['data'] == []


# ==================== Agent 执行排名测试 ====================

def test_performance_agents_success(client, admin_auth_header, sample_monitoring_data):
    """测试获取Agent执行排名成功"""
    response = client.get('/api/admin/performance/agents', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    assert 'agents' in data
    assert len(data['agents']) == 2

    # 验证按 total_calls 降序
    assert data['agents'][0]['total_calls'] >= data['agents'][1]['total_calls']

    # 验证字段
    agent = data['agents'][0]
    assert 'agent_id' in agent
    assert 'name' in agent
    assert 'total_calls' in agent
    assert 'success_rate' in agent
    assert 'avg_time' in agent
    assert 'total_tokens' in agent


def test_performance_agents_success_rate(client, admin_auth_header, sample_monitoring_data):
    """测试Agent成功率计算"""
    response = client.get('/api/admin/performance/agents', headers=admin_auth_header)
    assert response.status_code == 200
    agents = response.json()['agents']

    # cardiology-expert: 95/100 = 95.0%
    cardio = next(a for a in agents if a['agent_id'] == 'cardiology-expert')
    assert cardio['success_rate'] == 95.0

    # respiratory-expert: 45/50 = 90.0%
    respi = next(a for a in agents if a['agent_id'] == 'respiratory-expert')
    assert respi['success_rate'] == 90.0


# ==================== 工具调用日志测试 ====================

def test_tool_logs_success(client, admin_auth_header, sample_monitoring_data):
    """测试获取工具调用日志成功"""
    response = client.get('/api/admin/tools/logs', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    assert 'logs' in data
    assert 'total' in data
    assert 'page' in data
    assert 'per_page' in data
    assert data['total'] == 3


def test_tool_logs_filter_agent(client, admin_auth_header, sample_monitoring_data):
    """测试按Agent筛选工具日志"""
    response = client.get(
        '/api/admin/tools/logs?agent_id=cardiology-expert',
        headers=admin_auth_header
    )
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    for log in data['logs']:
        assert log['agent_id'] == 'cardiology-expert'


def test_tool_logs_filter_tool_name(client, admin_auth_header, sample_monitoring_data):
    """测试按工具名称筛选日志"""
    response = client.get(
        '/api/admin/tools/logs?tool_name=web_search',
        headers=admin_auth_header
    )
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    for log in data['logs']:
        assert log['tool_name'] == 'web_search'


def test_tool_logs_filter_status(client, admin_auth_header, sample_monitoring_data):
    """测试按状态筛选日志"""
    response = client.get(
        '/api/admin/tools/logs?status=failed',
        headers=admin_auth_header
    )
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1
    assert data['logs'][0]['status'] == 'failed'
    assert data['logs'][0]['error_message'] == '文件不存在'


def test_tool_logs_pagination(client, admin_auth_header, sample_monitoring_data):
    """测试工具日志分页"""
    response = client.get(
        '/api/admin/tools/logs?per_page=2&page=1',
        headers=admin_auth_header
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data['logs']) == 2

    response2 = client.get(
        '/api/admin/tools/logs?per_page=2&page=2',
        headers=admin_auth_header
    )
    assert response2.status_code == 200
    assert len(response2.json()['logs']) == 1


def test_tool_log_detail_success(client, admin_auth_header, sample_monitoring_data):
    """测试获取工具日志详情成功"""
    # 通过 API 获取第一条日志的 id
    response_list = client.get('/api/admin/tools/logs', headers=admin_auth_header)
    assert response_list.status_code == 200
    log_id = response_list.json()['logs'][0]['id']

    response = client.get(f'/api/admin/tools/logs/{log_id}', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    assert 'log' in data
    assert data['log']['id'] == log_id
    assert 'tool_name' in data['log']
    assert 'tool_input' in data['log']
    assert 'tool_output' in data['log']
    assert 'status' in data['log']
    assert 'execution_time' in data['log']


def test_tool_log_detail_not_found(client, admin_auth_header):
    """测试获取不存在的日志详情"""
    response = client.get('/api/admin/tools/logs/99999', headers=admin_auth_header)
    assert response.status_code == 404


# ==================== 工具使用统计测试 ====================

def test_tool_stats_success(client, admin_auth_header, sample_monitoring_data):
    """测试获取工具使用统计成功"""
    response = client.get('/api/admin/tools/stats', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    assert 'tool_stats' in data
    assert 'total_tools' in data
    assert 'total_calls' in data

    # 有 2 个工具（web_search 和 file_read）
    assert data['total_tools'] == 2
    assert data['total_calls'] == 3


def test_tool_stats_values(client, admin_auth_header, sample_monitoring_data):
    """测试工具统计值计算"""
    response = client.get('/api/admin/tools/stats', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    # 按调用数降序
    stats = data['tool_stats']
    assert len(stats) == 2

    # web_search: 2 calls, 2 success
    web_search = next(s for s in stats if s['tool_name'] == 'web_search')
    assert web_search['total_calls'] == 2
    assert web_search['success_rate'] == 1.0

    # file_read: 1 call, 0 success
    file_read = next(s for s in stats if s['tool_name'] == 'file_read')
    assert file_read['total_calls'] == 1
    assert file_read['success_rate'] == 0.0


def test_tool_stats_empty(client, admin_auth_header):
    """测试无数据时工具统计"""
    response = client.get('/api/admin/tools/stats', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()
    assert data['total_tools'] == 0
    assert data['total_calls'] == 0
    assert data['tool_stats'] == []


# ==================== 系统设置测试 ====================

def test_get_settings_success(client, admin_auth_header, sample_monitoring_data):
    """测试获取系统设置成功"""
    response = client.get('/api/admin/settings', headers=admin_auth_header)
    assert response.status_code == 200
    data = response.json()

    assert 'settings' in data
    assert len(data['settings']) == 2

    # 验证字段
    setting = data['settings'][0]
    assert 'id' in setting
    assert 'key' in setting
    assert 'value' in setting
    assert 'description' in setting


def test_get_settings_empty(client, admin_auth_header):
    """测试无设置数据时返回空列表"""
    response = client.get('/api/admin/settings', headers=admin_auth_header)
    assert response.status_code == 200
    assert response.json()['settings'] == []


def test_secret_settings_are_masked_and_legacy_llm_settings_are_hidden(client, admin_auth_header):
    from tests.conftest import TestSessionLocal

    session = TestSessionLocal()
    try:
        session.add_all([
            SystemConfig(key='EXA_API_KEY', value='exa-secret', description='Exa API Key'),
            SystemConfig(key='TAVILY_API_KEY', value='', description='Tavily API Key'),
            SystemConfig(key='LLM_API_KEY', value='legacy-llm-secret', description='Legacy LLM Key'),
        ])
        session.commit()
    finally:
        session.close()

    response = client.get('/api/admin/settings', headers=admin_auth_header)

    assert response.status_code == 200
    settings = {item['key']: item for item in response.json()['settings']}
    assert 'LLM_API_KEY' not in settings
    assert settings['EXA_API_KEY']['value'] == '********'
    assert settings['EXA_API_KEY']['is_secret'] is True
    assert settings['EXA_API_KEY']['is_configured'] is True
    assert settings['TAVILY_API_KEY']['value'] == ''
    assert settings['TAVILY_API_KEY']['is_configured'] is False
    assert 'exa-secret' not in response.text
    assert 'legacy-llm-secret' not in response.text


def test_empty_secret_update_preserves_value_and_ciphertext(client, admin_auth_header):
    from tests.conftest import TestSessionLocal

    session = TestSessionLocal()
    try:
        session.add(SystemConfig(key='EXA_API_KEY', value='exa-secret', description='Exa API Key'))
        session.commit()
        raw_before = session.execute(text(
            "SELECT value FROM system_configs WHERE key = 'EXA_API_KEY'"
        )).scalar_one()
    finally:
        session.close()

    response = client.put(
        '/api/admin/settings/EXA_API_KEY',
        headers=admin_auth_header,
        json={'value': ''},
    )

    assert response.status_code == 200
    assert response.json()['setting']['value'] == '********'
    session = TestSessionLocal()
    try:
        setting = session.query(SystemConfig).filter_by(key='EXA_API_KEY').one()
        raw_after = session.execute(text(
            "SELECT value FROM system_configs WHERE key = 'EXA_API_KEY'"
        )).scalar_one()
        assert setting.value == 'exa-secret'
        assert raw_after == raw_before
        assert 'exa-secret' not in raw_after
    finally:
        session.close()


def test_legacy_llm_setting_cannot_be_updated(client, admin_auth_header):
    from tests.conftest import TestSessionLocal

    session = TestSessionLocal()
    try:
        session.add(SystemConfig(key='LLM_API_KEY', value='legacy-key', description='Legacy LLM Key'))
        session.commit()
    finally:
        session.close()

    response = client.put(
        '/api/admin/settings/LLM_API_KEY',
        headers=admin_auth_header,
        json={'value': 'replacement'},
    )

    assert response.status_code == 400


def test_update_setting_success(client, admin_auth_header, sample_monitoring_data):
    """测试更新系统设置成功"""
    response = client.put('/api/admin/settings/OPENHARNESS_ENABLED',
        headers=admin_auth_header,
        json={'value': 'false'}
    )
    assert response.status_code == 200
    data = response.json()

    assert 'setting' in data
    assert data['setting']['key'] == 'OPENHARNESS_ENABLED'
    assert data['setting']['value'] == 'false'

    # 验证数据库更新
    from tests.conftest import TestSessionLocal
    session = TestSessionLocal()
    try:
        setting = session.query(SystemConfig).filter_by(key='OPENHARNESS_ENABLED').first()
        assert setting.value == 'false'
    finally:
        session.close()


def test_update_setting_not_found(client, admin_auth_header):
    """测试更新不存在的设置"""
    response = client.put('/api/admin/settings/NON_EXISTENT_KEY',
        headers=admin_auth_header,
        json={'value': 'test'}
    )
    assert response.status_code == 404


def test_update_setting_missing_value(client, admin_auth_header, sample_monitoring_data):
    """测试更新设置缺少value字段"""
    response = client.put('/api/admin/settings/OPENHARNESS_ENABLED',
        headers=admin_auth_header,
        json={'description': '新描述'}
    )
    assert response.status_code == 422


def test_update_setting_requires_admin(client, auth_header, sample_monitoring_data):
    """测试更新设置需要管理员权限"""
    response = client.put('/api/admin/settings/OPENHARNESS_ENABLED',
        headers=auth_header,
        json={'value': 'false'}
    )
    assert response.status_code == 403
