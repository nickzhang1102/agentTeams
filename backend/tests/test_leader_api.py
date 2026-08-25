"""
Leader API 测试 - FastAPI 版

迁移自 Flask test client 到 FastAPI TestClient：
- SSE 流式端点跳过（需要 mock LLM）
- 非 SSE 端点正常测试
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SKIP_MCP_INIT'] = 'true'

from tests.conftest import TestSessionLocal
from models import User, Conversation, Message, LeaderSession, LeaderAgentResult, LeaderFinalReport
from api.leader_api import _agent_result_to_dict, _build_leader_messages_and_sessions


@pytest.fixture
def leader_session(client, auth_header):
    """创建 Leader 会话记录"""
    db = TestSessionLocal()
    try:
        user = db.query(User).filter_by(username='testuser').first()
        conv = Conversation(title='测试对话', user_id=user.id)
        db.add(conv)
        db.commit()
        db.refresh(conv)

        session = LeaderSession(
            conversation_id=conv.id,
            user_message='测试消息',
            state='assessing'
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        return {
            'session_id': session.id,
            'conversation_id': conv.id,
            'user_id': user.id
        }
    finally:
        db.close()


# ========== SSE 流式端点测试（跳过） ==========

@pytest.mark.skip(reason="SSE 流式端点需要 mock LLM 服务")
def test_start_leader_session(client, auth_header, leader_session):
    """测试启动 Leader 会话（SSE 流式）"""
    pass


@pytest.mark.skip(reason="SSE 流式端点需要 mock LLM 服务")
def test_answer_questions(client, auth_header, leader_session):
    """测试回答提问（SSE 流式）"""
    pass


# ========== 非 SSE 端点测试 ==========

def test_stop_execution(client, auth_header, leader_session):
    """测试停止执行"""
    response = client.post(
        '/api/leader/stop',
        json={'session_id': leader_session['session_id']},
        headers=auth_header
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] == True


def test_get_leader_status(client, auth_header, leader_session):
    """测试查询状态"""
    # 更新状态为 completed（避免 SSE 触发）
    db = TestSessionLocal()
    try:
        session = db.get(LeaderSession, leader_session['session_id'])
        session.state = 'completed'
        db.commit()
    finally:
        db.close()

    response = client.get(
        f'/api/leader/status/{leader_session["session_id"]}',
        headers=auth_header
    )

    assert response.status_code == 200
    data = response.json()
    assert 'state' in data
    assert data['is_running'] is False
    assert data['error_message'] is None
    assert 'agent_results' not in data
    assert 'final_report' not in data
    assert data['decision_run']['legacy'] is True
    assert data['decision_run']['run_id'] is None


def test_get_leader_status_include_results(client, auth_header, leader_session):
    """测试显式请求时返回完整恢复数据"""
    db = TestSessionLocal()
    try:
        session = db.get(LeaderSession, leader_session['session_id'])
        session.state = 'completed'

        result = LeaderAgentResult(
            conversation_id=leader_session['conversation_id'],
            leader_session_id=leader_session['session_id'],
            agent_id='agent-1',
            agent_name='Agent 1',
            status='success',
            content='agent result',
            sequence_number=1,
        )
        report = LeaderFinalReport(
            conversation_id=leader_session['conversation_id'],
            leader_session_id=leader_session['session_id'],
            report='final report',
            content_locale='en-US',
        )
        db.add_all([result, report])
        db.commit()
    finally:
        db.close()

    response = client.get(
        f'/api/leader/status/{leader_session["session_id"]}?include_results=true',
        headers=auth_header
    )

    assert response.status_code == 200
    data = response.json()
    assert data['agent_results'][0]['content'] == 'agent result'
    assert data['final_report']['report'] == 'final report'
    assert data['final_report']['content_locale'] == 'en-US'


def test_historical_leader_messages_include_source_identity(leader_session):
    """历史消息必须保留翻译 source 所需的数据库 ID 和内容语言。"""
    db = TestSessionLocal()
    try:
        message = Message.create_leader_message(
            conversation_id=leader_session['conversation_id'],
            leader_session_id=leader_session['session_id'],
            message_type='progress',
            content={'text': 'Analysis in progress'},
            content_locale='en-US',
            sequence_number=1,
        )
        db.add(message)
        db.commit()
        db.refresh(message)

        data = _build_leader_messages_and_sessions(
            leader_session['conversation_id'],
            db_session=db,
        )

        assert data['messages'][0]['id'] == message.id
        assert data['messages'][0]['content_locale'] == 'en-US'
    finally:
        db.close()


def test_public_agent_result_projection_omits_private_evidence_payload():
    result = LeaderAgentResult(
        conversation_id=1,
        leader_session_id=1,
        agent_id="agent-1",
        agent_name="Agent 1",
        status="success",
        content="report",
        raw_tool_results={"ev_1": {"passage": "private passage"}},
        evidence_map=[{
            "evidence_id": "ev_1",
            "excerpt": "public excerpt",
            "raw_ref": "raw_tool_results.ev_1",
        }],
    )

    payload = _agent_result_to_dict(result, include_private_evidence=False)

    assert "raw_tool_results" not in payload
    assert "raw_ref" not in payload["evidence_map"][0]
    assert payload["evidence_map"][0]["excerpt"] == "public excerpt"


def test_agent_result_projection_is_minimal_by_default():
    result = LeaderAgentResult(
        conversation_id=1,
        leader_session_id=1,
        agent_id="agent-1",
        agent_name="Agent 1",
        status="success",
        content="report",
        raw_tool_results={"ev_1": {"passage": "private passage"}},
        evidence_map=[{
            "evidence_id": "ev_1",
            "excerpt": "bounded excerpt",
            "raw_ref": "raw_tool_results.ev_1",
        }],
    )

    payload = _agent_result_to_dict(result)

    assert "raw_tool_results" not in payload
    assert "raw_ref" not in payload["evidence_map"][0]
    assert payload["evidence_map"][0]["excerpt"] == "bounded excerpt"


def test_get_leader_status_not_found(client, auth_header):
    """测试查询不存在的会话"""
    response = client.get('/api/leader/status/999', headers=auth_header)

    assert response.status_code == 404


def test_stop_execution_not_found(client, auth_header):
    """测试停止不存在的会话"""
    response = client.post(
        '/api/leader/stop',
        json={'session_id': 999},
        headers=auth_header
    )

    assert response.status_code == 404


def test_leader_api_no_token(client):
    """测试没有 token 时访问 Leader API"""
    response = client.get('/api/leader/status/1')

    assert response.status_code == 401
