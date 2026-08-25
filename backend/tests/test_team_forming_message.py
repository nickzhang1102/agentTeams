"""
测试 Leader 消息保存功能

P1-4 重构后：测试 Message 模型的 Leader 消息功能
"""
import pytest
from models import LeaderSession, Message, User, Conversation


def test_save_team_config_message(db_session):
    """测试保存团队配置消息"""
    # 创建测试数据
    user = User(username='testuser')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='设计全栈系统',
        state='forming_team'
    )
    db_session.add(session)
    db_session.commit()

    # 创建 team_config 消息
    team_config = {
        'agents': ['backend-expert', 'frontend-expert'],
        'mode': 'parallel',
        'threshold': 0,
        'team_strategy': '前后端专家协作设计全栈系统',
        'agent_details': [
            {
                'agent_id': 'backend-expert',
                'agent_name': '后端专家',
                'reason': '负责后端架构设计'
            },
            {
                'agent_id': 'frontend-expert',
                'agent_name': '前端专家',
                'reason': '负责前端界面设计'
            }
        ]
    }

    msg = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='team_config',
        content=team_config,
        sequence_number=1
    )
    db_session.add(msg)
    db_session.commit()

    # 验证
    assert msg.id is not None
    assert msg.message_type == 'team_config'
    assert msg.content['agents'] == ['backend-expert', 'frontend-expert']
    assert msg.content['mode'] == 'parallel'
    assert msg.content['team_strategy'] == '前后端专家协作设计全栈系统'
    assert len(msg.content['agent_details']) == 2
    assert msg.sequence_number == 1


def test_team_config_with_high_risk(db_session):
    """测试高风险场景的团队配置"""
    # 创建测试数据
    user = User(username='testuser2')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test2', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='重要决策',
        state='forming_team',
        risk_level='high'
    )
    db_session.add(session)
    db_session.commit()

    # 创建包含逆向思考顾问的团队配置
    team_config = {
        'agents': ['backend-expert', 'critic-munger'],
        'mode': 'parallel',
        'threshold': 0,
        'team_strategy': '专家协作 + 逆向思考审查',
        'agent_details': [
            {
                'agent_id': 'backend-expert',
                'agent_name': '后端专家',
                'reason': '负责系统设计'
            },
            {
                'agent_id': 'critic-munger',
                'agent_name': '逆向思考顾问',
                'reason': '提供逆向思维审查'
            }
        ]
    }

    msg = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='team_config',
        content=team_config,
        sequence_number=1
    )
    db_session.add(msg)
    db_session.commit()

    # 验证
    assert 'critic-munger' in msg.content['agents']
    assert session.risk_level == 'high'


def test_team_config_updates_selected_agents(db_session):
    """测试团队配置更新 LeaderSession 的 selected_agents 字段"""
    # 创建测试数据
    user = User(username='testuser3')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test3', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='复杂任务',
        state='forming_team'
    )
    db_session.add(session)
    db_session.commit()

    # 创建团队配置
    team_config = {
        'agents': ['agent-1', 'agent-2', 'agent-3'],
        'mode': 'parallel',
        'threshold': 0,
        'team_strategy': '三位专家协作',
        'agent_details': [
            {'agent_id': 'agent-1', 'agent_name': '专家1', 'reason': '理由1'},
            {'agent_id': 'agent-2', 'agent_name': '专家2', 'reason': '理由2'},
            {'agent_id': 'agent-3', 'agent_name': '专家3', 'reason': '理由3'}
        ]
    }

    msg = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='team_config',
        content=team_config,
        sequence_number=1
    )
    db_session.add(msg)

    # 更新 session 的 selected_agents
    session.set_selected_agents_list(team_config['agents'])
    db_session.commit()

    # 验证
    db_session.refresh(session)
    assert session.get_selected_agents_list() == ['agent-1', 'agent-2', 'agent-3']

    # 验证消息已保存
    saved_msg = db_session.query(Message).filter_by(
        leader_session_id=session.id,
        message_type='team_config'
    ).first()
    assert saved_msg is not None
    assert saved_msg.content['agents'] == ['agent-1', 'agent-2', 'agent-3']


def test_multiple_team_config_messages(db_session):
    """测试多个团队配置消息（模拟重新组建团队）"""
    # 创建测试数据
    user = User(username='testuser4')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()

    conv = Conversation(title='Test4', user_id=user.id)
    db_session.add(conv)
    db_session.commit()

    # 创建 LeaderSession
    session = LeaderSession(
        conversation_id=conv.id,
        user_message='迭代任务',
        state='forming_team'
    )
    db_session.add(session)
    db_session.commit()

    # 第一次团队配置
    team_config1 = {
        'agents': ['agent-1', 'agent-2'],
        'mode': 'parallel',
        'threshold': 0,
        'team_strategy': '两位专家协作',
        'agent_details': [
            {'agent_id': 'agent-1', 'agent_name': '专家1', 'reason': '理由1'},
            {'agent_id': 'agent-2', 'agent_name': '专家2', 'reason': '理由2'}
        ]
    }

    msg1 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='team_config',
        content=team_config1,
        sequence_number=1
    )
    db_session.add(msg1)
    db_session.commit()

    # 第二次团队配置（重新组建）
    team_config2 = {
        'agents': ['agent-1', 'agent-2', 'agent-3'],
        'mode': 'parallel',
        'threshold': 0,
        'team_strategy': '三位专家协作',
        'agent_details': [
            {'agent_id': 'agent-1', 'agent_name': '专家1', 'reason': '理由1'},
            {'agent_id': 'agent-2', 'agent_name': '专家2', 'reason': '理由2'},
            {'agent_id': 'agent-3', 'agent_name': '专家3', 'reason': '理由3'}
        ]
    }

    msg2 = Message.create_leader_message(
        conversation_id=conv.id,
        leader_session_id=session.id,
        message_type='team_config',
        content=team_config2,
        sequence_number=2
    )
    db_session.add(msg2)
    db_session.commit()

    # 验证两条消息都存在
    messages = db_session.query(Message).filter_by(
        leader_session_id=session.id,
        message_type='team_config'
    ).order_by(Message.sequence_number).all()

    assert len(messages) == 2
    assert messages[0].content['agents'] == ['agent-1', 'agent-2']
    assert messages[1].content['agents'] == ['agent-1', 'agent-2', 'agent-3']
