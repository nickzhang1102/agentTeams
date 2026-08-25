import pytest
import os
import tempfile
from services.agent_metadata import AgentMetadataParser


@pytest.fixture
def temp_agents_dir():
    """创建临时 agents 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试 agent 文件
        agent_content = """---
name: 测试专家
description: 用于测试的专家
capabilities:
  - backend
  - database
  - api-design
skill_level: 5
tags:
  - 微服务
  - 高并发
preferred_contexts:
  - 架构设计
  - 性能优化
---

# 测试专家指令
这是一个测试专家的详细指令。
"""
        agent_file = os.path.join(tmpdir, 'test-expert.md')
        with open(agent_file, 'w', encoding='utf-8') as f:
            f.write(agent_content)

        yield tmpdir


def test_parse_agent_metadata(temp_agents_dir):
    """测试解析 agent 元数据"""
    parser = AgentMetadataParser(temp_agents_dir)
    metadata = parser.parse('test-expert')

    assert metadata['id'] == 'test-expert'
    assert metadata['name'] == '测试专家'
    assert metadata['description'] == '用于测试的专家'
    assert 'backend' in metadata['capabilities']
    assert 'database' in metadata['capabilities']
    assert metadata['skill_level'] == 5
    assert '微服务' in metadata['tags']
    assert '架构设计' in metadata['preferred_contexts']


def test_get_all_agents(temp_agents_dir):
    """测试获取所有 agent"""
    parser = AgentMetadataParser(temp_agents_dir)
    all_agents = parser.get_all_agents()

    assert len(all_agents) == 1
    assert all_agents[0]['id'] == 'test-expert'


def test_parse_nonexistent_agent(temp_agents_dir):
    """测试解析不存在的 agent"""
    parser = AgentMetadataParser(temp_agents_dir)
    metadata = parser.parse('nonexistent')

    assert metadata is None
