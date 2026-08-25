"""
测试精选案例在"我的案例"中保留

验证：
1. 用户创建的对话被标记为精选后，仍在"我的案例"中可见
2. 精选案例同时在 /api/conversations/featured 中展示
"""
import pytest
from fastapi.testclient import TestClient


def test_featured_conversation_visible_in_my_list(client, auth_header, db_session):
    """验证精选对话在用户的"我的案例"中保留"""
    from models import Conversation

    # 1. 创建一个普通对话
    response = client.post(
        '/api/conversations',
        json={'title': '我的重要案例', 'is_review_mode': False},
        headers=auth_header
    )
    assert response.status_code == 201
    conv_id = response.json()['id']

    # 2. 验证在"我的案例"中可见
    response = client.get('/api/conversations', headers=auth_header)
    assert response.status_code == 200
    my_convs = response.json()['conversations']
    assert len(my_convs) == 1
    assert my_convs[0]['id'] == conv_id
    assert my_convs[0]['is_featured'] is False

    # 3. 管理员将其标记为精选（模拟后台操作）
    conv = db_session.query(Conversation).get(conv_id)
    conv.is_featured = True
    conv.featured_order = 1
    db_session.commit()

    # 4. 验证仍在"我的案例"中可见
    response = client.get('/api/conversations', headers=auth_header)
    assert response.status_code == 200
    my_convs = response.json()['conversations']
    assert len(my_convs) == 1
    assert my_convs[0]['id'] == conv_id
    assert my_convs[0]['is_featured'] is True
    assert my_convs[0]['featured_order'] == 1

    # 5. 验证同时在精选案例列表中展示（无需认证）
    response = client.get('/api/conversations/featured')
    assert response.status_code == 200
    featured = response.json()
    assert len(featured) == 1
    assert featured[0]['id'] == conv_id
    assert featured[0]['title'] == '我的重要案例'


def test_multiple_featured_conversations(client, auth_header, db_session):
    """验证用户有多个精选对话时的表现"""
    from models import Conversation

    # 创建 3 个对话
    conv_ids = []
    for i in range(3):
        response = client.post(
            '/api/conversations',
            json={'title': f'案例 {i+1}', 'is_review_mode': False},
            headers=auth_header
        )
        assert response.status_code == 201
        conv_ids.append(response.json()['id'])

    # 将前 2 个标记为精选
    for idx, conv_id in enumerate(conv_ids[:2]):
        conv = db_session.query(Conversation).get(conv_id)
        conv.is_featured = True
        conv.featured_order = idx + 1
    db_session.commit()

    # 验证"我的案例"包含全部 3 个对话
    response = client.get('/api/conversations', headers=auth_header)
    assert response.status_code == 200
    my_convs = response.json()['conversations']
    assert len(my_convs) == 3

    # 验证精选列表只包含 2 个精选对话
    response = client.get('/api/conversations/featured')
    assert response.status_code == 200
    featured = response.json()
    assert len(featured) == 2
    featured_ids = [f['id'] for f in featured]
    assert set(featured_ids) == set(conv_ids[:2])


def test_archived_featured_conversation(client, auth_header, db_session):
    """验证归档的精选对话行为"""
    from models import Conversation

    # 创建精选对话
    response = client.post(
        '/api/conversations',
        json={'title': '归档测试', 'is_review_mode': False},
        headers=auth_header
    )
    assert response.status_code == 201
    conv_id = response.json()['id']

    # 标记为精选
    conv = db_session.query(Conversation).get(conv_id)
    conv.is_featured = True
    conv.featured_order = 1
    db_session.commit()

    # 归档对话
    response = client.post(f'/api/conversations/{conv_id}/archive', headers=auth_header)
    assert response.status_code == 200

    # 验证在"我的案例"默认列表中不可见（archived=false）
    response = client.get('/api/conversations', headers=auth_header)
    assert response.status_code == 200
    my_convs = response.json()['conversations']
    assert len(my_convs) == 0

    # 验证在"我的案例"归档列表中可见（archived=true）
    response = client.get('/api/conversations?archived=true', headers=auth_header)
    assert response.status_code == 200
    archived_convs = response.json()['conversations']
    assert len(archived_convs) == 1
    assert archived_convs[0]['id'] == conv_id

    # 验证精选列表中不展示（is_archived=True 被排除）
    response = client.get('/api/conversations/featured')
    assert response.status_code == 200
    featured = response.json()
    assert len(featured) == 0
