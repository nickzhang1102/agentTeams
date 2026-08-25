"""
测试 Agent 分类树 API（FastAPI TestClient）

迁移自 Flask test_client，使用 conftest 提供的 client 和 auth_header。
注意：build_category_tree 现在使用扁平结构（DB category 字段），
不再使用旧的子分类（internal/surgery/specialty/other）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_get_agent_tree(client, auth_header):
    """测试获取 Agent 分类树"""
    response = client.get('/api/agents/tree', headers=auth_header)

    assert response.status_code == 200
    data = response.json()

    # 验证结构
    assert 'tree' in data
    assert 'agents' in data
    # 至少包含 medical, business, finance 三个分类（CATEGORY_META 兜底）
    assert len(data['tree']) >= 3

    # 验证医疗专家分支（扁平结构，agents 直接在分类下）
    medical = data['tree']['medical']
    assert medical['name'] == '医疗专家'
    assert 'agents' in medical
