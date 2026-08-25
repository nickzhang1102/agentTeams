"""测试新增的 execute_tool 测试用例"""
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.harness.harness_adapter import HarnessToolRegistry

def test_execute_tool_success():
    """测试工具正常执行"""
    print("测试 1: 工具正常执行")

    with tempfile.TemporaryDirectory() as workspace:
        registry = HarnessToolRegistry(workspace_dir=workspace)

        # 执行 bash 工具
        result = registry.execute_tool('bash', {
            'command': 'echo "test"',
            'timeout_seconds': 10
        })

        print(f"  success: {result['success']}")
        print(f"  result: {result.get('result', '').strip()}")
        print(f"  error: {result.get('error', 'None')}")

        assert result['success'] is True, "工具应执行成功"
        assert 'test' in result['result'], "输出应包含 'test'"
        assert result['error'] is None, "不应有错误"
        assert 'metadata' in result, "应包含 metadata"

        print("  [OK] 工具正常执行测试通过\n")

def test_execute_tool_not_found():
    """测试执行不存在的工具"""
    print("测试 2: 执行不存在的工具")

    registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

    result = registry.execute_tool('nonexistent_tool', {})

    print(f"  success: {result['success']}")
    print(f"  error: {result.get('error', 'None')}")

    assert result['success'] is False, "不存在的工具应失败"
    assert 'not found' in result['error'], "错误信息应包含 'not found'"

    print("  [OK] 不存在的工具测试通过\n")

def test_execute_tool_invalid_params():
    """测试工具执行参数错误"""
    print("测试 3: 工具执行参数错误")

    registry = HarnessToolRegistry(workspace_dir='/tmp/test_workspace')

    # bash 工具缺少必需的 command 参数
    result = registry.execute_tool('bash', {})

    print(f"  success: {result['success']}")
    print(f"  error: {result.get('error', 'None')[:80]}")

    assert result['success'] is False, "参数错误应失败"
    assert 'error' in result, "应包含错误信息"

    print("  [OK] 参数错误测试通过\n")

def main():
    print("=" * 60)
    print("新增 execute_tool 测试用例")
    print("=" * 60)
    print()

    try:
        test_execute_tool_success()
        test_execute_tool_not_found()
        test_execute_tool_invalid_params()

        print("=" * 60)
        print("[SUCCESS] 所有新增测试用例通过！")
        print("=" * 60)
        return 0
    except Exception as e:
        print("=" * 60)
        print(f"[FAIL] 测试失败: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
