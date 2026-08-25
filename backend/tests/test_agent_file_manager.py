"""测试 AgentFileManager 服务（FastAPI 版）"""
import pytest
import os
from pathlib import Path
from services.agent_file_manager import AgentFileManager


@pytest.fixture
def file_manager():
    """创建 AgentFileManager 实例（无需 app context）"""
    manager = AgentFileManager()
    return manager


def test_validate_agent_id_valid(file_manager):
    """测试有效的agent_id验证"""
    assert file_manager.validate_agent_id('test-agent') is True
    assert file_manager.validate_agent_id('Agent123') is True
    assert file_manager.validate_agent_id('my-agent-123') is True


def test_validate_agent_id_invalid(file_manager):
    """测试无效的agent_id验证"""
    # 包含非法字符
    assert file_manager.validate_agent_id('test_agent') is False  # 下划线不允许
    assert file_manager.validate_agent_id('test.agent') is False  # 点不允许
    assert file_manager.validate_agent_id('test agent') is False  # 空格不允许

    # 路径遍历攻击
    assert file_manager.validate_agent_id('../etc/passwd') is False
    assert file_manager.validate_agent_id('..\\windows\\system32') is False
    assert file_manager.validate_agent_id('test/../../../etc') is False

    # 空字符串
    assert file_manager.validate_agent_id('') is False
    assert file_manager.validate_agent_id(None) is False


def test_create_agent_file(file_manager, tmp_path):
    """测试创建Agent文件"""
    # 使用临时目录
    file_manager.agents_dir = tmp_path

    agent_id = 'test-create-agent'
    metadata = {
        'name': 'Test Agent',
        'description': 'A test agent for unit testing',
        'model': 'claude-sonnet-4-6-20250514'
    }
    content = '# Test Agent\n\nThis is a test agent.'

    file_path = file_manager.create_agent_file(agent_id, metadata, content)

    # 验证文件创建成功
    assert os.path.exists(file_path)
    assert file_path.name == f'{agent_id}.md'

    # 验证文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        file_content = f.read()

    assert 'name: Test Agent' in file_content
    assert 'description: A test agent for unit testing' in file_content
    assert '# Test Agent' in file_content


def test_read_agent_file(file_manager):
    """测试读取Agent文件"""
    # 读取一个现有的Agent文件（假设存在）
    # 如果不存在，跳过测试
    agents_dir = Path(file_manager.agents_dir)
    md_files = list(agents_dir.glob('*.md'))

    if not md_files:
        pytest.skip('No agent files found')

    # 读取第一个文件
    test_file = md_files[0]
    agent_id = test_file.stem

    metadata, content = file_manager.read_agent_file(agent_id)

    # 验证读取结果
    assert isinstance(metadata, dict)
    assert 'name' in metadata or 'title' in metadata
    assert isinstance(content, str)


def test_update_agent_file(file_manager, tmp_path):
    """测试更新Agent文件"""
    file_manager.agents_dir = tmp_path

    # 先创建文件
    agent_id = 'test-update-agent'
    metadata = {'name': 'Old Name'}
    content = 'Old content'
    file_manager.create_agent_file(agent_id, metadata, content)

    # 更新文件
    new_metadata = {'name': 'New Name', 'description': 'Updated'}
    new_content = '# New Content'
    file_manager.update_agent_file(agent_id, new_metadata, new_content)

    # 验证更新成功
    read_metadata, read_content = file_manager.read_agent_file(agent_id)
    assert read_metadata['name'] == 'New Name'
    assert '# New Content' in read_content


def test_delete_agent_file(file_manager, tmp_path):
    """测试删除Agent文件"""
    file_manager.agents_dir = tmp_path

    # 先创建文件
    agent_id = 'test-delete-agent'
    metadata = {'name': 'To Delete'}
    content = 'Content'
    file_path = file_manager.create_agent_file(agent_id, metadata, content)

    # 确认文件存在
    assert os.path.exists(file_path)

    # 删除文件
    file_manager.delete_agent_file(agent_id)

    # 验证文件已删除
    assert not os.path.exists(file_path)


def test_create_file_with_invalid_agent_id(file_manager, tmp_path):
    """测试使用无效agent_id创建文件应被拒绝"""
    file_manager.agents_dir = tmp_path

    with pytest.raises(ValueError, match='Invalid agent_id'):
        file_manager.create_agent_file('../malicious', {}, 'content')


def test_path_traversal_protection(file_manager, tmp_path):
    """测试路径遍历攻击防护"""
    file_manager.agents_dir = tmp_path

    # 尝试路径遍历攻击
    malicious_ids = [
        '../../../etc/passwd',
        '..\\..\\..\\windows\\system32',
        'agent/../../../etc/passwd'
    ]

    for agent_id in malicious_ids:
        with pytest.raises(ValueError):
            file_manager.create_agent_file(agent_id, {}, 'content')


def test_create_existing_file_should_fail(file_manager, tmp_path):
    """测试创建已存在的文件应抛出错误"""
    file_manager.agents_dir = tmp_path

    # 先创建文件
    agent_id = 'test-duplicate'
    metadata = {'name': 'Original'}
    content = 'Original content'
    file_manager.create_agent_file(agent_id, metadata, content)

    # 尝试再次创建同名文件
    with pytest.raises(IOError, match='Agent file already exists'):
        file_manager.create_agent_file(agent_id, {'name': 'Duplicate'}, 'Duplicate content')


def test_read_nonexistent_file_should_fail(file_manager, tmp_path):
    """测试读取不存在的文件应抛出错误"""
    file_manager.agents_dir = tmp_path

    with pytest.raises(FileNotFoundError, match='Agent file not found'):
        file_manager.read_agent_file('nonexistent-agent')


def test_parse_invalid_yaml_frontmatter(file_manager, tmp_path):
    """测试解析无效YAML frontmatter"""
    file_manager.agents_dir = tmp_path

    # 创建一个包含无效YAML的文件
    agent_id = 'test-invalid-yaml'
    invalid_content = """---
name: Test Agent
description: [invalid yaml structure
  - broken
model: inherit
---

# Test Agent
"""

    # 手动创建文件（绕过正常创建流程）
    file_path = tmp_path / f'{agent_id}.md'
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(invalid_content)

    # 读取文件应该不崩溃，但返回空metadata
    metadata, content = file_manager.read_agent_file(agent_id)

    # YAML解析失败时返回空字典
    assert isinstance(metadata, dict)
    # content应该包含Markdown内容（即使YAML无效）
    assert '# Test Agent' in content


def test_validate_agent_id_detailed_error_messages(file_manager, tmp_path):
    """测试validate_agent_id的详细错误信息"""
    file_manager.agents_dir = tmp_path

    # 测试空值错误
    with pytest.raises(ValueError, match='agent_id cannot be None'):
        file_manager.create_agent_file(None, {}, 'content')

    # 测试类型错误
    with pytest.raises(ValueError, match='agent_id must be string'):
        file_manager.create_agent_file(123, {}, 'content')

    # 测试空字符串错误
    with pytest.raises(ValueError, match='agent_id cannot be empty'):
        file_manager.create_agent_file('', {}, 'content')

    # 测试路径遍历错误
    with pytest.raises(ValueError, match="path traversal sequence"):
        file_manager.create_agent_file('../etc/passwd', {}, 'content')

    # 测试路径分隔符错误
    with pytest.raises(ValueError, match="path separators"):
        file_manager.create_agent_file('test/agent', {}, 'content')

    # 测试非法字符错误
    with pytest.raises(ValueError, match='illegal characters'):
        file_manager.create_agent_file('test_agent', {}, 'content')
