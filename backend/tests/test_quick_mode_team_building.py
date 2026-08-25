"""_build_team_from_presets 快速模式单元测试

直接测试 team_form_nodes._build_team_from_presets 函数的团队构建逻辑。
通过 mock get_services() 控制 agent_reader / db_session / emit 行为。
"""
import pytest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['SKIP_MCP_INIT'] = 'true'

from leader.team_form_nodes import _build_team_from_presets


def _make_services(agent_metadata_map=None, has_db=True):
    """构造 mock services 对象。

    Args:
        agent_metadata_map: dict[agent_id → metadata | None]
        has_db: 是否 mock db_session
    """
    svc = MagicMock()

    # agent_reader mock
    if agent_metadata_map is not None:
        def _get_metadata(agent_id):
            return agent_metadata_map.get(agent_id)
        svc.agent_reader.get_agent_metadata.side_effect = _get_metadata
    else:
        svc.agent_reader = None

    # db_session mock
    if has_db:
        svc.db_session = MagicMock()
    else:
        svc.db_session = None

    return svc


class TestBuildTeamFromPresets:
    """_build_team_from_presets 测试集"""

    @patch('leader.team_form_nodes.get_services')
    @patch('leader.team_form_nodes._emit')
    def test_normal_preset_builds_team(self, mock_emit, mock_get_services):
        """正常 pre_selected_agents 构建团队，元数据正确映射"""
        metadata_map = {
            'agent-a': {'name': 'Agent A', 'description': '分析专家'},
            'agent-b': {'name': 'Agent B', 'description': '辅助顾问'},
        }
        mock_get_services.return_value = _make_services(metadata_map, has_db=False)

        state = {
            'session_id': 1,
            'conversation_id': 10,
            'user_message': '测试消息',
            'locale': 'en-US',
            'pre_selected_agents': ['agent-a', 'agent-b'],
            'sse_events': [],
        }

        with patch('leader.dag_planner.DAGPlanner') as MockPlanner:
            result = _build_team_from_presets(state, ['agent-a', 'agent-b'])

        agents = result['selected_agents']
        assert len(agents) == 2
        assert agents[0]['agent_id'] == 'agent-a'
        assert agents[0]['agent_name'] == 'Agent A'
        assert agents[0]['role_description'] == '分析专家'
        assert agents[1]['agent_id'] == 'agent-b'
        assert result['current_phase'] == 'team_form_dag'
        start_event = result['sse_events'][0]
        assert start_event['content'] == 'Building the team from preselected agents...'
        assert start_event['message_key'] == 'leader.phase.forming_preset_team'
        assert start_event['message'] == start_event['content']
        selection_event, ready_event = result['sse_events'][1:]
        assert selection_event['content'] == 'Quick mode team'
        assert selection_event['content_locale'] == 'en-US'
        assert ready_event['content_locale'] == 'en-US'
        assert ready_event['team']['name'].startswith('Quick team - ')
        assert ready_event['team']['description'] == 'Quick mode team'

    @patch('leader.team_form_nodes.get_services')
    @patch('leader.team_form_nodes._emit')
    def test_metadata_none_degrades_gracefully(self, mock_emit, mock_get_services):
        """某个 agent 的 metadata 为 None 时，降级为 raw agent_id"""
        metadata_map = {
            'agent-a': {'name': 'Agent A', 'description': 'OK'},
            'agent-b': None,  # metadata 缺失
        }
        mock_get_services.return_value = _make_services(metadata_map, has_db=False)

        state = {
            'session_id': 2,
            'conversation_id': 20,
            'user_message': '测试消息',
            'pre_selected_agents': ['agent-a', 'agent-b'],
            'sse_events': [],
        }

        with patch('leader.dag_planner.DAGPlanner'):
            result = _build_team_from_presets(state, ['agent-a', 'agent-b'])

        agents = result['selected_agents']
        assert len(agents) == 2
        # agent-a 有元数据
        assert agents[0]['agent_name'] == 'Agent A'
        # agent-b 降级：用 agent_id 作为 name
        assert agents[1]['agent_id'] == 'agent-b'
        assert agents[1]['agent_name'] == 'agent-b'
        assert agents[1]['role_description'] == ''

    @patch('leader.team_form_nodes.get_services')
    @patch('leader.team_form_nodes._emit')
    def test_all_metadata_none_fallback_to_ids(self, mock_emit, mock_get_services):
        """所有 agent metadata 均为 None，全部降级"""
        metadata_map = {
            'ghost-a': None,
            'ghost-b': None,
        }
        mock_get_services.return_value = _make_services(metadata_map, has_db=False)

        state = {
            'session_id': 3,
            'conversation_id': 30,
            'user_message': '全部无效',
            'pre_selected_agents': ['ghost-a', 'ghost-b'],
            'sse_events': [],
        }

        with patch('leader.dag_planner.DAGPlanner'):
            result = _build_team_from_presets(state, ['ghost-a', 'ghost-b'])

        agents = result['selected_agents']
        assert len(agents) == 2
        for agent in agents:
            assert agent['agent_name'] == agent['agent_id']
            assert agent['role_description'] == ''

    @patch('leader.team_form_nodes.get_services')
    @patch('leader.team_form_nodes._emit')
    def test_no_agent_reader_fallback(self, mock_emit, mock_get_services):
        """agent_reader 为 None 时，所有 agent 降级为 raw id"""
        mock_get_services.return_value = _make_services(None, has_db=False)

        state = {
            'session_id': 4,
            'conversation_id': 40,
            'user_message': '无 reader',
            'pre_selected_agents': ['raw-a', 'raw-b'],
            'sse_events': [],
        }

        result = _build_team_from_presets(state, ['raw-a', 'raw-b'])

        agents = result['selected_agents']
        assert len(agents) == 2
        assert agents[0]['agent_id'] == 'raw-a'
        assert agents[0]['agent_name'] == 'raw-a'
        assert agents[1]['agent_name'] == 'raw-b'

    @patch('leader.team_form_nodes.get_services')
    @patch('leader.team_form_nodes._emit')
    def test_dag_plan_generated(self, mock_emit, mock_get_services):
        """快速模式生成 DAG 计划"""
        metadata_map = {'agent-x': {'name': 'X', 'description': ''}}
        svc = _make_services(metadata_map, has_db=False)
        mock_get_services.return_value = svc

        state = {
            'session_id': 5,
            'conversation_id': 50,
            'user_message': 'DAG 测试',
            'pre_selected_agents': ['agent-x'],
            'sse_events': [],
        }

        result = _build_team_from_presets(state, ['agent-x'])

        dag_plan = result['dag_execution_plan']
        assert 'nodes' in dag_plan
        assert 'execution_batches' in dag_plan
        assert len(dag_plan['nodes']) == 1
        assert dag_plan['nodes'][0]['agent_id'] == 'agent-x'
