"""独立测试脚本 - 测试 HarnessToolRegistry"""
import sys
import os

# 添加 backend 到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.harness.harness_adapter import HarnessToolRegistry

def test_registry_initialization():
    """测试工具注册初始化"""
    print("测试 1: 工具注册初始化")

    registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

    # 验证工具数量
    tools = registry.list_tools()
    print(f"  [OK] 已注册 {len(tools)} 个工具")

    # 验证工具结构
    tool = tools[0]
    assert 'name' in tool, "工具应包含 name 字段"
    assert 'description' in tool, "工具应包含 description 字段"
    assert 'input_schema' in tool, "工具应包含 input_schema 字段"
    print(f"  [OK] 工具结构正确: {tool['name']}")

    assert len(tools) >= 35, f"预期至少 35 个工具，实际 {len(tools)} 个"
    print(f"  [OK] 工具数量符合预期 (>= 35)")

def test_list_tools_returns_valid_structure():
    """测试工具列表返回正确结构"""
    print("\n测试 2: 工具列表结构验证")

    registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')
    tools = registry.list_tools()

    for tool in tools:
        assert isinstance(tool, dict), "工具应为字典类型"
        assert 'name' in tool, "工具应包含 name 字段"
        assert 'description' in tool, "工具应包含 description 字段"
        assert 'input_schema' in tool, "工具应包含 input_schema 字段"

    print(f"  [OK] 所有 {len(tools)} 个工具结构正确")

def test_registry_has_core_tools():
    """测试注册了核心工具"""
    print("\n测试 3: 核心工具验证")

    registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')
    tools = registry.list_tools()
    tool_names = {tool['name'] for tool in tools}

    # 验证核心工具存在
    core_tools = {'bash', 'read_file', 'write_file', 'edit_file', 'grep', 'glob', 'agent'}
    missing_tools = core_tools - tool_names

    if missing_tools:
        print(f"  [FAIL] 缺少工具: {missing_tools}")
        raise AssertionError(f"缺少工具: {missing_tools}")

    print(f"  [OK] 核心工具全部存在: {core_tools}")

def test_get_tool_schema():
    """测试获取单个工具 schema"""
    print("\n测试 4: 获取工具 schema")

    registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

    # 获取 bash 工具 schema
    schema = registry.get_tool_schema('bash')
    assert schema is not None, "bash 工具应存在"
    assert schema['name'] == 'bash', "工具名称应为 bash"
    assert 'description' in schema, "schema 应包含 description"
    assert 'input_schema' in schema, "schema 应包含 input_schema"

    print(f"  [OK] bash 工具 schema 获取成功")
    print(f"    描述: {schema['description'][:50]}...")

def test_get_nonexistent_tool_schema():
    """测试获取不存在的工具 schema"""
    print("\n测试 5: 获取不存在的工具")

    registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

    schema = registry.get_tool_schema('nonexistent_tool')
    assert schema is None, "不存在的工具应返回 None"

    print(f"  [OK] 不存在的工具正确返回 None")

def main():
    """运行所有测试"""
    print("=" * 60)
    print("HarnessToolRegistry 适配器测试")
    print("=" * 60)

    try:
        test_registry_initialization()
        test_list_tools_returns_valid_structure()
        test_registry_has_core_tools()
        test_get_tool_schema()
        test_get_nonexistent_tool_schema()

        print("\n" + "=" * 60)
        print("[SUCCESS] 所有测试通过！")
        print("=" * 60)
        return 0
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[FAIL] 测试失败: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
